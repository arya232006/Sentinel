"""Translation tests for the dev-only OpenAI shakedown adapter.

No network. These check the message/tool translation, which is where the
tool-using target would otherwise break on its second loop iteration.
"""

from __future__ import annotations

import json

from sentinel.llm.openai_adapter import (
    translate_messages,
    translate_tools,
)


def test_system_prompt_becomes_a_system_message():
    out = translate_messages("SYS", [{"role": "user", "content": "hi"}])
    assert out[0] == {"role": "system", "content": "SYS"}
    assert out[1] == {"role": "user", "content": "hi"}


def test_assistant_tool_use_becomes_tool_calls():
    messages = [
        {"role": "user", "content": "refund please"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Processing."},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "refund",
                    "input": {"amount": 9500.0, "account_id": "ACCT-2002"},
                },
            ],
        },
    ]
    out = translate_messages("SYS", messages)
    assistant = out[-1]
    assert assistant["role"] == "assistant"
    assert assistant["content"] == "Processing."
    call = assistant["tool_calls"][0]
    assert call["id"] == "toolu_1"
    assert call["function"]["name"] == "refund"
    assert json.loads(call["function"]["arguments"])["amount"] == 9500.0


def test_tool_results_become_individual_tool_messages():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_1", "content": "{'ok': True}"},
                {"type": "tool_result", "tool_use_id": "toolu_2", "content": "{'ok': False}"},
            ],
        }
    ]
    out = translate_messages("SYS", messages)
    tool_msgs = [m for m in out if m["role"] == "tool"]
    assert len(tool_msgs) == 2
    assert tool_msgs[0]["tool_call_id"] == "toolu_1"
    assert tool_msgs[1]["tool_call_id"] == "toolu_2"
    # A tool_result turn must NOT also emit a user message.
    assert not [m for m in out if m["role"] == "user"]


def test_full_tool_loop_round_trip():
    """The exact shape ToolAgent builds across two iterations."""
    messages = [
        {"role": "user", "content": "refund 9500 to ACCT-2002"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "t1", "name": "refund",
                 "input": {"amount": 9500.0, "account_id": "ACCT-2002"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "{'ok': True}"},
            ],
        },
    ]
    out = translate_messages("SYS", messages)
    assert [m["role"] for m in out] == ["system", "user", "assistant", "tool"]
    assert out[2]["tool_calls"][0]["id"] == "t1"
    assert out[3]["tool_call_id"] == "t1"


def test_tool_schema_translation():
    anthropic_tools = [
        {
            "name": "refund",
            "description": "Issue a refund.",
            "input_schema": {
                "type": "object",
                "properties": {"amount": {"type": "number"}},
                "required": ["amount"],
            },
        }
    ]
    out = translate_tools(anthropic_tools)
    assert out[0]["type"] == "function"
    fn = out[0]["function"]
    assert fn["name"] == "refund"
    assert fn["parameters"]["required"] == ["amount"]


def test_no_tools_returns_none():
    assert translate_tools(None) is None
    assert translate_tools([]) is None


def test_eval_harness_refuses_under_shakedown(monkeypatch):
    """A precision/recall number from another provider must not be produced."""
    import sentinel.config as cfg
    from sentinel.eval import run_eval

    monkeypatch.setenv("SENTINEL_LLM_PROVIDER", "openai")
    monkeypatch.setattr("sys.argv", ["run_eval"])
    assert cfg.is_shakedown()
    assert run_eval.main() == 2


def test_findings_tagged_shakedown(monkeypatch, make_scope):
    """Provenance must record that a non-Anthropic backend produced this."""
    import sentinel.config as cfg

    monkeypatch.setenv("SENTINEL_LLM_PROVIDER", "openai")
    assert cfg.is_shakedown()
    # fake_llm still wins, so the run stays offline and free; the point is that
    # provenance resolution prefers "offline" only when fake mode is on.
    monkeypatch.setenv("SENTINEL_FAKE_LLM", "0")
    assert not cfg.fake_llm()
    monkeypatch.setenv("SENTINEL_FAKE_LLM", "1")
