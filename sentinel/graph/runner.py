"""Drives a compiled graph: creates the run, streams updates, handles the three
interrupt gates via resume decisions.

The auto_approve helper drives all three gates without a human, for the offline
pipeline, tests, and demo rehearsal. The API layer (phase 12) replaces it with
real /resume calls.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from sentinel import config
from sentinel.graph.build import build_graph
from sentinel.llm import budget as budget_mod
from sentinel.state import initial_state
from sentinel.store import repo


def new_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"


def run_offline(
    scope: dict[str, Any],
    scope_id: str,
    *,
    run_id: str | None = None,
    approvals: dict[str, bool] | None = None,
    on_update: Callable[[str, dict], None] | None = None,
    checkpointer=None,
) -> dict[str, Any]:
    """Run a graph to completion, auto-resolving the three gates.

    `approvals` maps gate name -> bool (default all True). `on_update` receives
    (node_name, state_delta) for each step, for wiring to an event sink.
    """
    run_id = run_id or new_run_id()
    approvals = {**{"run_start": True, "severity_escalation": True,
                    "report_finalization": True}, **(approvals or {})}

    graph = build_graph(checkpointer=checkpointer or InMemorySaver())
    cfg = {"configurable": {"thread_id": run_id}, "recursion_limit": 200}

    budget = budget_mod.new_budget()
    repo.insert_run(run_id, scope_id, budget)
    state = initial_state(run_id, scope_id, scope, budget)

    result = graph.invoke(state, cfg)
    result = _drive_interrupts(graph, cfg, result, approvals, on_update)

    final = graph.get_state(cfg).values
    repo.update_run(
        run_id,
        final.get("status", "completed"),
        final.get("budget", budget),
        final.get("abort_reason"),
    )
    for f in final.get("findings", []):
        repo.insert_finding(run_id, f)
    return final


def _drive_interrupts(graph, cfg, result, approvals, on_update):
    """Resume through every interrupt until the graph finishes."""
    guard = 0
    while True:
        state = graph.get_state(cfg)
        if not state.next:
            break  # graph is done
        interrupts = _pending_interrupts(state)
        if not interrupts:
            break
        guard += 1
        if guard > 50:
            raise RuntimeError("interrupt loop exceeded 50 iterations")

        payload = interrupts[0]
        gate = payload.get("gate", "")
        decision = approvals.get(gate, True)
        if on_update:
            on_update("interrupt", {"gate": gate, "decision": decision, "payload": payload})
        result = graph.invoke(Command(resume=decision), cfg)
    return result


def _pending_interrupts(state) -> list[dict]:
    out = []
    for task in state.tasks:
        for intr in getattr(task, "interrupts", []) or []:
            val = getattr(intr, "value", None)
            if isinstance(val, dict):
                out.append(val)
    return out
