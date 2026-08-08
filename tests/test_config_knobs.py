"""Env-tunable demo knobs must override cleanly and never change the defaults.

A demo needs to trade thoroughness for speed (a full high-effort audit is
~26 min), but the shipped defaults and the test suite must be unaffected by the
knobs existing.
"""

from __future__ import annotations

from sentinel import config


def test_int_env_parses_an_override(monkeypatch):
    monkeypatch.setenv("SENTINEL_MAX_ATTACKS", "3")
    assert config._int_env("SENTINEL_MAX_ATTACKS", 12) == 3


def test_int_env_falls_back_on_unset():
    assert config._int_env("SENTINEL_NOT_SET_ANYWHERE", 7) == 7


def test_int_env_falls_back_on_garbage(monkeypatch):
    """A typo'd knob must not crash the run - fall back, don't raise."""
    monkeypatch.setenv("SENTINEL_MAX_ATTACKS", "lots")
    assert config._int_env("SENTINEL_MAX_ATTACKS", 12) == 12


def test_shipped_defaults_hold_when_no_knob_is_set():
    """conftest pins provider/profile/fake but sets none of these, so the
    suite always runs against the real defaults."""
    assert config.MAX_ATTACKS_PER_RUN == 12
    assert config.PER_ATTACK_TURN_CAP == 6
    assert config.RECON_MAX_TURNS == 10
    assert config.EFFORT_ATTACKER == "high"
    # Judge ships at low: the sweep showed low ties medium on F1 (0.957).
    assert config.EFFORT_JUDGE == "low"
    assert config.EFFORT_SCORING == "medium"
