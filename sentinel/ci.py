"""CI regression gate: fail the build when a closed finding reopens.

An audit is a point-in-time deliverable. The failure mode it leaves open is
mundane and common: a vulnerability is found, it is fixed, and weeks later
someone edits the system prompt to make the agent friendlier and quietly
reopens it. Prompts are code, and nobody regression-tests them.

`sentinel ci --baseline report.json` closes that. It reads a previous report,
takes only the findings that were CONFIRMED, and replays exactly those attacks
against the target as it exists now. No recon, no planning, no probe
generation - it is not exploring, it is checking known holes, which is why it
costs a handful of calls per finding instead of a full audit and is cheap
enough to run on every commit.

Exit codes are the interface:
    0  every previously-confirmed finding still fails to reproduce
    1  at least one reproduced - a regression
    2  the gate could not run (unusable baseline, unreachable target)

2 is kept distinct from 1 deliberately. A gate that cannot tell whether it
passed must not report "pass", and it is not a regression either; conflating
the two either hides breakage or cries wolf.

Authorization still applies. Replaying an attack is an attack, so the gate
mints its own scope record restricted to exactly the categories present in the
baseline, and re-validates it per finding. There is no path through Sentinel
that attacks something without an authorization record, including this one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sentinel import config
from sentinel.llm import budget as budget_mod
from sentinel.replay import confirmed_findings, replay_finding
from sentinel.scope import ScopeDraft, create_scope, validate_scope

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_ERROR = 2

HELD = "held"
REGRESSED = "regressed"
INCONCLUSIVE = "inconclusive"
BLOCKED = "blocked"


class BaselineError(Exception):
    """The baseline cannot be used as a gate. Always exit 2, never 0."""


@dataclass
class GateResult:
    exit_code: int = EXIT_OK
    checked: list[dict[str, Any]] = field(default_factory=list)
    baseline_run_id: str = ""
    target_id: str = ""
    target_endpoint: str = ""
    scope_id: str = ""
    usd_spent: float = 0.0
    system_suffix: str = ""
    error: str = ""

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in self.checked:
            out[c["status"]] = out.get(c["status"], 0) + 1
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "baseline_run_id": self.baseline_run_id,
            "target_id": self.target_id,
            "target_endpoint": self.target_endpoint,
            "scope_id": self.scope_id,
            "usd_spent": round(self.usd_spent, 6),
            "system_suffix": self.system_suffix,
            "counts": self.counts(),
            "checked": self.checked,
            "error": self.error,
        }


def mark_patch(suffix: str) -> str:
    """Label a proposed prompt change as a patch, without rewording it.

    The marker exists so a patched target can never be mistaken for the
    baseline one. Unlike the mitigation patch that fix-and-reverify builds,
    nothing is added around the text: this is the user's proposed prompt
    change and the whole point is to test it exactly as it would ship.
    """
    if not suffix.strip():
        return ""
    return f"{config.MITIGATION_PATCH_MARKER}\n{suffix.strip()}"


def load_baseline(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise BaselineError(f"baseline not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BaselineError(f"baseline is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or "findings" not in data:
        raise BaselineError(
            "baseline has no 'findings' key - expected a Sentinel report "
            "(GET /runs/{run_id}/report)"
        )
    return data


def _gate_scope(baseline: dict, endpoint: str, target_id: str, authorizer: str) -> str:
    """Mint an authorization record for exactly what the gate will replay."""
    categories = sorted(
        {
            f.get("attack_category")
            for f in confirmed_findings(baseline)
            if f.get("attack_category")
        }
    )
    if not categories:
        raise BaselineError("no confirmed findings carry an attack category")
    unknown = sorted(set(categories) - set(config.ATTACK_CATEGORIES))
    if unknown:
        raise BaselineError(f"baseline references unknown categories: {unknown}")

    scope = create_scope(
        ScopeDraft(
            target_id=target_id,
            target_endpoint=endpoint,
            allowed_attack_categories=categories,
            authorizer=authorizer,
            expiry_timestamp=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    return scope.scope_id


def run_gate(
    baseline: dict[str, Any],
    *,
    endpoint: str | None = None,
    target_id: str | None = None,
    reruns: int | None = None,
    authorizer: str = "sentinel-ci",
    max_usd: float | None = None,
    system_suffix: str = "",
    on_result=None,
) -> GateResult:
    """Replay every confirmed finding in `baseline` against the current target.

    `system_suffix` appends a block to the target's system prompt for the
    duration of the gate. That turns the same command into a pre-merge check:
    run it against a prompt change you are proposing and see whether it closes
    the baseline findings before you ship it, rather than after.
    """
    result = GateResult()
    system_suffix = mark_patch(system_suffix)
    result.baseline_run_id = baseline.get("run_id", "")
    result.target_id = target_id or baseline.get("target_id") or ""
    result.target_endpoint = endpoint or baseline.get("target_endpoint") or ""

    if not result.target_endpoint:
        raise BaselineError(
            "baseline records no target_endpoint; pass --endpoint explicitly"
        )

    findings = confirmed_findings(baseline)
    if not findings:
        raise BaselineError(
            "baseline contains no confirmed findings - there is nothing to gate on"
        )

    result.scope_id = _gate_scope(
        baseline, result.target_endpoint, result.target_id, authorizer
    )

    budget = budget_mod.new_budget()
    if max_usd is not None:
        budget["usd_cap"] = max_usd
        budget["usd_warn"] = max_usd * 0.5

    run_id = f"ci_{result.baseline_run_id or 'baseline'}"[:40]
    regressed = False
    unusable = False

    for f in findings:
        category = f.get("attack_category", "")
        entry: dict[str, Any] = {
            "finding_id": f.get("finding_id"),
            "attack_category": category,
            "baseline_severity": f.get("severity", 0.0),
            "baseline_reproducibility": f.get("reproducibility", 0.0),
            "minimized_prompt": (f.get("minimized_prompt") or "")[:300],
        }

        check = validate_scope(result.scope_id, category)
        if not check.ok:
            entry.update(status=BLOCKED, note=f"scope check failed: {check.reason}")
            unusable = True
            result.checked.append(entry)
            if on_result:
                on_result(entry)
            continue

        try:
            outcome = replay_finding(
                f,
                run_id=run_id,
                endpoint=result.target_endpoint,
                target_id=result.target_id,
                budget=budget,
                reruns=reruns,
                system_suffix=system_suffix,
                label="ci",
            )
        except budget_mod.BudgetExceeded as exc:
            entry.update(status=INCONCLUSIVE, note=str(exc))
            unusable = True
            result.checked.append(entry)
            if on_result:
                on_result(entry)
            continue

        if outcome.inconclusive >= outcome.reruns or outcome.reruns == 0:
            entry.update(
                status=INCONCLUSIVE,
                note="target returned no usable response; cannot tell whether "
                "this finding still reproduces",
            )
            unusable = True
        elif outcome.reproduced:
            entry.update(
                status=REGRESSED,
                note=f"reproduced {outcome.successes}/{outcome.reruns} - this "
                "finding is open again",
            )
            regressed = True
        else:
            entry.update(
                status=HELD,
                note=f"did not reproduce ({outcome.successes}/{outcome.reruns})",
            )
        entry.update(outcome.summary())
        result.checked.append(entry)
        if on_result:
            on_result(entry)

    result.system_suffix = system_suffix
    result.usd_spent = budget["usd_spent"]
    if regressed:
        result.exit_code = EXIT_REGRESSION
    elif unusable:
        # Could not establish that everything held. Not a pass.
        result.exit_code = EXIT_ERROR
        result.error = "gate could not evaluate every finding"
    return result


def format_report(result: GateResult) -> str:
    """Terminal output. Written to be readable in a CI log, where it is the
    only thing anybody will see."""
    lines: list[str] = []
    provenance = config.run_provenance()
    lines.append("")
    lines.append("  sentinel ci - regression gate")
    lines.append(f"  baseline run : {result.baseline_run_id or '(unknown)'}")
    lines.append(f"  target       : {result.target_id} @ {result.target_endpoint}")
    lines.append(f"  scope minted : {result.scope_id}")
    if result.system_suffix:
        lines.append(
            "  prompt patch : applied "
            f"({len(result.system_suffix)} chars) - pre-merge check"
        )
    if provenance != "live":
        lines.append(f"  MODE         : {provenance} - not a result about Claude")
    lines.append("")

    symbol = {HELD: "PASS", REGRESSED: "FAIL", INCONCLUSIVE: "????", BLOCKED: "----"}
    for c in result.checked:
        lines.append(
            f"  [{symbol.get(c['status'], '????')}] {c['attack_category']}  "
            f"(baseline severity {c['baseline_severity']})"
        )
        lines.append(f"         {c.get('note', '')}")
        prompt = c.get("minimized_prompt", "")
        if prompt:
            lines.append(f"         trigger: {prompt[:120]}")
        lines.append("")

    counts = result.counts()
    lines.append(
        f"  {counts.get(HELD, 0)} held, {counts.get(REGRESSED, 0)} regressed, "
        f"{counts.get(INCONCLUSIVE, 0) + counts.get(BLOCKED, 0)} unevaluated "
        f"| ${result.usd_spent:.4f}"
    )
    if result.exit_code == EXIT_OK:
        lines.append("  GATE PASSED - no previously-confirmed finding reproduced.")
    elif result.exit_code == EXIT_REGRESSION:
        lines.append("  GATE FAILED - a previously-confirmed finding is open again.")
    else:
        lines.append(f"  GATE ERROR - {result.error}")
    lines.append("")
    return "\n".join(lines)
