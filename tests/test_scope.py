"""Scope authorization: hashing, immutability, expiry, category enforcement."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from sentinel.scope import ScopeDraft, compute_hash, create_scope, validate_scope


def test_hash_is_order_independent():
    base = {
        "scope_id": "s1", "target_id": "t", "target_endpoint": "e",
        "allowed_attack_categories": ["a", "b"], "exclusions": ["x"],
        "authorizer": "who", "expiry_timestamp": "2030-01-01T00:00:00+00:00",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    shuffled = {**base, "allowed_attack_categories": ["b", "a"]}
    assert compute_hash(base) == compute_hash(shuffled)


def test_hash_changes_when_a_field_changes():
    base = {
        "scope_id": "s1", "target_id": "t", "target_endpoint": "e",
        "allowed_attack_categories": ["a"], "exclusions": [],
        "authorizer": "who", "expiry_timestamp": "2030-01-01T00:00:00+00:00",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    assert compute_hash(base) != compute_hash({**base, "target_id": "other"})


def test_valid_scope_passes(make_scope):
    s = make_scope()
    assert validate_scope(s.scope_id).ok


def test_unauthorized_category_rejected(make_scope):
    s = make_scope(categories=["multiturn_erosion"])
    assert not validate_scope(s.scope_id, "tool_parameter_hijacking").ok


def test_excluded_action_rejected(make_scope):
    s = make_scope(exclusions=["direct_jailbreak"])
    assert not validate_scope(s.scope_id, "direct_jailbreak").ok


def test_expired_scope_rejected(make_scope):
    s = make_scope()
    future = datetime.now(timezone.utc) + timedelta(days=2)
    r = validate_scope(s.scope_id, now=future)
    assert not r.ok and "expired" in r.reason


def test_missing_scope_rejected():
    assert not validate_scope("scope_does_not_exist").ok


def test_scopes_are_write_once(make_scope, fresh_db):
    s = make_scope()
    conn = fresh_db.connect()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE scopes SET target_id='evil' WHERE scope_id=?", (s.scope_id,))
        conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM scopes WHERE scope_id=?", (s.scope_id,))
        conn.commit()


def test_tampered_hash_detected(make_scope, fresh_db):
    s = make_scope()
    # Reach past the repo to simulate a tampered record.
    conn = fresh_db.connect()
    conn.execute("DROP TRIGGER scopes_immutable")
    conn.execute(
        "UPDATE scopes SET payload_json = replace(payload_json, 'support_bot', 'other') "
        "WHERE scope_id=?", (s.scope_id,)
    )
    conn.commit()
    r = validate_scope(s.scope_id)
    assert not r.ok and "tamper" in r.reason.lower()


def test_unknown_category_rejected_at_draft_time():
    with pytest.raises(ValueError):
        ScopeDraft(
            target_id="t", target_endpoint="e",
            allowed_attack_categories=["not_a_real_category"],
            authorizer="a",
            expiry_timestamp=datetime.now(timezone.utc) + timedelta(hours=1),
        )
