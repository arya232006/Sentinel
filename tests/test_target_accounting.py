"""Target calls must be traced and cost-counted, but never abort the run.

Found live: the trace DB had zero target:* rows across three full audits, and
target token cost was excluded from the budget - so the reported cost undercount
and, more importantly, the cap did not bound target spend (which matters when a
differential audit runs the target on Opus 5). Target calls now flow run_id +
budget, so they record and trace; but they use enforce_cap=False so a target
call can never raise BudgetExceeded from inside a node the graph doesn't guard.
"""

from __future__ import annotations

import pytest

from sentinel.graph.runner import run_offline
from sentinel.llm import budget as B
from sentinel.llm import client as C
from sentinel.store import repo


def test_target_calls_are_traced(make_scope, fresh_db):
    s = make_scope("support_bot", ["authority_impersonation"])
    final = run_offline(s.model_dump(), s.scope_id)
    rows = fresh_db.list_trace(final["run_id"])
    target_rows = [r for r in rows if r["node"].startswith("target:")]
    assert target_rows, "target calls were not persisted to the trace"
    # And they are still counted in the budget's call tally.
    assert len(rows) == final["budget"]["calls"]


def test_offline_target_cost_is_zero_but_counted(make_scope):
    """Offline every call is $0, so this checks the plumbing (call count rises),
    not a dollar figure."""
    s = make_scope("support_bot", ["multiturn_erosion"])
    final = run_offline(s.model_dump(), s.scope_id)
    # target calls are part of the accounted total
    assert final["budget"]["calls"] > 0


def _mock_anthropic(monkeypatch):
    monkeypatch.setattr(C.config, "fake_llm", lambda: False)
    monkeypatch.setattr(C.config, "provider", lambda: "anthropic")

    class Msgs:
        def count_tokens(self, **kw):
            return type("R", (), {"input_tokens": 1000})()

        def create(self, **kw):
            return type("Resp", (), {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "ok"}],
                "usage": {"input_tokens": 1000, "output_tokens": 500},
                "model": kw["model"],
            })()

    monkeypatch.setattr(C, "get_client", lambda: type("F", (), {"messages": Msgs()})())


def test_enforce_cap_false_records_without_raising(monkeypatch):
    """Over an exhausted budget, a Sentinel-side call still raises (the cap is
    real), but a target call with enforce_cap=False records and returns - it
    must not abort the run from inside an unguarded node."""
    _mock_anthropic(monkeypatch)
    budget = B.new_budget()
    budget["usd_spent"] = budget["usd_cap"]  # already at the cap

    with pytest.raises(B.BudgetExceeded):
        C.traced_call(node="judge_outcome", model="claude-opus-5", system="s",
                      messages=[{"role": "user", "content": "x"}], budget=budget)

    r = C.traced_call(node="target:support_bot", model="claude-haiku-4-5",
                      system="s", messages=[{"role": "user", "content": "x"}],
                      budget=budget, enforce_cap=False)
    assert r is not None  # did not raise
    assert r.text == "ok"


def test_target_cost_would_count_toward_the_cap(monkeypatch):
    """The point of the fix: target spend accumulates into usd_spent so the cap
    and the reported total are honest."""
    _mock_anthropic(monkeypatch)
    budget = B.new_budget()
    before = budget["usd_spent"]
    C.traced_call(node="target:support_bot", model="claude-haiku-4-5", system="s",
                  messages=[{"role": "user", "content": "x"}], max_tokens=500,
                  budget=budget, enforce_cap=False)
    assert budget["usd_spent"] > before, "target cost did not count toward the budget"
