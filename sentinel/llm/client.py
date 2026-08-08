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
    # Set when a call degraded rather than succeeded (e.g. unparsable structured
    # output). Surfaced in the trace so a degraded run is visible, not silent.
    trace_note: str = ""

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


# Recovery escalates the MODEL, not the token budget.
#
# Measured, and it overturned the obvious guess. A structured response that
# fails to parse looks like truncation, so the first fix was to retry with 3x
# the tokens. That never once helped: the same prompt failed identically at
# 4000, 8000 and 16000 - the model rambles until it exhausts whatever ceiling
# it is given, so more room just buys more wasted tokens. One case that
# succeeded at 4000 actually FAILED at 8000, i.e. the retry caused failures.
#
# What does work is swapping models. Opus 5 declines the recon and planning
# prompts outright (cyber classifier) and generates unparsably on some attacker
# prompts; Opus 4.8 either answers them cleanly or refuses cleanly - and a clean
# refusal is a usable, first-class outcome, unlike an unparsable ramble.
_PARSE_MAX_ATTEMPTS = 1


def _invoke(
    client: anthropic.Anthropic,
    kwargs: dict[str, Any],
    output_format: type[BaseModel] | None,
    use_fallbacks: bool,
) -> tuple[Any, Exception | None]:
    """One API call in whichever shape this request needs.

    Split out of traced_call so the identical request can be re-issued against
    the fallback model when the primary declines.
    """
    if output_format is not None:
        return _parse_once(client, kwargs, output_format)
    if use_fallbacks:
        return (
            client.beta.messages.create(
                betas=[config.FALLBACK_BETA], fallbacks="default", **kwargs
            ),
            None,
        )
    if kwargs["max_tokens"] > 16000:
        with client.messages.stream(**kwargs) as stream:
            return stream.get_final_message(), None
    return client.messages.create(**kwargs), None


def _parse_once(
    client: anthropic.Anthropic, kwargs: dict[str, Any], output_format: type[BaseModel]
) -> tuple[Any, Exception | None]:
    """`messages.parse()`, returning the parse failure instead of raising it.

    A structured response that cannot be parsed raises a pydantic
    ValidationError from inside the SDK. Left alone, that propagates out of the
    node and aborts the whole audit - one bad response anywhere kills the run.
    Every node carries a `parsed is None` fallback for exactly this case; those
    fallbacks were unreachable because the SDK raised first. Returning the error
    is what makes them reachable.

    Genuine API errors (auth, rate limit, 400) are re-raised untouched: those
    are not recoverable by retrying, and masking one would turn a
    misconfiguration into a silently degraded audit.
    """
    try:
        return client.messages.parse(output_format=output_format, **kwargs), None
    except anthropic.APIError:
        raise
    except Exception as exc:  # noqa: BLE001 - schema/parse failure
        return None, exc


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
    allow_refusal_fallback: bool = True,
    enforce_cap: bool = True,
    run_id: str = "",
    budget: dict[str, Any] | None = None,
) -> LLMResult:
    """Make one Claude call, fully accounted for.

    `temperature` is only valid for the target harness (Haiku 4.5). Passing it
    with an Opus 5 model is a programming error and raises here rather than
    producing an opaque 400 from the API.

    `enforce_cap=False` records and traces the call but skips the pre-flight
    raise. The target harness uses it: target cost MUST count toward the budget
    (so the cap is real and the reported total is honest - a differential audit
    runs the target on Opus 5), but a target call must not itself abort the run
    with BudgetExceeded from inside a node the graph doesn't guard. The cap is
    still enforced, just at the next Sentinel-side pre-flight instead of here.
    """
    if (
        temperature is not None
        and not config.accepts_temperature(model)
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

        if budget is not None and enforce_cap:
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
    if budget is not None and enforce_cap:
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
    response, parse_error = _invoke(client, kwargs, output_format, use_fallbacks)

    # 3b. client-side model fallback ---------------------------------------
    #
    # Two distinct failures recover the same way, so they share one path:
    #
    #   refusal        Opus 5's cyber classifiers decline the recon and
    #                  planning prompts outright (measured: stop_reason
    #                  "refusal", category "cyber", on every attempt). Opus 4.8
    #                  answers the identical prompts.
    #   unparsable     On some attacker prompts Opus 5 generates until it
    #                  exhausts max_tokens without ever closing the JSON. Opus
    #                  4.8 either answers cleanly or refuses cleanly - and a
    #                  clean refusal is a usable outcome, unlike a ramble.
    #
    # The server-side `fallbacks` beta cannot be combined with structured
    # output, and every node that matters uses structured output, so this is
    # done client-side. Without it the auditor cannot profile or plan at all.
    declined = getattr(response, "stop_reason", None) == "refusal"
    unparsable = response is None
    served_by_fallback = False
    _refusal_surcharge = 0.0

    if (
        allow_refusal_fallback
        and config.FALLBACK_MODEL
        and model != config.FALLBACK_MODEL
        and (declined or unparsable)
    ):
        # A ramble that never parsed still generated tokens; bill it at the
        # ceiling it consumed. A refusal is billed from its own usage.
        _refusal_surcharge = (
            pricing.estimate_cost(model, est_in, max_tokens)
            if unparsable
            else pricing.cost_from_usage(model, getattr(response, "usage", None))
        )
        fb_kwargs = {**kwargs, "model": config.FALLBACK_MODEL}
        if not config.accepts_temperature(config.FALLBACK_MODEL):
            fb_kwargs.pop("temperature", None)
        fb_response, fb_error = _invoke(
            client, fb_kwargs, output_format, use_fallbacks
        )
        if fb_response is not None:
            response, parse_error = fb_response, fb_error
            served_by_fallback = True
            _fallback_reason = "declined" if declined else "generated unparsably"

    if output_format is not None:
        if response is None:
            # Both the primary and the fallback produced something unparsable.
            # Degrade, never abort - the caller's `parsed is None` branch takes
            # over. Cost is estimated rather than read from usage, because the
            # raise loses the response object; a generation that ran to its
            # ceiling really did consume it, so this estimates a real cost.
            latency_ms = int((time.perf_counter() - t0) * 1000)
            attempts = 2 if _refusal_surcharge else 1
            spent = pricing.estimate_cost(model, est_in, max_tokens) * attempts
            result = LLMResult(
                text="",
                parsed=None,
                refused=False,
                stop_reason="output_parse_failed",
                model=model,
                usd=spent,
                tokens_in=est_in * attempts,
                tokens_out=max_tokens * attempts,
                latency_ms=latency_ms,
            )
            result.trace_note = f"structured output unparsable: {parse_error}"[:500]
            _finalize(result, node, model, system, messages, run_id, budget)
            return result
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
    # Bill against whichever model actually served the turn, plus the declined
    # attempt when a fallback ran - a refusal generates few tokens but is not
    # free, and silently dropping it would understate the run.
    billed_model = config.FALLBACK_MODEL if served_by_fallback else model
    usage = getattr(response, "usage", None)
    usd = pricing.cost_from_usage(billed_model, usage) + _refusal_surcharge
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
    if served_by_fallback:
        result.trace_note = (
            f"{model} {_fallback_reason}; re-served by {config.FALLBACK_MODEL}"
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
            "note": result.trace_note,
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
