"""Control nodes: scope guards, cursor advance, terminal nodes.

validate_scope is re-checked at every phase transition, not once at the start.
A failure routes to the aborted terminal node with abort_reason set.
"""

from __future__ import annotations

from sentinel.scope.service import validate_scope
from sentinel.state import SentinelState


def check_scope_node(state: SentinelState) -> dict:
    """Entry guard. Also re-run before recon/planner/verify/score via the
    per-phase checks below; this node covers run start."""
    result = validate_scope(state["scope_id"])
    if not result.ok:
        return {"status": "aborted", "abort_reason": f"scope invalid: {result.reason}"}
    return {"status": "running"}


def _guard(state: SentinelState, action: str) -> dict | None:
    result = validate_scope(state["scope_id"], action)
    if not result.ok:
        return {
            "status": "aborted",
            "abort_reason": f"scope check failed before {action}: {result.reason}",
        }
    return None


def phase_guard_recon(state: SentinelState) -> dict:
    return _guard(state, "recon") or {}


def phase_guard_planner(state: SentinelState) -> dict:
    return _guard(state, "planning") or {}


def phase_guard_verify(state: SentinelState) -> dict:
    return _guard(state, "verify") or {}


def phase_guard_score(state: SentinelState) -> dict:
    return _guard(state, "scoring") or {}


def craft_scope_guard(state: SentinelState) -> dict:
    """Checked at each craft_probe entry: the specific attack category must be
    authorized. This is the per-attack scope enforcement the spec requires."""
    idx = state["current_attack_idx"]
    plan = state["attack_plan"]
    if idx >= len(plan):
        return {}
    category = plan[idx].get("category", "")
    result = validate_scope(state["scope_id"], category)
    if not result.ok:
        return {
            "status": "aborted",
            "abort_reason": f"attack category '{category}' failed scope check: {result.reason}",
        }
    return {}


def next_attack_node(state: SentinelState) -> dict:
    """Advance the cursor, reset the per-attack counters."""
    return {
        "current_attack_idx": state["current_attack_idx"] + 1,
        "current_attack_turn": 0,
        "current_attack_transcript": [],
        "last_verdict": {},
        "_pending_probe": None,
    }


def aborted_node(state: SentinelState) -> dict:
    return {"status": "aborted"}


def completed_node(state: SentinelState) -> dict:
    # status is set to completed by the report gate on approval.
    if state.get("status") != "aborted":
        return {"status": "completed"}
    return {}
