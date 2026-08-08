"""One bad response must never kill an audit.

Found live: Opus 5 thinks adaptively and `max_tokens` caps thinking *plus*
output, so a structured response can be truncated mid-JSON. `messages.parse()`
then raises a pydantic ValidationError from inside the SDK, which propagated out
of the node and aborted the entire run.

Every node carries a `parsed is None` fallback for exactly this case. Those
fallbacks were unreachable, because the SDK raised before the node ever saw the
result - and `craft_probe` did not have one at all. Both are pinned here.
"""

from __future__ import annotations

from unittest.mock import patch

import anthropic
import pytest
from pydantic import BaseModel

from sentinel.llm import budget as B
from sentinel.llm import client as C
from sentinel.state import ProbeDraft, ReconProfile


@pytest.fixture
def anthropic_path(monkeypatch):
    """Force traced_call down the Anthropic branch.

    conftest pins SENTINEL_FAKE_LLM=1 for the suite, which short-circuits before
    the SDK is ever reached - so without this the mocked client is never called
    and these tests would pass vacuously.
    """
    monkeypatch.setattr(C.config, "fake_llm", lambda: False)
    monkeypatch.setattr(C.config, "provider", lambda: "anthropic")


class _Counter:
    def __init__(self, exc):
        self.n = 0
        self.exc = exc

    def count_tokens(self, **kw):
        class R:
            input_tokens = 100

        return R()

    def parse(self, **kw):
        self.n += 1
        raise self.exc


def _client(exc):
    msgs = _Counter(exc)
    return type("FakeClient", (), {"messages": msgs})(), msgs


def _call(fake, **over):
    kwargs = dict(
        node="recon",
        model="claude-opus-5",
        system="s",
        messages=[{"role": "user", "content": "x"}],
        max_tokens=2000,
        output_format=ReconProfile,
    )
    kwargs.update(over)
    with patch.object(C, "get_client", lambda: fake):
        return C.traced_call(**kwargs)


def test_truncated_structured_output_does_not_raise(anthropic_path):
    fake, msgs = _client(ValueError("EOF while parsing a string"))
    result = _call(fake)
    assert result.parsed is None
    assert result.stop_reason == "output_parse_failed"


def test_recovery_escalates_the_model_not_the_token_budget(anthropic_path):
    """Measured: the identical prompt failed at 4000, 8000 and 16000 tokens,
    and one case that worked at 4000 FAILED at 8000. Asking for more room buys
    more wasted tokens. Swapping models is what recovers."""
    seen = []

    class Msgs(_Counter):
        def parse(self, **kw):
            seen.append((kw["model"], kw["max_tokens"]))
            return super().parse(**kw)

    m = Msgs(ValueError("unparsable"))
    fake = type("F", (), {"messages": m})()
    _call(fake, model="claude-opus-5", max_tokens=2000)

    assert seen == [("claude-opus-5", 2000), (C.config.FALLBACK_MODEL, 2000)]
    assert {mt for _, mt in seen} == {2000}, "max_tokens must not be escalated"


def test_a_real_api_error_is_not_masked(anthropic_path):
    """Auth failures and 400s are not fixed by asking for more tokens. Masking
    one would turn a misconfiguration into a silently degraded audit."""
    exc = anthropic.APIError("boom", request=None, body=None)
    fake, msgs = _client(exc)
    with pytest.raises(anthropic.APIError):
        _call(fake)
    assert msgs.n == 1, "an API error must not be retried"


def test_degraded_call_is_still_billed_and_traced(anthropic_path):
    """The raise loses the response object, so cost is estimated - but it is
    never zero. A failed call that generated tokens still spent money."""
    budget = B.new_budget()
    fake, _ = _client(ValueError("truncated"))
    result = _call(fake, budget=budget)
    assert result.usd > 0
    assert budget["usd_spent"] == pytest.approx(result.usd)
    assert "unparsable" in result.trace["output"]["note"]


def test_every_structured_node_survives_an_unparsable_response(make_scope, monkeypatch):
    """The end-to-end property: an audit completes even when a node's
    structured output cannot be parsed."""
    from sentinel.graph.runner import run_offline
    import sentinel.llm.fake as fake_mod

    real = fake_mod.fake_call

    def flaky(**kw):
        r = real(**kw)
        if kw["node"] == "craft_probe":
            r.parsed = None  # simulate a truncated ProbeDraft
            r.stop_reason = "output_parse_failed"
        return r

    monkeypatch.setattr(fake_mod, "fake_call", flaky)
    s = make_scope("support_bot", ["authority_impersonation"])
    final = run_offline(s.model_dump(), s.scope_id)

    assert final["status"] == "completed", "an unparsable probe aborted the run"


def test_craft_probe_records_why_no_probe_was_sent():
    """Refusal and unparsable output are different failures and the transcript
    must distinguish them."""
    from sentinel.graph.nodes.craft_probe import craft_probe_node
    from sentinel.llm.client import LLMResult
    import sentinel.graph.nodes.craft_probe as cp

    state = {
        "run_id": "r",
        "scope": {"target_id": "support_bot"},
        "recon_profile": {},
        "attack_plan": [{"id": "a1", "category": "authority_impersonation",
                         "target_weakness": "w", "rationale": "r"}],
        "current_attack_idx": 0,
        "current_attack_turn": 0,
        "current_attack_transcript": [],
        "budget": B.new_budget(),
    }

    for stub, expected in [
        (LLMResult(refused=True, refusal_category="cyber"), "refused to craft"),
        (LLMResult(parsed=None, stop_reason="output_parse_failed"), "no usable probe"),
    ]:
        with patch.object(cp, "traced_call", lambda **kw: stub):
            out = craft_probe_node(dict(state))
        turn = out["current_attack_transcript"][-1]
        assert turn["probe"] == ""
        assert expected in turn["note"]
        assert out["_pending_probe"] is None


