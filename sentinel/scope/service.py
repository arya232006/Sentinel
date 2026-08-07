"""Scope creation and the validate_scope guard.

validate_scope is called at every phase transition in the graph, not once at
the start. A failure routes the graph to the aborted terminal node.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sentinel.scope.models import Scope, ScopeDraft, compute_hash
from sentinel.store import repo


class ScopeError(Exception):
    pass


class ValidationResult:
    __slots__ = ("ok", "reason")

    def __init__(self, ok: bool, reason: str = ""):
        self.ok = ok
        self.reason = reason

    def __bool__(self) -> bool:
        return self.ok

    def __repr__(self) -> str:
        return f"ValidationResult(ok={self.ok}, reason={self.reason!r})"


def create_scope(draft: ScopeDraft) -> Scope:
    """Create and immutably persist a scope. Write-once: repo has no update path."""
    scope_id = f"scope_{uuid.uuid4().hex[:12]}"
    created_at = datetime.now(timezone.utc)

    payload = {
        "scope_id": scope_id,
        "target_id": draft.target_id,
        "target_endpoint": draft.target_endpoint,
        "allowed_attack_categories": draft.allowed_attack_categories,
        "exclusions": draft.exclusions,
        "authorizer": draft.authorizer,
        "expiry_timestamp": draft.expiry_timestamp.isoformat(),
        "created_at": created_at.isoformat(),
    }
    scope = Scope(**payload, signed_hash=compute_hash(payload))
    repo.insert_scope(scope)
    return scope


def get_scope(scope_id: str) -> Scope | None:
    return repo.get_scope(scope_id)


def validate_scope(
    scope_id: str,
    requested_action: str | None = None,
    *,
    now: datetime | None = None,
) -> ValidationResult:
    """Guard checked at every phase transition.

    Order matters: existence, then integrity, then expiry, then authorization.
    An expired-and-tampered scope reports tampering, which is the more serious
    finding.
    """
    scope = repo.get_scope(scope_id)
    if scope is None:
        return ValidationResult(False, f"no scope record for {scope_id}")

    if scope.recompute_hash() != scope.signed_hash:
        return ValidationResult(False, "scope hash mismatch - record was tampered with")

    if scope.is_expired(now):
        return ValidationResult(
            False, f"scope expired at {scope.expiry_timestamp.isoformat()}"
        )

    if requested_action:
        if requested_action in scope.exclusions:
            return ValidationResult(False, f"'{requested_action}' is explicitly excluded")
        # Phase names (recon, planning, verify...) are always permitted; only
        # attack categories are checked against the allowlist.
        from sentinel.config import ATTACK_CATEGORIES

        if requested_action in ATTACK_CATEGORIES:
            if requested_action not in scope.allowed_attack_categories:
                return ValidationResult(
                    False, f"category '{requested_action}' not authorized by scope"
                )

    if scope.target_id in scope.exclusions:
        return ValidationResult(False, f"target '{scope.target_id}' is excluded")

    return ValidationResult(True, "ok")
