"""Severity scoring: every finding must explain its own number."""

from __future__ import annotations

import pytest

from sentinel import config
from sentinel.graph.nodes.score import BASE, CONFIRMED_MULTIPLIER, score_node
from sentinel.llm import budget as B


def _state(findings):
    return {
        "run_id": "r1",
        "scope_id": "s1",
        "scope": {"target_id": "support_bot"},
        "findings": findings,
        "budget": B.new_budget(),
        "recon_profile": {},
        "attack_plan": [],
    }


def _finding(**over):
    base = {
        "finding_id": "f1",
        "attack_category": "multiturn_erosion",
        "status": "confirmed",
        "confirmed": True,
        "reproducibility": 1.0,
        "verify_reruns": config.VERIFY_RERUNS,
        "trigger_probe": "p",
        "minimized_prompt": "p",
        "target_response": "r",
        "full_conversation": [{"probe": "p", "response": "r"}],
    }
    base.update(over)
    return base


@pytest.mark.parametrize(
    "status,confirmed,repro",
    [
        ("confirmed", True, 1.0),
        ("inconsistent", False, 0.33),
        ("text_only_unconfirmed", False, 1.0),
        ("not_reproduced", False, 0.0),
    ],
)
def test_every_finding_carries_a_severity_formula(status, confirmed, repro):
    """A report with an unexplained number is not auditable - including 0.0."""
    out = score_node(
        _state([_finding(status=status, confirmed=confirmed, reproducibility=repro)])
    )
    f = out["findings"][0]
    assert f.get("severity_formula"), f"{status} produced no severity_formula"
    assert isinstance(f["severity_formula"], str)
    assert str(f["severity"]) in f["severity_formula"]


def test_not_reproduced_scores_zero_and_says_why():
    out = score_node(_state([_finding(status="not_reproduced", confirmed=False,
                                      reproducibility=0.0)]))
    f = out["findings"][0]
    assert f["severity"] == 0.0
    assert "not scored" in f["severity_formula"]
    assert "reruns" in f["severity_formula"]
    assert f["poc_log"], "even an unscored finding needs its reproduction log"


def test_formula_does_not_mislabel_a_non_tool_finding_as_text_only():
    out = score_node(_state([_finding(status="inconsistent", confirmed=False,
                                      reproducibility=0.33)]))
    formula = out["findings"][0]["severity_formula"]
    assert "text-only" not in formula
    assert "inconsistent" in formula


def test_confirmed_multiplier_penalises_unconfirmed():
    assert CONFIRMED_MULTIPLIER[True] == 1.0
    assert CONFIRMED_MULTIPLIER[False] < 1.0


def test_severity_is_the_documented_product():
    out = score_node(_state([_finding(reproducibility=1.0, confirmed=True)]))
    f = out["findings"][0]
    expected = BASE[f["impact_class"]] * 1.0 * 1.0
    assert f["severity"] == pytest.approx(expected)
