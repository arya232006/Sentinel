"""FastAPI surface: scope authorization, runs, SSE, and the target harness.

The target agents are served here too, so send_to_target makes a genuine HTTP
call rather than an in-process shortcut.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from sentinel import config
from sentinel.api.auth import token_gate
from sentinel.api.events import manager, sse_format
from sentinel.scope import ScopeDraft, create_scope, get_scope, validate_scope
from sentinel.store import repo
from sentinel.targets import TARGET_IDS, get_target

app = FastAPI(title="Sentinel", version="0.1.0")

# Order matters, and it is the reverse of what it reads like: Starlette runs the
# LAST-added middleware outermost, so CORS has to be added after the token gate.
# Added the other way round, a 401 would unwind without ever passing through
# CORS, and the browser would report an opaque cross-origin failure instead of
# the actual reason the call was refused.
app.add_middleware(BaseHTTPMiddleware, dispatch=token_gate)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    repo.connect()
    repo.seed_patterns()


# ------------------------------------------------------------------ meta ---
@app.get("/healthz")
def healthz() -> dict:
    """Liveness only, and unauthenticated - a load balancer health check has
    nowhere to keep a secret. Everything a probe does not need to know is in
    /health, which is behind the token."""
    return {"ok": True}


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "profile": config.profile().name,
        "budget_cap": config.profile().usd_cap,
        "budget_warn": config.profile().usd_warn,
        "fake_llm": config.fake_llm(),
        "provider": config.provider(),
        "shakedown_mode": config.is_shakedown(),
        "shakedown_warning": (
            "Non-Anthropic backend. Findings are tagged provenance=shakedown and "
            "say nothing about Claude's behaviour, judge accuracy, or the "
            "attacker guardrail."
        ) if config.is_shakedown() else None,
        "api_key_present": bool(config.api_key()),
        "attacker_model": config.ATTACKER_MODEL,
        "target_model": config.TARGET_MODEL,
        "targets": list(TARGET_IDS),
        "categories": list(config.ATTACK_CATEGORIES),
    }


# ---------------------------------------------------------------- scopes ---
@app.post("/scopes")
def create_scope_endpoint(draft: ScopeDraft) -> dict:
    scope = create_scope(draft)
    return scope.model_dump(mode="json")


@app.get("/scopes")
def list_scopes() -> list[dict]:
    return repo.list_scopes()


@app.get("/scopes/{scope_id}")
def get_scope_endpoint(scope_id: str) -> dict:
    scope = get_scope(scope_id)
    if scope is None:
        raise HTTPException(404, f"no scope {scope_id}")
    return scope.model_dump(mode="json")


# ------------------------------------------------------------------ runs ---
class StartRun(BaseModel):
    scope_id: str


@app.post("/runs")
async def start_run(body: StartRun) -> dict:
    scope = get_scope(body.scope_id)
    if scope is None:
        raise HTTPException(404, f"no scope {body.scope_id}")

    check = validate_scope(body.scope_id)
    if not check.ok:
        raise HTTPException(400, f"scope not usable: {check.reason}")

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    manager.start(run_id, body.scope_id, scope.model_dump(mode="json"))
    return {"run_id": run_id, "scope_id": body.scope_id, "status": "running"}


@app.get("/runs")
def list_runs() -> list[dict]:
    return manager.all()


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    session = manager.get(run_id)
    if session is None:
        stored = repo.get_run(run_id)
        if stored is None:
            raise HTTPException(404, f"no run {run_id}")
        return stored
    return {
        "run_id": run_id,
        "scope_id": session.scope_id,
        "status": session.status,
        "pending_interrupt": session.pending_interrupt,
        "final_state": _safe_state(session.final_state),
    }


@app.get("/runs/{run_id}/events")
async def stream_events(run_id: str) -> StreamingResponse:
    session = manager.get(run_id)
    if session is None:
        raise HTTPException(404, f"no run {run_id}")

    async def generator():
        # Replay history first so a late subscriber (or a reconnect) sees the
        # whole run, not just what happens from now on. Track the highest seq
        # replayed and drop anything the queue re-delivers below it, or a
        # mid-run subscriber would see each pending event twice.
        replayed = list(session.history)
        last_seq = 0
        for evt in replayed:
            last_seq = max(last_seq, evt.get("seq", 0))
            yield sse_format(evt)
            if evt["type"] == "done":
                return
        while True:
            try:
                evt = await asyncio.wait_for(session.queue.get(), timeout=15.0)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            if evt.get("seq", 0) <= last_seq:
                continue  # already delivered during replay
            last_seq = evt.get("seq", last_seq)
            yield sse_format(evt)
            if evt["type"] == "done":
                return

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ResumeBody(BaseModel):
    decision: str | bool = True
    notes: str = ""


@app.post("/runs/{run_id}/resume")
def resume_run(run_id: str, body: ResumeBody) -> dict:
    session = manager.get(run_id)
    if session is None:
        raise HTTPException(404, f"no run {run_id}")
    if session.pending_interrupt is None:
        raise HTTPException(409, "run is not waiting on a decision")

    gate = session.pending_interrupt.get("gate")
    ok = session.provide_resume({"approved": _as_bool(body.decision), "notes": body.notes})
    return {"ok": ok, "gate": gate, "decision": _as_bool(body.decision)}


@app.get("/runs/{run_id}/report")
def get_report(run_id: str) -> dict:
    session = manager.get(run_id)
    if session and session.final_state:
        return session.final_state.get("report", {})
    findings = repo.list_findings(run_id)
    if not findings:
        raise HTTPException(404, "no report available for this run yet")
    return {"run_id": run_id, "findings": findings}


@app.get("/runs/{run_id}/trace")
def get_trace(run_id: str) -> list[dict]:
    return repo.list_trace(run_id)


# ------------------------------------------------------------- knowledge ---
@app.get("/knowledge/techniques")
def list_techniques(learned_only: bool = False) -> dict:
    """The planner's technique KB: the curated file plus whatever runs have
    discovered for themselves. Learned entries carry the run and target that
    found them, so a plan citing one is traceable."""
    from sentinel.knowledge.retrieval import learned_techniques, load_techniques

    learned = learned_techniques()
    return {
        "provenance": config.run_provenance(),
        "curated": [] if learned_only else list(load_techniques()),
        "learned": learned,
        "counts": {
            "curated": len(load_techniques()),
            "learned": len(learned),
        },
    }


# --------------------------------------------------------------- targets ---
class TargetChat(BaseModel):
    messages: list[dict[str, Any]]
    session_id: str = ""
    attack_id: str | None = None
    turn: int | None = None
    # Appended to the target's system prompt. Fix-and-reverify uses it to
    # replay an attack against a target patched with the finding's own
    # mitigation; nothing else in the request changes.
    system_suffix: str = ""
    # Overrides which model backs the target, for the differential audit.
    model: str | None = None


@app.post("/targets/{target_id}/chat")
def target_chat(target_id: str, body: TargetChat) -> dict:
    try:
        target = get_target(target_id)
    except KeyError:
        raise HTTPException(404, f"unknown target '{target_id}'")

    kwargs: dict[str, Any] = {
        "session_id": body.session_id,
        "system_suffix": body.system_suffix,
        "model": body.model,
    }
    if target_id == "tool_agent":
        kwargs.update(attack_id=body.attack_id, turn=body.turn)
    resp = target.chat(body.messages, **kwargs)
    return resp.to_dict()


class PlantBody(BaseModel):
    scope_id: str
    doc_id: str
    text: str


@app.post("/targets/rag/plant")
def plant_rag_document(body: PlantBody) -> dict:
    """Scope-gated: planting is itself an attack action and requires the
    rag_context_poisoning category to be authorized."""
    check = validate_scope(body.scope_id, "rag_context_poisoning")
    if not check.ok:
        raise HTTPException(403, f"not authorized: {check.reason}")
    from sentinel.targets.rag_agent import plant_document

    return plant_document(body.doc_id, body.text)


@app.delete("/targets/rag/planted")
def clear_planted() -> dict:
    from sentinel.targets.rag_agent import remove_planted

    return {"removed": remove_planted()}


# ----------------------------------------------------------------- utils ---
def _as_bool(v: str | bool) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "yes", "approve", "approved", "1")


def _safe_state(state: dict | None) -> dict | None:
    if not state:
        return None
    return {
        "status": state.get("status"),
        "abort_reason": state.get("abort_reason"),
        "budget": state.get("budget"),
        "findings": state.get("findings", []),
        "attack_plan": state.get("attack_plan", []),
        "recon_profile": state.get("recon_profile", {}),
        "learned_techniques": state.get("learned_techniques", []),
    }
