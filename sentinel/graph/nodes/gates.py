"""The three human-in-the-loop interrupt points, and decide_next as a node.

LangGraph interrupt() must be called from a node, not a conditional edge - the
edge function is not replayed on resume, the node is. So:

  - run_start_gate, escalation_gate, report_gate are real nodes that call
    interrupt() and act on the resumed value.
  - decide_router is a node that runs pure decide_next() and stores the route
    in state, so the routing decision is checkpointed and traced.

This resolves DESIGN.md concern 1: the spec placed the escalation interrupt
inside the conditional router, which LangGraph cannot do.
"""

from __future__ import annotations

from langgraph.types import interrupt

from sentinel import config
from sentinel.graph import routers
from sentinel.state import SentinelState


def decide_router_node(state: SentinelState) -> dict:
    """Runs the pure router, records the choice. Also advances the attack
    cursor when the route is next_attack, and stages escalation metadata."""
    route = routers.decide_next(state)
    out: dict = {"_route": route}

    if route == routers.ESCALATION_GATE:
        idx = state["current_attack_idx"]
        plan = state["attack_plan"]
        cat = plan[idx].get("category", "") if idx < len(plan) else ""
        out["pending_escalation"] = {
            "category": cat,
            "attack_idx": idx,
            "verdict": state.get("last_verdict", {}),
        }
    return out


# --------------------------------------------------------------- gate 1 ---
def run_start_gate_node(state: SentinelState) -> dict:
    """After check_scope passes, before recon. Surfaces target + categories,
    requires explicit confirmation."""
    decision = interrupt(
        {
            "gate": "run_start",
            "prompt": "Confirm this authorized run before recon begins.",
            "target_id": state["scope"].get("target_id"),
            "target_endpoint": state["scope"].get("target_endpoint"),
            "allowed_categories": state["scope"].get("allowed_attack_categories"),
            "authorizer": state["scope"].get("authorizer"),
        }
    )
    approved = _approved(decision)
    if not approved:
        return {"status": "aborted", "abort_reason": "run rejected at start gate"}
    return {"status": "running"}


# --------------------------------------------------------------- gate 2 ---
def escalation_gate_node(state: SentinelState) -> dict:
    """First escalation into a high-severity category in this run. Approve ->
    continue the attack; reject -> advance to the next attack."""
    pending = state.get("pending_escalation", {})
    category = pending.get("category", "")

    decision = interrupt(
        {
            "gate": "severity_escalation",
            "prompt": f"Approve escalation into high-severity category '{category}'?",
            "category": category,
            "verdict": pending.get("verdict", {}),
            "budget": {
                "usd_spent": state["budget"]["usd_spent"],
                "usd_cap": state["budget"]["usd_cap"],
            },
        }
    )
    approved = _approved(decision)
    approved_list = list(state.get("escalation_approved", []))

    if approved:
        if category and category not in approved_list:
            approved_list.append(category)
        return {
            "escalation_approved": approved_list,
            "pending_escalation": {},
            "_route": routers.ESCALATE,
        }
    # Rejected: skip this attack.
    return {
        "pending_escalation": {},
        "_route": routers.NEXT_ATTACK,
    }


# --------------------------------------------------------------- gate 3 ---
def report_gate_node(state: SentinelState) -> dict:
    """Before the report is marked shareable. Human reviews findings, e.g. to
    redact anything that surfaced real rather than simulated data."""
    findings = state.get("findings", [])
    decision = interrupt(
        {
            "gate": "report_finalization",
            "prompt": "Review findings before the report is marked shareable.",
            "finding_count": len(findings),
            "findings_preview": [
                {
                    "finding_id": f.get("finding_id"),
                    "category": f.get("attack_category"),
                    "severity": f.get("severity"),
                    "confirmed": f.get("confirmed"),
                    "minimized_prompt": (f.get("minimized_prompt") or "")[:200],
                }
                for f in findings
            ],
        }
    )
    approved = _approved(decision)
    if not approved:
        return {"status": "aborted", "abort_reason": "report rejected at finalization gate"}
    return {"status": "completed"}


def _approved(decision) -> bool:
    """Interpret a resume value. Accepts bool, or a dict with an approve/decision
    field, defaulting to rejection on anything ambiguous - fail closed."""
    if isinstance(decision, bool):
        return decision
    if isinstance(decision, dict):
        if "approved" in decision:
            return bool(decision["approved"])
        if "decision" in decision:
            return str(decision["decision"]).lower() in ("approve", "approved", "yes", "true")
    if isinstance(decision, str):
        return decision.lower() in ("approve", "approved", "yes", "true")
    return False
