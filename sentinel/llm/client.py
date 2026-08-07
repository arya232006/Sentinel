"""traced_call() - the single chokepoint for every Anthropic API call.

This is the only module in Sentinel that imports `anthropic`. Every node calls
through here, which is what makes "every Claude call is logged" a structural
guarantee rather than a matter of discipline.

Responsibilities, in order:
  1. pre-flight token count
  2. hard budget check (raises before the call is made)
  3. the call itself
  4. refusal detection, before content is ever indexed
  5. cost computation from usage
  6. trace entry emission
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import anthropic
from pydantic import BaseModel

from sentinel import config
from sentinel.llm import budget as budget_mod
from sentinel.llm import pricing

# Nodes may register a sink so the UI trace panel updates during a node rather
# than after it.
_trace_sink: Callable[[dict], None] | None = None
_client: anthropic.Anthropic | None = None


def set_trace_sink(fn: Callable[[dict], None] | None) -> None:
    global _trace_sink
    _trace_sink = fn


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        key = config.api_key()
        if not key and not config.fake_llm():
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Either add it to .env, or run with "
                "SENTINEL_FAKE_LLM=1 for the deterministic offline pipeline."
            )
        _client = anthropic.Anthropic(api_key=key)
    return _client


@dataclass
class LLMResult:
    text: str = ""
    parsed: Any = None
    refused: bool = False
    refusal_category: str | None = None
    stop_reason: str | None = None
    model: str = ""
    usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    trace: dict[str, Any] = field(default_factory=dict)
    # Raw assistant content, needed by the tool-using target to read tool_use
    # blocks and to echo the assistant turn back on the next request.
    content_blocks: list[Any] = field(default_factory=list)

    def tool_uses(self) -> list[dict[str, Any]]:
        out = []
        for b in self.content_blocks:
            btype = getattr(b, "type", None) or (
                b.get("type") if isinstance(b, dict) else None
            )
            if btype != "tool_use":
                continue
            out.append(
                {
                    "id": getattr(b, "id", None) or b.get("id"),
                    "name": getattr(b, "name", None) or b.get("name"),
                    "input": getattr(b, "input", None) or b.get("input") or {},
                }
            )
        return out


def _extract_text(content: Any) -> str:
    out = []
    for block in content or []:
        btype = getattr(block, "type", None) or (
            block.get("type") if isinstance(block, dict) else None
        )
        if btype == "text":
            out.append(
                getattr(block, "text", None)
                or (block.get("text", "") if isinstance(block, dict) else "")
            )
    return "\n".join(out).strip()


def _system_blocks(system: str) -> list[dict[str, Any]]:
    """System prompts are stable for a whole run, so they are the largest
    reusable cache prefix we have. Opus 5's minimum cacheable prefix is 512
    tokens, so even the judge prompt qualifies."""
    return [
        {
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def _summarize_input(system: str, messages: list[dict]) -> dict[str, Any]:
    return {
        "system": system[:2000],
        "messages": [
            {
                "role": m.get("role"),
                "content": (
                    m.get("content")
                    if isinstance(m.get("content"), str)
                    else json.dumps(m.get("content"), default=str)
                )[:4000],
            }
            for m in messages
        ],
    }


def traced_call(
    *,
    node: str,
    model: str,
    system: str,
    messages: list[dict],
    max_tokens: int = 4096,
    effort: str | None = None,
    output_format: type[BaseModel] | None = None,
    tools: list[dict] | None = None,
    temperature: float | None = None,
    use_fallbacks: bool = False,
    run_id: str = "",
    budget: dict[str, Any] | None = None,
) -> LLMResult:
    """Make one Claude call, fully accounted for.

    `temperature` is only valid for the target harness (Haiku 4.5). Passing it
    with an Opus 5 model is a programming error and raises here rather than
    producing an opaque 400 from the API.
    """
    if (
        temperature is not None
        and model.startswith("claude-opus-5")
        and config.provider() == "anthropic"
    ):
        raise ValueError(
            f"{model} rejects `temperature` with a 400. Steer with prompting, or "
            f"use {config.TARGET_MODEL} where determinism is required."
        )

    if config.fake_llm():
        from sentinel.llm.fake import fake_call

        result = fake_call(
            node=node, model=model, system=system, messages=messages,
            output_format=output_format, tools=tools,
        )
        _finalize(result, node, model, system, messages, run_id, budget)
        return result

    if config.provider() == "openai":
        # DEV-ONLY shakedown path. Does not validate judge accuracy or the
        # attacker guardrail; see sentinel/llm/openai_adapter.py.
        from sentinel.llm.openai_adapter import openai_call

        if budget is not None:
            budget_mod.check(budget, 0.02)  # coarse pre-flight; no count_tokens API parity
        result = openai_call(
            node=node, model=model, system=system, messages=messages,
            max_tokens=max_tokens, output_format=output_format, tools=tools,
            temperature=temperature,
        )
        _finalize(result, node, model, system, messages, run_id, budget)
        return result

    client = get_client()

    # 1. pre-flight token count -------------------------------------------
    try:
        counted = client.messages.count_tokens(
            model=model,
            system=_system_blocks(system),
            messages=messages,
            **({"tools": tools} if tools else {}),
        )
        est_in = counted.input_tokens
    except Exception:
        # Never let accounting break the run; fall back to a rough estimate.
        est_in = sum(len(str(m.get("content", ""))) for m in messages) // 3

    # 2. hard budget gate --------------------------------------------------
    if budget is not None:
        budget_mod.check(budget, pricing.estimate_cost(model, est_in, max_tokens))

    # 3. the call ----------------------------------------------------------
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": _system_blocks(system),
        "messages": messages,
    }
    if effort:
        kwargs["output_config"] = {"effort": effort}
    if tools:
        kwargs["tools"] = tools
    if temperature is not None:
        kwargs["temperature"] = temperature

    t0 = time.perf_counter()
    if output_format is not None:
        response = client.messages.parse(output_format=output_format, **kwargs)
    elif use_fallbacks:
        # Opus 5's cyber classifiers can decline probe generation. A
        # cyber-category refusal is re-served by the fallback model inside the
        # same call rather than surfacing as a dead end.
        response = client.beta.messages.create(
            betas=[config.FALLBACK_BETA], fallbacks="default", **kwargs
        )
    elif max_tokens > 16000:
        with client.messages.stream(**kwargs) as stream:
            response = stream.get_final_message()
    else:
        response = client.messages.create(**kwargs)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    # 4. refusal check, BEFORE content is indexed --------------------------
    stop_reason = getattr(response, "stop_reason", None)
    refused = stop_reason == "refusal"
    category = None
    if refused:
        details = getattr(response, "stop_details", None)
        category = getattr(details, "category", None) if details else None

    text = "" if refused else _extract_text(getattr(response, "content", []))
    parsed = None
    if not refused and output_format is not None:
        parsed = getattr(response, "parsed_output", None)

    # 5. cost --------------------------------------------------------------
    usage = getattr(response, "usage", None)
    usd = pricing.cost_from_usage(model, usage)
    tin, tout = pricing.token_totals(usage)

    result = LLMResult(
        text=text,
        parsed=parsed,
        refused=refused,
        refusal_category=category,
        stop_reason=stop_reason,
        model=getattr(response, "model", model),
        usd=usd,
        tokens_in=tin,
        tokens_out=tout,
        latency_ms=latency_ms,
        content_blocks=list(getattr(response, "content", []) or []),
    )
    _finalize(result, node, model, system, messages, run_id, budget)
    return result


def _finalize(
    result: LLMResult,
    node: str,
    model: str,
    system: str,
    messages: list[dict],
    run_id: str,
    budget: dict[str, Any] | None,
) -> None:
    """6. trace entry. Every call lands here; there is no path that skips it."""
    result.trace = {
        "run_id": run_id,
        "node": node,
        "model": result.model or model,
        "ts": datetime.now(timezone.utc).isoformat(),
        "latency_ms": result.latency_ms,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "usd": result.usd,
        "input": _summarize_input(system, messages),
        "output": {
            "text": result.text[:4000],
            "parsed": (
                result.parsed.model_dump(mode="json")
                if isinstance(result.parsed, BaseModel)
                else None
            ),
            "refused": result.refused,
            "refusal_category": result.refusal_category,
            "stop_reason": result.stop_reason,
        },
    }

    if budget is not None:
        budget_mod.record(budget, result.usd, result.tokens_in, result.tokens_out)
        result.trace["budget_after"] = {
            "usd_spent": budget["usd_spent"],
            "usd_cap": budget["usd_cap"],
            "warned": budget["warned"],
        }

    if run_id:
        try:
            from sentinel.store import repo

            repo.insert_trace(run_id, result.trace)
        except Exception:
            pass  # persistence must never break a run

    if _trace_sink:
        try:
            _trace_sink(result.trace)
        except Exception:
            pass
