"""Replay a recorded finding against a target and judge what comes back.

Three separate features need exactly this primitive, and none of them may grow
its own copy of it - the moment two of them disagree about what "replaying a
finding" means, their numbers stop being comparable:

  fix-and-reverify   replay against a target patched with the finding's own
                     mitigation, to test whether the fix actually closes it
  CI regression gate replay against the current target in a pipeline, to catch
                     a prompt change that silently reopens a closed finding
  differential audit replay against the same harness backed by a different
                     model, to show where a guardrail holds

All three are the same operation with a different target modification, so this
module owns the operation and each feature owns only its modification.

The replayed conversation is byte-identical to what `verify` measured: the full
recorded conversation with `trigger_probe` as the final turn, judged with the
same `judge_response` and the same goal string. That is what makes an AFTER
number comparable to the BEFORE number in the report.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sentinel import config
from sentinel.graph.nodes.judge import judge_response, render_target_output
from sentinel.graph.nodes.verify import replay_messages
from sentinel.graph.transport import call_target


@dataclass
class ReplayOutcome:
    """What N replays of one finding produced."""

    reruns: int = 0
    successes: int = 0
    inconclusive: int = 0
    classifications: list[str] = field(default_factory=list)
    details: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    traces: list[dict[str, Any]] = field(default_factory=list)
    skipped_reason: str = ""

    @property
    def reproducibility(self) -> float:
        return (self.successes / self.reruns) if self.reruns else 0.0

    @property
    def reproduced(self) -> bool:
        """Same majority rule verification uses. A finding that fires once in
        three is not reproduced, in any of the three features."""
        return self.reruns > 0 and self.successes >= config.VERIFY_MAJORITY

    def summary(self) -> dict[str, Any]:
        return {
            "reruns": self.reruns,
            "successes": self.successes,
            "inconclusive": self.inconclusive,
            "reproducibility": round(self.reproducibility, 4),
            "reproduced": self.reproduced,
            "classifications": list(self.classifications),
            "skipped_reason": self.skipped_reason,
        }


def attack_goal(finding: dict[str, Any]) -> str:
    """The goal string handed to the judge.

    Deliberately the same shape verify used, because a BEFORE and an AFTER
    judged against different goals are not a comparison.
    """
    return finding.get("attack_category", "") or ""


def replay_finding(
    finding: dict[str, Any],
    *,
    run_id: str,
    endpoint: str,
    target_id: str = "",
    budget: dict[str, Any] | None = None,
    reruns: int | None = None,
    system_suffix: str = "",
    model: str | None = None,
    label: str = "replay",
) -> ReplayOutcome:
    """Re-run one finding's attack `reruns` times and judge each response.

    Never raises on a target problem: an unreachable or malformed response is
    counted as inconclusive rather than as a pass, so a broken target can never
    be read as "the vulnerability is fixed".
    """
    reruns = reruns if reruns is not None else config.VERIFY_RERUNS
    outcome = ReplayOutcome()

    conversation = finding.get("full_conversation") or []
    trigger = finding.get("trigger_probe") or finding.get("minimized_prompt") or ""
    if not trigger:
        outcome.skipped_reason = "finding carries no trigger probe to replay"
        return outcome

    goal = attack_goal(finding)
    attack_id = finding.get("attack_id") or finding.get("finding_id") or "?"

    for _ in range(reruns):
        resp = call_target(
            endpoint,
            target_id,
            replay_messages(conversation, trigger),
            session_id=f"{run_id}-{label}-{uuid.uuid4().hex[:6]}",
            attack_id=attack_id,
            system_suffix=system_suffix,
            model=model,
        )
        outcome.reruns += 1

        if resp.get("inconclusive"):
            # The target failed to answer. Not a pass, not a fail.
            outcome.inconclusive += 1
            outcome.classifications.append("inconclusive")
            outcome.details.append(
                {
                    "classification": "inconclusive",
                    "error": resp.get("error", ""),
                    "response_excerpt": "",
                    "tool_calls": [],
                }
            )
            continue

        verdict, trace = judge_response(
            run_id=run_id,
            attack_goal=goal,
            probe=trigger,
            target_response=render_target_output(resp),
            budget=budget,
        )
        outcome.traces.append(trace)
        outcome.classifications.append(verdict.classification)
        if verdict.classification == "succeeded":
            outcome.successes += 1

        calls = resp.get("tool_calls", []) or []
        outcome.tool_calls.extend({**c, "attack_id": attack_id} for c in calls)
        outcome.details.append(
            {
                "classification": verdict.classification,
                "confidence": verdict.confidence,
                "response_excerpt": (resp.get("text", "") or "")[:200],
                "tool_calls": calls,
            }
        )

    return outcome


def confirmed_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Confirmed findings from a report, highest severity first.

    Only confirmed ones: a finding that never cleared verification is not a
    baseline anybody should be gated on, and re-running an inconsistent one
    would produce an inconsistent answer.
    """
    findings = [f for f in report.get("findings", []) if f.get("confirmed")]
    findings.sort(key=lambda f: f.get("severity", 0.0), reverse=True)
    return findings
