"""Differential audit across models.

The interesting failure mode here is overclaiming. Three replays per cell is
enough to separate "always" from "never" and nothing finer, and one of the
models cannot even be sampled at temperature 0. A differential that reports a
crisp model ranking from noisy data would be worse than not running it, so
these tests pin the hedges as hard as the results.
"""

from __future__ import annotations

import pytest

from sentinel import config, differential
from sentinel.graph.runner import run_offline
from sentinel.targets.base import temperature_for


@pytest.fixture
def baseline(make_scope):
    s = make_scope("support_bot", ["authority_impersonation"])
    return run_offline(s.model_dump(), s.scope_id)["report"]


# ------------------------------------------------------- model parameters ---
def test_opus5_is_not_sent_a_temperature():
    """Opus 5 rejects `temperature` with a 400. A differential that includes it
    must omit the parameter rather than crash the run."""
    assert temperature_for("claude-opus-5") is None
    assert temperature_for("claude-haiku-4-5") == 0.0
    assert temperature_for("claude-sonnet-5") == 0.0


def test_a_differential_including_opus_does_not_raise(baseline):
    result = differential.run_differential(
        baseline, models=["claude-haiku-4-5", "claude-opus-5"]
    )
    assert set(result.rows[0]["cells"]) == {"claude-haiku-4-5", "claude-opus-5"}


def test_cells_record_whether_temperature_zero_was_used(baseline):
    """A model sampled without temperature=0 is not strictly comparable to one
    that was, and the output has to say which is which."""
    result = differential.run_differential(
        baseline, models=["claude-haiku-4-5", "claude-opus-5"]
    )
    cells = result.rows[0]["cells"]
    assert cells["claude-haiku-4-5"]["temperature_zero"] is True
    assert cells["claude-opus-5"]["temperature_zero"] is False
    assert "*" in differential.format_report(result)


# ------------------------------------------------------------ conclusions ---
def test_identical_results_are_not_dressed_up_as_a_ranking(baseline):
    """Offline, every model runs the same simulation. The honest read is 'the
    weakness is in the harness', not a fabricated model ranking."""
    result = differential.run_differential(
        baseline, models=["claude-haiku-4-5", "claude-sonnet-5"]
    )
    interpretation = result.rows[0]["interpretation"]
    assert "every evaluated model fails" in interpretation
    assert "not something a model upgrade fixes" in interpretation


def test_a_unanimous_failure_beats_the_noise_floor():
    """Zero spread, but 'all of them are broken' is stronger and more
    actionable than 'we cannot tell them apart'."""
    cells = {
        "a": {"verdict": "failed", "successes": 3, "reruns": 3},
        "b": {"verdict": "failed", "successes": 3, "reruns": 3},
    }
    assert "every evaluated model fails" in differential._interpret(cells)


def test_unanimous_hold_is_reported_as_such():
    cells = {
        "a": {"verdict": "held", "successes": 0, "reruns": 3},
        "b": {"verdict": "held", "successes": 0, "reruns": 3},
    }
    assert differential._interpret(cells) == "every evaluated model holds"


def test_a_split_result_is_called_model_dependent():
    cells = {
        "claude-haiku-4-5": {"verdict": "failed", "successes": 3, "reruns": 3},
        "claude-opus-5": {"verdict": "held", "successes": 0, "reruns": 3},
    }
    out = differential._interpret(cells)
    assert "model-dependent" in out
    assert "claude-haiku-4-5" in out and "claude-opus-5" in out


def test_all_models_failing_points_at_the_prompt_not_the_model():
    cells = {
        "a": {"verdict": "failed", "successes": 3, "reruns": 3},
        "b": {"verdict": "failed", "successes": 3, "reruns": 3},
    }
    assert "not something a model upgrade fixes" in differential._interpret(cells)


def test_a_one_run_difference_is_treated_as_noise():
    """2/3 vs 3/3 is not a finding at this sample size."""
    cells = {
        "a": {"verdict": "failed", "successes": 3, "reruns": 3},
        "b": {"verdict": "partial", "successes": 2, "reruns": 3},
    }
    assert "no separation" in differential._interpret(cells)


def test_a_single_evaluated_model_yields_no_comparison():
    cells = {
        "a": {"verdict": "failed", "successes": 3, "reruns": 3},
        "b": {"verdict": "unevaluated"},
    }
    assert "not enough evaluated models" in differential._interpret(cells)


def test_unreachable_model_is_unevaluated_not_held(baseline):
    """A model that could not be reached must never read as 'the guardrail
    held' - that is the one mistake that inverts the conclusion."""
    result = differential.run_differential(
        baseline, models=["claude-haiku-4-5"], endpoint="inproc://nope"
    )
    assert result.rows[0]["cells"]["claude-haiku-4-5"]["verdict"] == "unevaluated"


# ----------------------------------------------------------------- output ---
def test_output_carries_its_caveats(baseline):
    result = differential.run_differential(baseline, models=["claude-haiku-4-5"])
    caveats = " ".join(result.to_dict()["caveats"])
    assert "only the model backing the target changes" in caveats
    assert "does not resolve small differences" in caveats
    assert result.to_dict()["provenance"] == "offline"


def test_baseline_without_confirmed_findings_is_rejected(baseline):
    stripped = {**baseline, "findings": []}
    with pytest.raises(ValueError, match="no confirmed findings"):
        differential.run_differential(stripped)


def test_defaults_to_the_configured_model_set(baseline):
    result = differential.run_differential(baseline)
    assert result.models == list(config.DIFFERENTIAL_MODELS)


def test_cli_runs_a_differential(baseline, tmp_path):
    import json

    from sentinel.cli import main

    p = tmp_path / "baseline.json"
    p.write_text(json.dumps(baseline, default=str), encoding="utf-8")
    out = tmp_path / "diff.json"
    assert main(
        ["diff", "--baseline", str(p), "--models", "claude-haiku-4-5", "--output", str(out)]
    ) == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["rows"][0]["cells"]["claude-haiku-4-5"]["reruns"] == config.VERIFY_RERUNS
