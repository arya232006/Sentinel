"""Per-model pricing, in USD per million tokens.

Cache reads bill at ~0.1x the input rate; 5-minute cache writes at ~1.25x.
Billing cached tokens at the plain input rate would overstate cost by roughly
10x on a run with a stable system prompt, which is exactly our shape.
"""

from __future__ import annotations

from typing import Any

CACHE_READ_MULTIPLIER = 0.10
CACHE_WRITE_MULTIPLIER = 1.25

# (input $/MTok, output $/MTok)
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-fable-5": (10.00, 50.00),
}

_FALLBACK_PRICE = (5.00, 25.00)


def rates(model: str) -> tuple[float, float]:
    return PRICING.get(model, _FALLBACK_PRICE)


def cost_from_usage(model: str, usage: Any) -> float:
    """Compute USD from a response usage object or dict.

    Total prompt size is input_tokens + cache_read + cache_creation; each of
    the three bills at a different rate.
    """
    in_rate, out_rate = rates(model)

    def _get(name: str) -> int:
        if usage is None:
            return 0
        if isinstance(usage, dict):
            return int(usage.get(name) or 0)
        return int(getattr(usage, name, 0) or 0)

    plain_in = _get("input_tokens")
    cache_read = _get("cache_read_input_tokens")
    cache_write = _get("cache_creation_input_tokens")
    out = _get("output_tokens")

    usd = (
        plain_in * in_rate
        + cache_read * in_rate * CACHE_READ_MULTIPLIER
        + cache_write * in_rate * CACHE_WRITE_MULTIPLIER
        + out * out_rate
    ) / 1_000_000
    return round(usd, 8)


def estimate_cost(model: str, input_tokens: int, expected_output: int) -> float:
    """Pre-flight estimate. Used to refuse a call that would breach the cap
    before it is made, rather than discovering the breach afterwards."""
    in_rate, out_rate = rates(model)
    return round((input_tokens * in_rate + expected_output * out_rate) / 1_000_000, 8)


def token_totals(usage: Any) -> tuple[int, int]:
    """(all input tokens incl. cache, output tokens)."""

    def _get(name: str) -> int:
        if usage is None:
            return 0
        if isinstance(usage, dict):
            return int(usage.get(name) or 0)
        return int(getattr(usage, name, 0) or 0)

    total_in = (
        _get("input_tokens")
        + _get("cache_read_input_tokens")
        + _get("cache_creation_input_tokens")
    )
    return total_in, _get("output_tokens")
