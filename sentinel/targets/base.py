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
        self, messages: list[dict[str, Any]], session_id: str
    ) -> TargetResponse: ...
