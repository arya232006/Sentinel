"""SSE broker and background run sessions.

The graph is synchronous, so each run executes on its own thread and pushes
typed events onto an asyncio.Queue owned by the event loop. Interrupts park the
thread until a /resume call supplies a decision.
"""

from __future__ import annotations

import asyncio
import json
import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from sentinel.graph.build import build_graph
from sentinel.llm import budget as budget_mod
from sentinel.llm.client import set_trace_sink
from sentinel.state import initial_state
from sentinel.store import repo


@dataclass
class RunSession:
    run_id: str
    scope_id: str
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    history: list[dict] = field(default_factory=list)
    pending_interrupt: dict | None = None
    resume_event: threading.Event = field(default_factory=threading.Event)
    resume_value: Any = None
    status: str = "starting"
    final_state: dict | None = None
    thread: threading.Thread | None = None
    _seq: int = 0

    # ------------------------------------------------------------------
    def emit(self, event_type: str, data: dict) -> None:
        """Thread-safe push onto the SSE queue.

        Every event carries a monotonic `seq`. A subscriber replays history
        first, then skips any queued event it already saw - without this a
        client that connects mid-run receives the same event twice (once from
        history, once from the queue) and acts on it twice.
        """
        self._seq += 1
        evt = {
            "type": event_type,
            "seq": self._seq,
            "run_id": self.run_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        self.history.append(evt)
        try:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, evt)
        except RuntimeError:
            pass  # loop closed; run is being torn down

    def await_resume(self, payload: dict) -> Any:
        """Park the run thread until /resume supplies a decision."""
        self.pending_interrupt = payload
        self.status = "paused_for_human"
        self.emit("interrupt", payload)
        self.resume_event.wait()
        self.resume_event.clear()
        self.pending_interrupt = None
        self.status = "running"
        value = self.resume_value
        self.resume_value = None
        self.emit("status", {"status": "running", "resumed_with": value})
        return value

    def provide_resume(self, value: Any) -> bool:
        if self.pending_interrupt is None:
            return False
        self.resume_value = value
        self.resume_event.set()
        return True


class RunManager:
    def __init__(self) -> None:
        self._runs: dict[str, RunSession] = {}
        self._lock = threading.Lock()

    def get(self, run_id: str) -> RunSession | None:
        return self._runs.get(run_id)

    def all(self) -> list[dict]:
        return [
            {"run_id": r.run_id, "scope_id": r.scope_id, "status": r.status}
            for r in self._runs.values()
        ]

    def start(self, run_id: str, scope_id: str, scope: dict) -> RunSession:
        loop = asyncio.get_running_loop()
        session = RunSession(run_id=run_id, scope_id=scope_id, loop=loop)
        with self._lock:
            self._runs[run_id] = session

        t = threading.Thread(target=_execute, args=(session, scope), daemon=True)
        session.thread = t
        t.start()
        return session


def _execute(session: RunSession, scope: dict) -> None:
    """Run the graph to completion on a worker thread."""
    run_id = session.run_id
    budget = budget_mod.new_budget()

    # Route every traced LLM call into this run's event stream, live.
    set_trace_sink(lambda entry: _on_trace(session, entry))

    try:
        repo.insert_run(run_id, session.scope_id, budget)
        graph = build_graph(checkpointer=InMemorySaver())
        cfg = {"configurable": {"thread_id": run_id}, "recursion_limit": 250}
        state = initial_state(run_id, session.scope_id, scope, budget)

        session.status = "running"
        session.emit("status", {"status": "running"})

        _drive(session, graph, cfg, state)
        _pump(session, graph, cfg)

        final = graph.get_state(cfg).values
        session.final_state = final
        session.status = final.get("status", "completed")

        repo.update_run(run_id, session.status, final.get("budget", budget),
                        final.get("abort_reason"))
        for f in final.get("findings", []):
            repo.insert_finding(run_id, f)

        # Cross-run learning is updated only after the report gate approves,
        # so a rejected report cannot poison it.
        if session.status == "completed":
            _record_patterns(final)

        session.emit("status", {
            "status": session.status,
            "abort_reason": final.get("abort_reason"),
            "budget": final.get("budget"),
        })
        session.emit("report", final.get("report", {}))
    except Exception as exc:  # noqa: BLE001
        session.status = "aborted"
        session.emit("error", {"error": f"{type(exc).__name__}: {exc}",
                               "traceback": traceback.format_exc()[-2000:]})
    finally:
        set_trace_sink(None)
        session.emit("done", {"status": session.status})