# --------------------------------------------------------------------------
# Client-side refusal fallback.
#
# Measured live: Opus 5's cyber classifiers decline the recon and planning
# prompts on every attempt (stop_reason="refusal", category="cyber"), while
# Opus 4.8 answers the identical prompts. The server-side `fallbacks` beta
# cannot be combined with structured output and every node that matters uses
# structured output, so traced_call re-issues the request itself.
# --------------------------------------------------------------------------
class _Refuser:
    """Refuses for the primary model, answers for the fallback."""

    def __init__(self, fallback_model, refuse_all=False):
        self.fallback_model = fallback_model
        self.refuse_all = refuse_all
        self.models = []

    def count_tokens(self, **kw):
        return type("R", (), {"input_tokens": 100})()

    def _respond(self, model):
        self.models.append(model)
        refused = self.refuse_all or model != self.fallback_model
        return type(
            "Resp",
            (),
            {
                "stop_reason": "refusal" if refused else "end_turn",
                "stop_details": type("D", (), {"category": "cyber"})(),
                "content": [] if refused else [{"type": "text", "text": "ok"}],
                "usage": {"input_tokens": 100, "output_tokens": 2 if refused else 200},
                "model": model,
                "parsed_output": None if refused else "PARSED",
            },
        )()

    def create(self, **kw):
        return self._respond(kw["model"])

    def parse(self, **kw):
        return self._respond(kw["model"])


def _refusing_client(refuse_all=False):
    m = _Refuser(C.config.FALLBACK_MODEL, refuse_all)
    return type("F", (), {"messages": m})(), m


def test_a_refused_call_is_reissued_on_the_fallback_model(anthropic_path):
    fake, m = _refusing_client()
    result = _call(fake, model="claude-opus-5")
    assert m.models == ["claude-opus-5", C.config.FALLBACK_MODEL]
    assert result.refused is False
    assert result.parsed == "PARSED"
    assert "declined" in result.trace_note and C.config.FALLBACK_MODEL in result.trace_note


def test_the_fallback_is_not_reissued_against_itself(anthropic_path):
    """If the fallback model itself declines, the refusal stands - retrying the
    same model forever would spend money to learn nothing."""
    fake, m = _refusing_client(refuse_all=True)
    result = _call(fake, model="claude-opus-5")
    assert m.models == ["claude-opus-5", C.config.FALLBACK_MODEL]
    assert result.refused is True
    assert result.refusal_category == "cyber"


def test_a_call_already_on_the_fallback_model_does_not_recurse(anthropic_path):
    fake, m = _refusing_client(refuse_all=True)
    _call(fake, model=C.config.FALLBACK_MODEL)
    assert m.models == [C.config.FALLBACK_MODEL]


def test_the_fallback_can_be_turned_off(anthropic_path):
    """A refusal is a first-class outcome; a caller must be able to observe one
    rather than have it silently routed around."""
    fake, m = _refusing_client()
    result = _call(fake, model="claude-opus-5", allow_refusal_fallback=False)
    assert m.models == ["claude-opus-5"]
    assert result.refused is True


def test_the_declined_attempt_is_still_billed(anthropic_path):
    """A refusal generates few tokens but is not free, and dropping it would
    understate what the run cost."""
    budget = B.new_budget()
    fake, _ = _refusing_client()
    result = _call(fake, model="claude-opus-5", budget=budget)
    assert result.usd > 0
    assert budget["usd_spent"] == pytest.approx(result.usd)


def test_billing_uses_the_model_that_actually_served_it(anthropic_path):
    """Opus 4.8 and Opus 5 happen to share a price today; billing the served
    model keeps that from silently becoming wrong when they diverge."""
    from sentinel.llm import pricing

    fake, _ = _refusing_client()
    result = _call(fake, model="claude-opus-5")
    served = pricing.cost_from_usage(
        C.config.FALLBACK_MODEL, {"input_tokens": 100, "output_tokens": 200}
    )
    declined = pricing.cost_from_usage(
        "claude-opus-5", {"input_tokens": 100, "output_tokens": 2}
    )
    assert result.usd == pytest.approx(served + declined)


def test_unparsable_output_also_falls_back_to_the_other_model(anthropic_path):
    """Measured: on one attacker prompt Opus 5 generated unparsably while Opus
    4.8 refused cleanly - and a clean refusal is a usable outcome, unlike a
    ramble. Refusal and unparsable therefore share one recovery path."""
    calls = []

    class Msgs(_Counter):
        def parse(self, **kw):
            calls.append(kw["model"])
            if kw["model"] == C.config.FALLBACK_MODEL:
                return type("R", (), {
                    "stop_reason": "end_turn",
                    "content": [{"type": "text", "text": "ok"}],
                    "usage": {"input_tokens": 10, "output_tokens": 20},
                    "model": kw["model"],
                    "parsed_output": "PARSED",
                })()
            raise ValueError("unparsable ramble")

    m = Msgs(None)
    fake = type("F", (), {"messages": m})()
    result = _call(fake, model="claude-opus-5")

    assert calls == ["claude-opus-5", C.config.FALLBACK_MODEL]
    assert result.parsed == "PARSED"
    assert "unparsably" in result.trace_note


def test_both_models_unparsable_degrades_without_aborting(anthropic_path):
    fake, m = _client(ValueError("unparsable"))
    result = _call(fake, model="claude-opus-5")
    assert result.parsed is None
    assert result.stop_reason == "output_parse_failed"
    assert result.usd > 0, "two ceiling-consuming generations are not free"
