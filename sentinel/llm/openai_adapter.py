"""DEV-ONLY OpenAI adapter — a shakedown harness, not a supported backend.

Purpose: exercise the pipeline against a real, non-deterministic model when no
Anthropic key is available. Offline mode (`SENTINEL_FAKE_LLM=1`) is
self-consistent by construction - the fake judge reads the fake target - so it
cannot catch prompts that produce garbage, structured-output parses that fail,
a judge that contradicts itself across reruns, or attacks that never land.
Running against OpenAI catches all of that.

WHAT THIS DOES NOT VALIDATE (do not let a green run here imply otherwise):

  * Judge precision/recall. Measuring GPT's judgement says nothing about Opus
    5's. A number from here must never be reported as the judge's accuracy.
  * The attacker guardrail suite. That asks whether *Claude* redacts harmful
    content under pressure; GPT's refusal behaviour is a different system.
  * Anthropic-specific behaviour the design depends on: `stop_reason:
    "refusal"`, server-side `fallbacks`, `output_config.effort`, prompt-cache
    economics, and real cost figures.

Enable with SENTINEL_LLM_PROVIDER=openai. The Anthropic path in client.py is
untouched by this module; deleting this file returns the project to
Anthropic-only with no other edits.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from pydantic import BaseModel

# Rough public rates in USD per million tokens, for shakedown accounting only.
# Not authoritative - the cost numbers that matter come from the Anthropic run.
OPENAI_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
}
_DEFAULT_RATE = (2.50, 10.00)

_client = None


def get_client():
    global _client
    if _client is None:
        import openai

        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "SENTINEL_LLM_PROVIDER=openai but OPENAI_API_KEY is not set."
            )
        _client = openai.OpenAI(api_key=key)
    return _client


def map_model(model: str) -> str:
    """Map a Claude model id onto its OpenAI stand-in.

    Overridable, because this file cannot know OpenAI's current lineup - if a
    default 404s, set the env var rather than editing code.
    """
    if model.startswith("claude-haiku"):
        return os.getenv("OPENAI_TARGET_MODEL", "gpt-4o-mini")
    return os.getenv("OPENAI_ATTACKER_MODEL", "gpt-4o")


# --------------------------------------------------------------------------
# Message translation. The tool-using target speaks Anthropic content blocks,
# so a naive pass-through breaks on the second loop iteration.
# --------------------------------------------------------------------------
def _blocks(content: Any) -> list[dict]:
    if isinstance(content, list):
        out = []
        for b in content:
            if isinstance(b, dict):
                out.append(b)
            else:  # SDK object
                out.append(
                    {
                        "type": getattr(b, "type", None),
                        "text": getattr(b, "text", None),
                        "id": getattr(b, "id", None),
                        "name": getattr(b, "name", None),
                        "input": getattr(b, "input", None),
                    }
                )
        return out
    return []


def translate_messages(system: str, messages: list[dict]) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": system}]

    for m in messages:
        role = m.get("role")
        content = m.get("content")

        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue

        blocks = _blocks(content)
        tool_results = [b for b in blocks if b.get("type") == "tool_result"]
        tool_uses = [b for b in blocks if b.get("type") == "tool_use"]
        texts = [b.get("text") or "" for b in blocks if b.get("type") == "text"]

        if tool_results:
            # Anthropic packs results into one user turn; OpenAI wants one
            # `tool` message per result, keyed by tool_call_id.
            for tr in tool_results:
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": tr.get("tool_use_id"),
                        "content": str(tr.get("content", "")),
                    }
                )
            continue

        if tool_uses:
            out.append(
                {
                    "role": "assistant",
                    "content": "\n".join(t for t in texts if t) or None,
                    "tool_calls": [
                        {
                            "id": tu.get("id"),
                            "type": "function",
                            "function": {
                                "name": tu.get("name"),
                                "arguments": json.dumps(tu.get("input") or {}),
                            },
                        }
                        for tu in tool_uses
                    ],
                }
            )
            continue

        out.append({"role": role, "content": "\n".join(texts)})

    return out


def translate_tools(tools: list[dict] | None) -> list[dict] | None:
    if not tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]


_FINISH_MAP = {
    "stop": "end_turn",
    "length": "max_tokens",
    "tool_calls": "tool_use",
    "content_filter": "refusal",
}


# --------------------------------------------------------------------------
# Structured output.
#
# OpenAI's *strict* mode cannot express two things the Sentinel schemas use:
#   - open-ended maps (ReconProfile.refusal_map is dict[str, str], which emits
#     `additionalProperties: {"type": "string"}`; strict mode demands
#     `additionalProperties: false`)
#   - numeric bounds (JudgeVerdict.confidence carries ge/le -> minimum/maximum)
#
# So this adapter uses non-strict `json_schema` and validates client-side. The
# Anthropic path is unaffected and keeps its real schema guarantee; here the
# schema is a strong hint plus a validation step, which is the right trade for
# a shakedown harness. A single repair retry covers the occasional model that
# returns prose around its JSON.
# --------------------------------------------------------------------------
def _response_format(model: type[BaseModel]) -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": model.__name__,
            "schema": model.model_json_schema(),
            "strict": False,
        },
    }


def _extract_json(text: str) -> str:
    """Pull a JSON object out of a response that may be fenced or prefaced."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("```")[1] if "```" in t[3:] else t.lstrip("`")
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    start, end = t.find("{"), t.rfind("}")
    return t[start : end + 1] if start != -1 and end > start else t


def _validate(model: type[BaseModel], text: str) -> BaseModel | None:
    try:
        return model.model_validate_json(_extract_json(text))
    except Exception:
        return None


def openai_call(
    *,
    node: str,
    model: str,
    system: str,
    messages: list[dict],
    max_tokens: int,
    output_format: type[BaseModel] | None,
    tools: list[dict] | None,
    temperature: float | None,
):
    from sentinel.llm.client import LLMResult

    client = get_client()
    oa_model = map_model(model)
    oa_messages = translate_messages(system, messages)
    oa_tools = translate_tools(tools)

    kwargs: dict[str, Any] = {
        "model": oa_model,
        "messages": oa_messages,
        "max_completion_tokens": max_tokens,
    }
    if oa_tools:
        kwargs["tools"] = oa_tools
    if temperature is not None:
        kwargs["temperature"] = temperature

    t0 = time.perf_counter()
    if output_format is not None:
        try:
            response = client.chat.completions.create(
                response_format=_response_format(output_format), **kwargs
            )
        except Exception as exc:
            # Any schema the endpoint won't accept (nested $defs/$ref, an
            # unsupported keyword) degrades to plain JSON mode with the schema
            # inlined in the prompt, rather than killing the run with a 400.
            if "response_format" not in str(exc) and "schema" not in str(exc).lower():
                raise
            fallback = list(oa_messages)
            fallback[0] = {
                "role": "system",
                "content": (
                    f"{system}\n\nReturn ONLY a JSON object conforming to this "
                    f"schema. No prose, no code fences.\n"
                    f"{json.dumps(output_format.model_json_schema())}"
                ),
            }
            response = client.chat.completions.create(
                **{**kwargs, "messages": fallback},
                response_format={"type": "json_object"},
            )
    else:
        response = client.chat.completions.create(**kwargs)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    choice = response.choices[0]
    msg = choice.message

    # OpenAI surfaces a structured-output refusal on the message itself; treat
    # it the same way the Anthropic path treats stop_reason == "refusal".
    refusal = getattr(msg, "refusal", None)
    refused = bool(refusal) or choice.finish_reason == "content_filter"

    extra_in = extra_out = 0
    parsed = None
    if output_format is not None and not refused:
        parsed = _validate(output_format, msg.content or "")
        if parsed is None:
            # One repair attempt: hand the model its own output and the schema
            # and ask for JSON only. Cheap on mini, and it keeps a single bad
            # generation from failing an entire attack.
            repair = client.chat.completions.create(
                model=oa_model,
                messages=[
                    {"role": "system", "content":
                     "Return ONLY a JSON object matching the schema. No prose, no code fences."},
                    {"role": "user", "content":
                     f"Schema:\n{json.dumps(output_format.model_json_schema())}\n\n"
                     f"Fix this into valid JSON matching the schema:\n{msg.content or ''}"},
                ],
                response_format=_response_format(output_format),
                max_completion_tokens=max_tokens,
            )
            ru = getattr(repair, "usage", None)
            extra_in = int(getattr(ru, "prompt_tokens", 0) or 0)
            extra_out = int(getattr(ru, "completion_tokens", 0) or 0)
            parsed = _validate(output_format, repair.choices[0].message.content or "")

    content_blocks: list[dict] = []
    for tc in getattr(msg, "tool_calls", None) or []:
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        content_blocks.append(
            {"type": "tool_use", "id": tc.id, "name": tc.function.name, "input": args}
        )

    usage = getattr(response, "usage", None)
    tin = int(getattr(usage, "prompt_tokens", 0) or 0) + extra_in
    tout = int(getattr(usage, "completion_tokens", 0) or 0) + extra_out
    in_rate, out_rate = OPENAI_PRICING.get(oa_model, _DEFAULT_RATE)
    usd = round((tin * in_rate + tout * out_rate) / 1_000_000, 8)

    return LLMResult(
        text="" if refused else (msg.content or ""),
        parsed=parsed,
        refused=refused,
        refusal_category="content_filter" if refused else None,
        stop_reason=_FINISH_MAP.get(choice.finish_reason, choice.finish_reason),
        model=f"openai:{oa_model}",
        usd=usd,
        tokens_in=tin,
        tokens_out=tout,
        latency_ms=latency_ms,
        content_blocks=content_blocks,
    )