def _pump(session: RunSession, graph, cfg) -> None:
    """Drive the graph through every interrupt until it finishes."""
    guard = 0
    while True:
        snap = graph.get_state(cfg)
        if not snap.next:
            return
        payloads = []
        for task in snap.tasks:
            for intr in getattr(task, "interrupts", []) or []:
                if isinstance(intr.value, dict):
                    payloads.append(intr.value)
        if not payloads:
            return
        guard += 1
        if guard > 60:
            raise RuntimeError("interrupt pump exceeded 60 iterations")

        decision = session.await_resume(payloads[0])
        _drive(session, graph, cfg, Command(resume=decision))


def _drive(session: RunSession, graph, cfg, payload) -> None:
    """Stream the graph, translating each node's state delta into typed events
    as that node completes.

    DESIGN.md 14 specifies streaming here, and it is load-bearing for the UI:
    with graph.invoke() the plan, transcript and findings only surface in a
    burst at the next interrupt, so the live panels sit empty through the whole
    attack cycle - precisely the part of a run worth watching.
    """
    for chunk in graph.stream(payload, cfg, stream_mode="updates"):
        if not isinstance(chunk, dict):
            continue
        for node_name, update in chunk.items():
            if node_name == "__interrupt__" or not isinstance(update, dict):
                continue
            _emit_update(session, node_name, update)


def _emit_update(session: RunSession, node: str, update: dict) -> None:
    """Translate one node's delta into typed events.

    Only fields the node actually wrote are emitted. That is what stops the
    whole accumulated state being re-sent on every hop - findings used to
    arrive once per gate, so a two-finding run delivered four finding events.
    """
    if update.get("attack_plan"):
        session.emit("plan", {"attacks": update["attack_plan"]})
    if update.get("recon_profile"):
        session.emit("recon", update["recon_profile"])
    if update.get("current_attack_transcript"):
        # Emitted twice per turn by design: once when send_to_target appends the
        # probe/response pair, once when judge_outcome annotates it with the
        # verdict. Turns carry attack_id, so the client upserts rather than
        # appends. next_attack clears the transcript, which is falsy and so
        # emits nothing - the client keeps prior attacks grouped by attack_id.
        session.emit("transcript", {"node": node, "turns": update["current_attack_transcript"]})
    if "current_attack_idx" in update:
        session.emit("cursor", {"attack_idx": update["current_attack_idx"]})
    if node == "decide_router" and update.get("_route"):
        # Surfacing the router's choice makes the control flow visible: this is
        # the graph deciding to escalate/pivot/advance, not a hidden while-loop.
        session.emit("route", {
            "route": update["_route"],
            "escalation": update.get("pending_escalation") or {},
        })
    for call in update.get("interceptor_log") or []:
        session.emit("intercept", call)
    for f in update.get("findings") or []:
        # verify emits the raw finding, score re-emits it enriched with severity
        # and mitigation. The client upserts on finding_id, so a finding appears
        # as soon as it is verified and gains its score a moment later.
        session.emit("finding", f)
    if update.get("budget"):
        session.emit("budget", update["budget"])
    if update.get("status") in ("aborted", "completed"):
        session.emit("status", {
            "status": update["status"],
            "abort_reason": update.get("abort_reason"),
        })


def _on_trace(session: RunSession, entry: dict) -> None:
    session.emit("trace", entry)
    after = entry.get("budget_after")
    if after:
        session.emit("budget", after)
        if after.get("warned"):
            session.emit("budget_warning", after)


def _record_patterns(final: dict) -> None:
    target_type = final.get("scope", {}).get("target_id", "unknown")
    succeeded = {
        f.get("attack_category") for f in final.get("findings", []) if f.get("confirmed")
    }
    for attack in final.get("attack_plan", []):
        cat = attack.get("category")
        if cat:
            repo.record_pattern_outcome(cat, target_type, cat in succeeded)


def sse_format(event: dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event, default=str)}\n\n"


manager = RunManager()
