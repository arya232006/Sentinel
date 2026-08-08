"""Retrieval-augmented planning.

Three sources feed the planner before it drafts a plan:

  1. the curated technique knowledge base (techniques.json), retrieved by
     relevance to the recon profile;
  2. techniques earlier runs discovered and wrote back (learned_techniques),
     retrieved by exactly the same scoring - a learned entry competes with a
     curated one on fit, it is not privileged or penalised;
  3. the cross-run pattern table (attack_pattern -> target_type -> success_rate),
     which is what makes the planner improve across runs rather than starting
     cold every time.

(2) and (3) are different kinds of memory and both are needed: the pattern table
knows *that* a category works against a target type, a learned technique knows
*how* the manoeuvre goes, which is what transfers to a target it has never seen.

Retrieval over ~12 techniques does not need embeddings; scoring on category
overlap and susceptibility-signal matches is more predictable and has no
warm-up cost. The RAG *target* uses Chroma because that is the system under
test; the planner's own retrieval does not need to.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from sentinel import config
from sentinel.config import ROOT
from sentinel.store import repo

_KB_PATH = ROOT / "sentinel" / "knowledge" / "techniques.json"


@lru_cache(maxsize=1)
def load_techniques() -> list[dict[str, Any]]:
    """The curated file. Cached: it is read-only and never changes at runtime."""
    return json.loads(_KB_PATH.read_text(encoding="utf-8"))["techniques"]


def learned_techniques() -> list[dict[str, Any]]:
    """Techniques earlier runs wrote back, filtered to this run's provenance.

    Not cached - a run writes to this table and the next run must see it.

    The provenance filter is the important part. An offline simulation or a
    non-Anthropic shakedown can discover a "technique" that is really an
    artifact of the harness; letting one of those steer a live audit would
    quietly corrupt a real result. A live run therefore retrieves only live
    discoveries, and each mode only ever learns from itself.
    """
    return repo.list_learned_techniques(provenance=config.run_provenance())


def all_techniques() -> list[dict[str, Any]]:
    """Curated plus learned, in the shape the planner and the curator expect."""
    return list(load_techniques()) + learned_techniques()


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
    for t in all_techniques():
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
    lines = ["## Documented techniques (knowledge base)"]
    if not techniques:
        lines.append("(none matched the authorized categories)")
    for t in techniques:
        # Learned entries are labelled with where they came from, so a plan
        # citing one is traceable back to the run that discovered it.
        origin = (
            f" | LEARNED by run {t.get('source_run_id', '?')} against "
            f"{t.get('source_target', '?')}"
            if t.get("learned")
            else " | curated"
        )
        lines.append(
            f"- id={t['id']} | category={t['category']} | {t['name']}{origin}\n"
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
