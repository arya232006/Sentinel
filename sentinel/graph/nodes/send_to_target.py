"""send_to_target node: plain HTTP call to the target. NO LLM call here.

Appends the probe/response pair to the current attack transcript and folds any
intercepted tool calls into the interceptor log, tagged with the attack id and
turn that produced them.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sentinel.graph.transport import call_target
from sentinel.state import SentinelState


def send_to_target_node(state: SentinelState) -> dict:
    pending = state.get("_pending_probe")
    transcript = state.get("current_attack_transcript", [])
    turn = state["current_attack_turn"]

    if not pending:
        # craft_probe refused; the refusal turn was already appended there.
        return {"_pending_probe": None}

    endpoint = state["scope"].get("target_endpoint", "")
    target_id = state["scope"].get("target_id", "")
    run_id = state["run_id"]

    # Rebuild the full conversation the target should see for this attack.
    messages: list[dict] = []
    for t in transcript:
        if t.get("probe"):
            messages.append({"role": "user", "content": t["probe"]})
            messages.append({"role": "assistant", "content": t.get("response", "")})
    messages.append({"role": "user", "content": pending["probe"]})

    resp = call_target(
        endpoint,
        target_id,
        messages,
        session_id=f"{run_id}-{pending['attack_id']}",
        attack_id=pending["attack_id"],
        turn=turn,
        run_id=run_id,
        budget=state.get("budget"),
    )

    tool_calls = resp.get("tool_calls", []) or []
    intercepted = []
    for c in tool_calls:
        entry = dict(c)
        entry.setdefault("attack_id", pending["attack_id"])
        entry.setdefault("turn", turn)
        intercepted.append(entry)

    new_turn = {
        "probe": pending["probe"],
        "angle": pending.get("angle", ""),
        "withheld": pending.get("withheld", ""),
        "response": resp.get("text", ""),
        "tool_calls": tool_calls,
        "retrieved_docs": resp.get("retrieved_docs", []),
        "inconclusive": resp.get("inconclusive", False),
        "error": resp.get("error"),
        "attack_id": pending["attack_id"],
        "category": pending["category"],
        "turn": turn,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    out: dict = {
        "current_attack_transcript": transcript + [new_turn],
        "_pending_probe": None,
    }
    if intercepted:
        out["interceptor_log"] = intercepted
    return out
