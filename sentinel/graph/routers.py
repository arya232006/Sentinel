"""decide_next: pure routing logic over the last verdict and the counters.

No LLM call. Hard caps are checked before anything else, which is what makes
"no unbounded loops anywhere" true by construction. Returns a route string that
build.py maps to the next node.
"""

from __future__ import annotations

from sentinel import config
from sentinel.llm import budget as budget_mod
from sentinel.state import SentinelState

# Route constants.
ESCALATE = "escalate"        # loop craft_probe, same attack, more aggressive
PIVOT = "pivot"              # loop craft_probe, different angle/category
NEXT_ATTACK = "next_attack"  # advance the cursor
VERIFY = "verify"            # exit the cycle to verification
ESCALATION_GATE = "escalation_gate"  # human approval before high-severity escalation
ABORT = "abort"              # budget exhausted


def decide_next(state: SentinelState) -> str:
    budget = state["budget"]
    turn = state["current_attack_turn"]
    idx = state["current_attack_idx"]
    plan = state["attack_plan"]
    verdict = state.get("last_verdict", {}) or {}
    classification = verdict.get("classification", "failed")

    # --- hard caps first -------------------------------------------------
    if budget_mod.is_exhausted(budget):
        return ABORT

    attacks_remaining = idx < min(len(plan), config.MAX_ATTACKS_PER_RUN)
    if not attacks_remaining:
        return VERIFY

    if turn >= config.PER_ATTACK_TURN_CAP:
        return NEXT_ATTACK

    # --- verdict-driven routing -----------------------------------------
    if classification == "succeeded":
        # The candidate is already captured in judge_node. Advance to the next
        # attack rather than exiting the whole cycle on the first success, so a
        # run surfaces findings across the plan. verify_node processes all
        # captured candidates together once the cycle ends (plan exhausted or a
        # cap trips). This is the one place the build refines DESIGN.md 6: a
        # single success must not end the audit.
        return NEXT_ATTACK

    if classification == "partial":
        # Escalating into a high-severity category for the first time in this
        # run requires human approval. The gate node fires at most once per
        # category because it consults escalation_approved.
        next_cat = _next_category(plan, idx)
        if (
            next_cat in config.HIGH_SEVERITY_CATEGORIES
            and next_cat not in state.get("escalation_approved", [])
        ):
            return ESCALATION_GATE
        return ESCALATE

    if classification == "refused_differently":
        return PIVOT

    # failed
    return ESCALATE if turn < config.PER_ATTACK_TURN_CAP else NEXT_ATTACK


def _next_category(plan: list[dict], idx: int) -> str:
    if idx < len(plan):
        return plan[idx].get("category", "")
    return ""


def route_after_decide(state: SentinelState) -> str:
    """LangGraph conditional-edge function. Reads the route decide_next stored
    in state so the decision is visible in the checkpoint and the trace."""
    return state.get("_route", NEXT_ATTACK)
