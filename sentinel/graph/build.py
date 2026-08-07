"""LangGraph state graph assembly.

Topology (DESIGN.md section 6). Interrupts live in dedicated gate nodes, never
in conditional edges - the fix for concern 1. Scope is re-validated at every
phase transition via wrapped guards. Checkpointing is automatic per node.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from sentinel import config
from sentinel.graph import routers
from sentinel.graph.nodes import control, gates
from sentinel.graph.nodes.craft_probe import craft_probe_node
from sentinel.graph.nodes.judge import judge_node
from sentinel.graph.nodes.planner import planner_node
from sentinel.graph.nodes.recon import recon_node
from sentinel.graph.nodes.score import score_node
from sentinel.graph.nodes.send_to_target import send_to_target_node
from sentinel.graph.nodes.verify import verify_node
from sentinel.scope.service import validate_scope
from sentinel.state import SentinelState


def _guarded(fn, action: str):
    """Re-validate scope at a phase transition before running the phase node."""

    def wrapped(state: SentinelState) -> dict:
        result = validate_scope(state["scope_id"], action)
        if not result.ok:
            return {
                "status": "aborted",
                "abort_reason": f"scope check failed before {action}: {result.reason}",
            }
        return fn(state)

    return wrapped


def _aborted(state: SentinelState) -> str:
    return "aborted" if state.get("status") == "aborted" else "continue"


def build_graph(checkpointer=None):
    g = StateGraph(SentinelState)

    # --- nodes -----------------------------------------------------------
    g.add_node("check_scope", control.check_scope_node)
    g.add_node("run_start_gate", gates.run_start_gate_node)
    g.add_node("recon", _guarded(recon_node, "recon"))
    g.add_node("plan_attacks", _guarded(planner_node, "planning"))
    g.add_node("craft_probe", _guarded_craft())
    g.add_node("send_to_target", send_to_target_node)
    g.add_node("judge_outcome", judge_node)
    g.add_node("decide_router", gates.decide_router_node)
    g.add_node("escalation_gate", gates.escalation_gate_node)
    g.add_node("next_attack", control.next_attack_node)
    g.add_node("verify", _guarded(verify_node, "verify"))
    g.add_node("score", _guarded(score_node, "scoring"))
    g.add_node("report_gate", gates.report_gate_node)
    g.add_node("aborted", control.aborted_node)
    g.add_node("completed", control.completed_node)

    # --- edges -----------------------------------------------------------
    g.add_edge(START, "check_scope")
    g.add_conditional_edges(
        "check_scope", _aborted, {"aborted": "aborted", "continue": "run_start_gate"}
    )
    g.add_conditional_edges(
        "run_start_gate", _aborted, {"aborted": "aborted", "continue": "recon"}
    )
    g.add_conditional_edges(
        "recon", _aborted, {"aborted": "aborted", "continue": "plan_attacks"}
    )
    g.add_conditional_edges(
        "plan_attacks",
        _after_plan,
        {"aborted": "aborted", "attack": "craft_probe", "verify": "verify"},
    )

    # execution cycle
    g.add_conditional_edges(
        "craft_probe",
        _aborted,
        {"aborted": "aborted", "continue": "send_to_target"},
    )
    g.add_edge("send_to_target", "judge_outcome")
    g.add_edge("judge_outcome", "decide_router")
    g.add_conditional_edges(
        "decide_router",
        routers.route_after_decide,
        {
            routers.ESCALATE: "craft_probe",
            routers.PIVOT: "craft_probe",
            routers.NEXT_ATTACK: "next_attack",
            routers.VERIFY: "verify",
            routers.ESCALATION_GATE: "escalation_gate",
            routers.ABORT: "aborted",
        },
    )
    g.add_conditional_edges(
        "escalation_gate",
        _after_gate,
        {"escalate": "craft_probe", "next_attack": "next_attack", "aborted": "aborted"},
    )
    g.add_conditional_edges(
        "next_attack",
        _after_next_attack,
        {"attack": "craft_probe", "verify": "verify"},
    )

    # tail
    g.add_conditional_edges(
        "verify", _aborted, {"aborted": "aborted", "continue": "score"}
    )
    g.add_conditional_edges(
        "score", _aborted, {"aborted": "aborted", "continue": "report_gate"}
    )
    g.add_conditional_edges(
        "report_gate", _aborted, {"aborted": "aborted", "continue": "completed"}
    )
    g.add_edge("completed", END)
    g.add_edge("aborted", END)

    return g.compile(checkpointer=checkpointer)


def _guarded_craft():
    """craft_probe entry re-checks the specific attack category against scope."""
    from sentinel.graph.nodes.craft_probe import craft_probe_node as _craft

    def wrapped(state: SentinelState) -> dict:
        idx = state["current_attack_idx"]
        plan = state["attack_plan"]
        if idx < len(plan):
            category = plan[idx].get("category", "")
            result = validate_scope(state["scope_id"], category)
            if not result.ok:
                return {
                    "status": "aborted",
                    "abort_reason": f"category '{category}' failed scope check: {result.reason}",
                }
        return _craft(state)

    return wrapped


def _after_plan(state: SentinelState) -> str:
    if state.get("status") == "aborted":
        return "aborted"
    if not state.get("attack_plan"):
        # No plannable attacks; skip straight to verify (which yields no findings).
        return "verify"
    return "attack"


def _after_gate(state: SentinelState) -> str:
    if state.get("status") == "aborted":
        return "aborted"
    return state.get("_route", routers.NEXT_ATTACK)


def _after_next_attack(state: SentinelState) -> str:
    idx = state["current_attack_idx"]
    plan = state["attack_plan"]
    if idx >= min(len(plan), config.MAX_ATTACKS_PER_RUN):
        return "verify"
    return "attack"
