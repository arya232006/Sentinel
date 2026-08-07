"""Retrieval-augmented planning.

Two sources feed the planner before it drafts a plan:

  1. the curated technique knowledge base (techniques.json), retrieved by
     relevance to the recon profile;
  2. the cross-run pattern table (attack_pattern -> target_type -> success_rate),
     which is what makes the planner improve across runs rather than starting
     cold every time.

Retrieval over ~12 techniques does not need embeddings; scoring on category
overlap and susceptibility-signal matches is more predictable and has no
warm-up cost. The RAG *target* uses Chroma because that is the system under
test; the planner's own retrieval does not need to.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from sentinel.config import ROOT
from sentinel.store import repo

_KB_PATH = ROOT / "sentinel" / "knowledge" / "techniques.json"


@lru_cache(maxsize=1)
def load_techniques() -> list[dict[str, Any]]:
    return json.loads(_KB_PATH.read_text(encoding="utf-8"))["techniques"]


def _profile_terms(recon_profile: dict[str, Any]) -> set[str]:
    parts: list[str] = [
        recon_profile.get("apparent_purpose", ""),
        recon_profile.get("notes", ""),
        *recon_profile.get("apparent_tools", []),
        *recon_profile.get("apparent_data_access", []),
        *recon_profile.get("observed_quirks", []),
    ]
    for topic, behaviour in (recon_profile.get("refusal_map") or {}).items():
        parts.append(f"{topic} {behaviour}")
    tokens = set()
    for p in parts:
        tokens |= {t.strip(".,;:'\"()").lower() for t in str(p).split()}
    return {t for t in tokens if len(t) > 3}


def retrieve_techniques(
    recon_profile: dict[str, Any],
    allowed_categories: list[str],
    limit: int = 6,
) -> list[dict[str, Any]]:
    """Rank techniques by fit to the observed target. Only ever returns
    techniques in categories the scope authorizes."""
    terms = _profile_terms(recon_profile)
    refusal_map = recon_profile.get("refusal_map") or {}
    has_soft_hedge = any(v == "soft_hedge" for v in refusal_map.values())

    scored: list[tuple[float, dict]] = []
    for t in load_techniques():
        if t["category"] not in allowed_categories:
            continue
        score = 0.0
        for signal in t.get("signals_of_susceptibility", []):
            sig_terms = {w.strip(".,;:").lower() for w in signal.split() if len(w) > 3}
            overlap = len(sig_terms & terms)
            score += overlap * 1.5
            if "soft_hedge" in signal and has_soft_hedge:
                score += 3.0
        # A technique whose exploit description matches observed quirks ranks up.
        exploit_terms = {w.strip(".,;:").lower() for w in t["exploits"].split() if len(w) > 3}
        score += len(exploit_terms & terms) * 1.0
        scored.append((score, t))

    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    return [t for _, t in scored[:limit]]


def retrieve_prior_runs(target_type: str, allowed_categories: list[str]) -> list[dict[str, Any]]:
    """Cross-run pattern table, filtered to authorized categories."""
    rows = repo.get_patterns(target_type)
    return [r for r in rows if r["attack_pattern"] in allowed_categories]


def format_for_planner(
    techniques: list[dict[str, Any]], priors: list[dict[str, Any]]
) -> str:
    """Render retrieved context as the planner's reference block. Each item
    carries a stable id so the plan's `retrieved_basis` can cite it."""
    lines = ["## Documented techniques (curated knowledge base)"]
    if not techniques:
        lines.append("(none matched the authorized categories)")
    for t in techniques:
        lines.append(
            f"- id={t['id']} | category={t['category']} | {t['name']}\n"
            f"    exploits: {t['exploits']}\n"
            f"    mechanism: {t['mechanism']}"
        )

    lines.append("")
    lines.append("## Prior-run outcomes against this target type")
    if not priors:
        lines.append("(no prior runs recorded for this target type)")
    for p in priors:
        lines.append(
            f"- id=prior_run:{p['attack_pattern']}/{p['target_type']} | "
            f"success_rate={p['success_rate']:.2f} "
            f"({p['successes']}/{p['attempts']} attempts)"
        )
    return "\n".join(lines)
