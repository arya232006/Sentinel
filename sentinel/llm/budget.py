"""Cost accounting with a soft warning and a hard cap.

The cap is enforced pre-flight: a call whose estimated cost would breach it is
refused before it is made. The warning fires once and is advisory.
"""

from __future__ import annotations

from typing import Any, Callable

from sentinel.config import BudgetProfile, profile


class BudgetExceeded(Exception):
    """Raised when a call would breach the hard cap. Routes the graph to aborted."""

    def __init__(self, spent: float, cap: float, estimate: float):
        self.spent, self.cap, self.estimate = spent, cap, estimate
        super().__init__(
            f"budget cap ${cap:.2f} would be breached: "
            f"spent ${spent:.4f} + estimated ${estimate:.4f}"
        )


def new_budget(prof: BudgetProfile | None = None) -> dict[str, Any]:
    p = prof or profile()
    return {
        "usd_spent": 0.0,
        "usd_cap": p.usd_cap,
        "usd_warn": p.usd_warn,
        "warned": False,
        "profile": p.name,
        "tokens_in": 0,
        "tokens_out": 0,
        "calls": 0,
    }


def check(budget: dict[str, Any], estimate: float) -> None:
    """Pre-flight gate. Raises BudgetExceeded rather than returning a flag so
    a caller cannot forget to check the result."""
    if budget["usd_spent"] + estimate > budget["usd_cap"]:
        raise BudgetExceeded(budget["usd_spent"], budget["usd_cap"], estimate)


def record(
    budget: dict[str, Any],
    usd: float,
    tokens_in: int,
    tokens_out: int,
    on_warn: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    budget["usd_spent"] = round(budget["usd_spent"] + usd, 8)
    budget["tokens_in"] += tokens_in
    budget["tokens_out"] += tokens_out
    budget["calls"] += 1

    if not budget["warned"] and budget["usd_spent"] >= budget["usd_warn"]:
        budget["warned"] = True
        if on_warn:
            on_warn(budget)
    return budget


def remaining(budget: dict[str, Any]) -> float:
    return max(0.0, budget["usd_cap"] - budget["usd_spent"])


def is_exhausted(budget: dict[str, Any]) -> bool:
    return budget["usd_spent"] >= budget["usd_cap"]
