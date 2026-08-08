"""Target agent protocol.

All targets speak the same shape so `send_to_target` is a plain HTTP call and
the graph would work unchanged against a third-party endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class TargetResponse:
    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    retrieved_docs: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "tool_calls": self.tool_calls,
            "retrieved_docs": self.retrieved_docs,
            "error": self.error,
        }


class TargetAgent(Protocol):
    target_id: str

    def chat(
        self,
        messages: list[dict[str, Any]],
        session_id: str = "",
        *,
        system_suffix: str = "",
        model: str | None = None,
        run_id: str = "",
        budget: dict[str, Any] | None = None,
    ) -> TargetResponse: ...


def compose_system(base: str, suffix: str = "") -> str:
    """Base system prompt plus an optional appended block.

    The only caller that passes a suffix is fix-and-reverify, which appends a
    finding's own generated mitigation and replays the attack against the
    patched prompt. Appending rather than rewriting is deliberate: the delta
    between the two runs must be exactly the mitigation text and nothing else,
    or a BEFORE/AFTER comparison proves nothing.
    """
    if not suffix.strip():
        return base
    return f"{base.rstrip()}\n\n{suffix.strip()}\n"


def resolve_model(model: str | None) -> str:
    """Target model for this call: an explicit override, else the configured
    default. The override exists for the differential audit, which runs one
    harness against several models."""
    from sentinel import config

    return model or config.TARGET_MODEL


def temperature_for(model: str) -> float | None:
    """0.0 where the model accepts it, None where it does not.

    The targets want determinism, but Opus 5 rejects `temperature` outright, so
    a differential run that includes it must omit the parameter rather than
    fail. Reported in the differential output, because a model sampled without
    temperature=0 is not strictly comparable to one that was.
    """
    from sentinel import config

    return 0.0 if config.accepts_temperature(model) else None
