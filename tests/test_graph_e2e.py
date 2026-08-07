"""End-to-end graph behaviour on the deterministic offline pipeline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from sentinel import config
from sentinel.graph.build import build_graph
from sentinel.graph.runner import run_offline
from sentinel.llm import budget as B
from sentinel.state import initial_state


def test_support_bot_run_produces_confirmed_finding(make_scope):
    s = make_scope("support_bot", ["authority_impersonation", "multiturn_erosion"])
    final = run_offline(s.model_dump(), s.scope_id)

    assert final["status"] == "completed"
    assert final["attack_plan"], "planner produced no attacks"
    assert final["findings"], "no findings produced"
    confirmed = [f for f in final["findings"] if f["confirmed"]]
    assert confirmed, "no confirmed finding"
    f = confirmed[0]
    assert f["severity"] > 0
    assert f["reproducibility"] >= config.VERIFY_MAJORITY / config.VERIFY_RERUNS
    assert f["poc_log"], "no PoC log"
    assert f["mitigation"], "no mitigation"


def test_minimization_shortens_the_trigger(make_scope):
    s = make_scope("support_bot", ["authority_impersonation"])
    final = run_offline(s.model_dump(), s.scope_id)
    f = next(f for f in final["findings"] if f["confirmed"])
    assert len(f["minimized_prompt"]) < len(f["trigger_probe"])
    assert f["minimization_steps"] <= config.MAX_MINIMIZATION_STEPS


def test_tool_finding_requires_interceptor_corroboration(make_scope):
    s = make_scope("tool_agent", ["tool_parameter_hijacking"])
    final = run_offline(s.model_dump(), s.scope_id)
    f = final["findings"][0]
    assert f["attack_category"] == "tool_parameter_hijacking"
    assert f["corroborated_by_interceptor"] is True
    assert f["confirmed"] is True
    assert f["corroborating_call"]["tool_name"] == "refund"


def test_tool_finding_downgraded_without_corroboration(monkeypatch, make_scope):
    """Judge says succeeded but no flagged call -> text-only, not confirmed."""
    import sentinel.graph.nodes.verify as verify_mod

    monkeypatch.setattr(
        verify_mod, "has_corroborating_call", lambda log, aid=None: (False, None)
    )
    s = make_scope("tool_agent", ["tool_parameter_hijacking"])
    final = run_offline(s.model_dump(), s.scope_id)
    f = final["findings"][0]
    assert f["confirmed"] is False
    assert f["status"] == "text_only_unconfirmed"
    assert "unconfirmed" in f["confirmation_note"]


def test_plan_never_exceeds_authorized_categories(make_scope):
    s = make_scope("support_bot", ["multiturn_erosion"])
    final = run_offline(s.model_dump(), s.scope_id)
    for a in final["attack_plan"]:
        assert a["category"] == "multiturn_erosion"


def test_rejected_run_start_gate_aborts(make_scope):
    s = make_scope("support_bot", ["multiturn_erosion"])
    final = run_offline(s.model_dump(), s.scope_id, approvals={"run_start": False})
    assert final["status"] == "aborted"
    assert "rejected" in final["abort_reason"]
    assert not final["findings"]


def test_rejected_report_gate_aborts(make_scope):
    s = make_scope("support_bot", ["multiturn_erosion"])
    final = run_offline(s.model_dump(), s.scope_id, approvals={"report_finalization": False})
    assert final["status"] == "aborted"


def test_expired_scope_aborts_before_recon(make_scope, fresh_db):
    from sentinel.scope import ScopeDraft, create_scope

    s = create_scope(
        ScopeDraft(
            target_id="support_bot", target_endpoint="inproc://support_bot",
            allowed_attack_categories=["multiturn_erosion"], authorizer="t",
            expiry_timestamp=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
    )
    final = run_offline(s.model_dump(), s.scope_id)
    assert final["status"] == "aborted"
    assert "expired" in final["abort_reason"]


def test_interrupts_fire_at_three_points(make_scope):
    """The graph must pause for a human at run start, and again at report."""
    s = make_scope("support_bot", ["multiturn_erosion"])
    graph = build_graph(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "t-interrupt"}, "recursion_limit": 200}
    state = initial_state("t-interrupt", s.scope_id, s.model_dump(), B.new_budget())

    graph.invoke(state, cfg)
    snap = graph.get_state(cfg)
    gates_seen = []
    for task in snap.tasks:
        for intr in getattr(task, "interrupts", []) or []:
            gates_seen.append(intr.value.get("gate"))
    assert "run_start" in gates_seen, "run start gate did not interrupt"

    # Resume through to the end, collecting gates.
    guard = 0
    while snap.next and guard < 30:
        guard += 1
        graph.invoke(Command(resume=True), cfg)
        snap = graph.get_state(cfg)
        for task in snap.tasks:
            for intr in getattr(task, "interrupts", []) or []:
                gates_seen.append(intr.value.get("gate"))
    assert "report_finalization" in gates_seen, "report gate did not interrupt"


def test_checkpoint_survives_a_new_graph_object(make_scope):
    """A run must be resumable after the process rebuilding the graph."""
    s = make_scope("support_bot", ["multiturn_erosion"])
    saver = InMemorySaver()
    cfg = {"configurable": {"thread_id": "t-resume"}, "recursion_limit": 200}
    state = initial_state("t-resume", s.scope_id, s.model_dump(), B.new_budget())

    g1 = build_graph(checkpointer=saver)
    g1.invoke(state, cfg)
    assert g1.get_state(cfg).next  # parked at the run-start interrupt

    # Rebuild the graph from scratch against the same checkpointer.
    g2 = build_graph(checkpointer=saver)
    resumed = g2.get_state(cfg)
    assert resumed.values["scope_id"] == s.scope_id
    g2.invoke(Command(resume=True), cfg)
    assert g2.get_state(cfg).values["recon_profile"], "did not resume into recon"


def test_trace_log_records_every_llm_call(make_scope, fresh_db):
    s = make_scope("support_bot", ["multiturn_erosion"])
    final = run_offline(s.model_dump(), s.scope_id)
    rows = fresh_db.list_trace(final["run_id"])
    assert len(rows) == final["budget"]["calls"], "trace count != accounted calls"
    for r in rows:
        assert r["node"] and r["model"] and r["ts"]
