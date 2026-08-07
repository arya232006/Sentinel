"""The non-negotiable constraints: cost math, caps, and no unbounded loops."""

from __future__ import annotations

import pytest

from sentinel import config
from sentinel.graph import routers
from sentinel.llm import budget as B
from sentinel.llm import pricing


def test_cache_tokens_billed_at_their_own_rates():
    usage = {
        "input_tokens": 1000,
        "cache_read_input_tokens": 10000,
        "cache_creation_input_tokens": 2000,
        "output_tokens": 500,
    }
    # 1000*5 + 10000*0.5 + 2000*6.25 + 500*25 = 35000 micro-dollars
    assert pricing.cost_from_usage("claude-opus-5", usage) == pytest.approx(0.035)
    # Billing every input token at the plain rate would more than double it.
    naive = (13000 * 5 + 500 * 25) / 1e6
    assert naive > pricing.cost_from_usage("claude-opus-5", usage) * 2


def test_token_totals_include_cache():
    usage = {"input_tokens": 10, "cache_read_input_tokens": 20,
             "cache_creation_input_tokens": 5, "output_tokens": 7}
    assert pricing.token_totals(usage) == (35, 7)


def test_profiles():
    assert config.PROFILES["dev"].usd_cap == 2.00
    assert config.PROFILES["demo"].usd_cap == 8.00
    assert config.PROFILES["demo"].usd_warn == 5.00


def test_warning_fires_once_and_does_not_abort():
    b = B.new_budget(config.PROFILES["demo"])
    fired = []
    B.record(b, 4.0, 1, 1, on_warn=lambda x: fired.append(1))
    assert not b["warned"] and not fired
    B.record(b, 1.5, 1, 1, on_warn=lambda x: fired.append(1))
    assert b["warned"] and len(fired) == 1
    B.record(b, 0.5, 1, 1, on_warn=lambda x: fired.append(1))
    assert len(fired) == 1  # once only
    assert not B.is_exhausted(b)  # warning is advisory


def test_hard_cap_raises_preflight():
    b = B.new_budget(config.PROFILES["dev"])
    B.record(b, 1.9, 1, 1)
    with pytest.raises(B.BudgetExceeded):
        B.check(b, 0.5)


def test_router_aborts_when_budget_exhausted():
    state = {
        "budget": {"usd_spent": 2.0, "usd_cap": 2.0, "usd_warn": 1.0,
                   "warned": True, "tokens_in": 0, "tokens_out": 0, "calls": 0},
        "current_attack_turn": 0, "current_attack_idx": 0,
        "attack_plan": [{"category": "multiturn_erosion"}],
        "last_verdict": {"classification": "succeeded"},
        "escalation_approved": [],
    }
    assert routers.decide_next(state) == routers.ABORT


def test_router_respects_turn_cap():
    state = {
        "budget": {"usd_spent": 0.0, "usd_cap": 2.0},
        "current_attack_turn": config.PER_ATTACK_TURN_CAP,
        "current_attack_idx": 0,
        "attack_plan": [{"category": "multiturn_erosion"}],
        "last_verdict": {"classification": "failed"},
        "escalation_approved": [],
    }
    assert routers.decide_next(state) == routers.NEXT_ATTACK


def test_router_exits_when_plan_exhausted():
    state = {
        "budget": {"usd_spent": 0.0, "usd_cap": 2.0},
        "current_attack_turn": 0, "current_attack_idx": 3,
        "attack_plan": [{"category": "a"}, {"category": "b"}],
        "last_verdict": {"classification": "failed"},
        "escalation_approved": [],
    }
    assert routers.decide_next(state) == routers.VERIFY


def test_router_gates_first_high_severity_escalation():
    state = {
        "budget": {"usd_spent": 0.0, "usd_cap": 2.0},
        "current_attack_turn": 1, "current_attack_idx": 0,
        "attack_plan": [{"category": "authority_impersonation"}],
        "last_verdict": {"classification": "partial"},
        "escalation_approved": [],
    }
    assert routers.decide_next(state) == routers.ESCALATION_GATE
    # ...and only once per category per run.
    state["escalation_approved"] = ["authority_impersonation"]
    assert routers.decide_next(state) == routers.ESCALATE


def test_every_route_terminates():
    """No verdict/counter combination can produce an undefined route."""
    valid = {routers.ESCALATE, routers.PIVOT, routers.NEXT_ATTACK,
             routers.VERIFY, routers.ESCALATION_GATE, routers.ABORT}
    for classification in ("succeeded", "partial", "failed", "refused_differently", "junk"):
        for turn in (0, 3, config.PER_ATTACK_TURN_CAP, 99):
            for idx in (0, 1, 50):
                state = {
                    "budget": {"usd_spent": 0.0, "usd_cap": 2.0},
                    "current_attack_turn": turn, "current_attack_idx": idx,
                    "attack_plan": [{"category": "multiturn_erosion"}],
                    "last_verdict": {"classification": classification},
                    "escalation_approved": [],
                }
                assert routers.decide_next(state) in valid


def test_temperature_rejected_for_opus5():
    """Passing temperature to Opus 5 must fail loudly here, not as an API 400."""
    from sentinel.llm.client import traced_call

    with pytest.raises(ValueError, match="temperature"):
        traced_call(
            node="t", model="claude-opus-5", system="s",
            messages=[{"role": "user", "content": "x"}], temperature=0.0,
        )
