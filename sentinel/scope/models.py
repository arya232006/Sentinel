"""Scope authorization schema and canonical hashing.

The hash is a tamper-evident integrity check, not a cryptographic signature.
Upgrading to an HMAC with a server-side key is a change to compute_hash() alone.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

from sentinel.config import ATTACK_CATEGORIES

# Fields covered by the hash, in canonical order. signed_hash itself is excluded.
HASHED_FIELDS = (
    "scope_id",
    "target_id",
    "target_endpoint",
    "allowed_attack_categories",
    "exclusions",
    "authorizer",
    "expiry_timestamp",
    "created_at",
)


def canonical_json(payload: dict[str, Any]) -> str:
    """Deterministic serialization. Key order and separators are fixed so the
    same logical scope always hashes identically."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(payload: dict[str, Any]) -> str:
    subset = {k: payload[k] for k in HASHED_FIELDS if k in payload}
    # Categories are a set semantically; sort so ordering can't change the hash.
    if "allowed_attack_categories" in subset:
        subset["allowed_attack_categories"] = sorted(subset["allowed_attack_categories"])
    if "exclusions" in subset:
        subset["exclusions"] = sorted(subset["exclusions"])
    return hashlib.sha256(canonical_json(subset).encode("utf-8")).hexdigest()


class ScopeDraft(BaseModel):
    """What the authorization form submits."""

    target_id: str = Field(min_length=1)
    target_endpoint: str = Field(min_length=1)
    allowed_attack_categories: list[str] = Field(min_length=1)
    exclusions: list[str] = Field(default_factory=list)
    authorizer: str = Field(min_length=1)
    expiry_timestamp: datetime

    @field_validator("allowed_attack_categories")
    @classmethod
    def _known_categories(cls, v: list[str]) -> list[str]:
        unknown = sorted(set(v) - set(ATTACK_CATEGORIES))
        if unknown:
            raise ValueError(f"unknown attack categories: {unknown}")
        return v

    @field_validator("expiry_timestamp")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


class Scope(BaseModel):
    """An immutable, hashed authorization record."""

    scope_id: str
    target_id: str
    target_endpoint: str
    allowed_attack_categories: list[str]
    exclusions: list[str]
    authorizer: str
    expiry_timestamp: datetime
    created_at: datetime
    signed_hash: str

    def hashed_payload(self) -> dict[str, Any]:
        return {
            "scope_id": self.scope_id,
            "target_id": self.target_id,
            "target_endpoint": self.target_endpoint,
            "allowed_attack_categories": self.allowed_attack_categories,
            "exclusions": self.exclusions,
            "authorizer": self.authorizer,
            "expiry_timestamp": self.expiry_timestamp.isoformat(),
            "created_at": self.created_at.isoformat(),
        }

    def recompute_hash(self) -> str:
        return compute_hash(self.hashed_payload())

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        expiry = self.expiry_timestamp
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return now >= expiry
