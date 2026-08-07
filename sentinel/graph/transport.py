"""HTTP transport to the target endpoint.

Deliberately contains no LLM call. Retry with backoff, malformed-response
detection, and a hard retry ceiling: past the ceiling an attempt is marked
inconclusive rather than dropped silently.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from sentinel import config


class TargetUnreachable(Exception):
    pass


def call_target(
    endpoint: str,
    target_id: str,
    messages: list[dict[str, Any]],
    *,
    session_id: str = "",
    attack_id: str | None = None,
    turn: int | None = None,
) -> dict[str, Any]:
    """POST to the target. Returns a dict with text/tool_calls/retrieved_docs.

    On exhaustion of retries, returns {"inconclusive": True, ...} rather than
    raising, so one flaky target cannot abort an otherwise healthy run.
    """
    # In-process shortcut: "inproc://<target_id>" calls the target directly,
    # bypassing HTTP. Used by the offline pipeline and tests, and by a
    # single-process demo. The graph is otherwise identical either way.
    if endpoint.startswith("inproc://"):
        return _call_inproc(endpoint, messages, session_id, attack_id, turn)

    payload = {
        "messages": messages,
        "session_id": session_id,
        "attack_id": attack_id,
        "turn": turn,
    }
    last_error = ""
    delay = 0.5

    for attempt in range(config.TARGET_HTTP_RETRIES):
        try:
            with httpx.Client(timeout=config.TARGET_HTTP_TIMEOUT) as client:
                r = client.post(f"{endpoint.rstrip('/')}", json=payload)

            if r.status_code == 429 or r.status_code >= 500:
                last_error = f"HTTP {r.status_code}"
                time.sleep(delay)
                delay *= 2
                continue
            if r.status_code >= 400:
                return {
                    "text": "",
                    "tool_calls": [],
                    "retrieved_docs": [],
                    "inconclusive": True,
                    "error": f"HTTP {r.status_code}: {r.text[:200]}",
                }

            data = r.json()
            if not isinstance(data, dict) or "text" not in data:
                last_error = "malformed response: no 'text' field"
                time.sleep(delay)
                delay *= 2
                continue
            if not (data.get("text") or "").strip() and not data.get("tool_calls"):
                last_error = "empty response body"
                time.sleep(delay)
                delay *= 2
                continue

            data.setdefault("tool_calls", [])
            data.setdefault("retrieved_docs", [])
            data["inconclusive"] = False
            return data

        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(delay)
            delay *= 2

    # Hard ceiling reached. Mark inconclusive; never drop silently.
    return {
        "text": "",
        "tool_calls": [],
        "retrieved_docs": [],
        "inconclusive": True,
        "error": f"retry ceiling ({config.TARGET_HTTP_RETRIES}) reached: {last_error}",
    }


def _call_inproc(
    endpoint: str,
    messages: list[dict[str, Any]],
    session_id: str,
    attack_id: str | None,
    turn: int | None,
) -> dict[str, Any]:
    from sentinel.targets import get_target

    target_id = endpoint[len("inproc://") :]
    try:
        target = get_target(target_id)
    except KeyError as exc:
        return {
            "text": "", "tool_calls": [], "retrieved_docs": [],
            "inconclusive": True, "error": str(exc),
        }
    # ToolAgent accepts attack_id/turn for interception attribution.
    kwargs: dict[str, Any] = {"session_id": session_id}
    if target_id == "tool_agent":
        kwargs.update(attack_id=attack_id, turn=turn)
    resp = target.chat(messages, **kwargs)
    data = resp.to_dict()
    data["inconclusive"] = bool(data.get("error"))
    return data
