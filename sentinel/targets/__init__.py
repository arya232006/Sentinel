"""The three deliberately vulnerable target agents."""

from __future__ import annotations

from sentinel.targets.base import TargetAgent, TargetResponse
from sentinel.targets.rag_agent import RagAgent
from sentinel.targets.support_bot import SupportBot
from sentinel.targets.tool_agent import ToolAgent

_INSTANCES: dict[str, TargetAgent] = {}


def get_target(target_id: str) -> TargetAgent:
    if target_id not in _INSTANCES:
        cls = {
            "support_bot": SupportBot,
            "tool_agent": ToolAgent,
            "rag_agent": RagAgent,
        }.get(target_id)
        if cls is None:
            raise KeyError(f"unknown target '{target_id}'")
        _INSTANCES[target_id] = cls()
    return _INSTANCES[target_id]


TARGET_IDS = ("support_bot", "tool_agent", "rag_agent")

__all__ = ["TargetAgent", "TargetResponse", "get_target", "TARGET_IDS"]
