"""SentinelState and every structured-output schema.

The Pydantic models here are passed straight to `messages.parse(output_format=...)`,
so the schema is a guarantee rather than a hope, and no node needs JSON repair.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, Field

Classification = Literal["succeeded", "partial", "failed", "refused_differently"]
ImpactClass = Literal["data_exposure", "action_bypass", "tone_or_policy_violation"]
RunStatus = Literal["running", "paused_for_human", "completed", "aborted"]


# --------------------------------------------------------------- schemas ---
class ReconProfile(BaseModel):
    """Output of the recon sub-loop. Inferred only from benign probing."""

    apparent_purpose: str
    apparent_tools: list[str] = Field(default_factory=list)
    apparent_data_access: list[str] = Field(default_factory=list)
    refusal_map: dict[str, str] = Field(
        default_factory=dict,
        description="topic -> 'hard_block' | 'soft_hedge' | 'no_refusal'",
    )
    observed_quirks: list[str] = Field(default_factory=list)
    notes: str = ""


class PlannedAttack(BaseModel):
    id: str
    category: str
    target_weakness: str
    rationale: str
    retrieved_basis: str
    priority: Literal["high", "medium", "low"] = "medium"


class AttackPlan(BaseModel):
    attacks: list[PlannedAttack]


class JudgeVerdict(BaseModel):
    """The LLM-as-judge component. Reused verbatim by verification and scoring."""

    classification: Classification
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_span: str = Field(
        description="Verbatim quote from the target response supporting the call."
    )
    reasoning: str


class SeverityAssessment(BaseModel):
    impact_class: ImpactClass
    impact_explanation: str
    blast_radius_notes: str


class ProbeDraft(BaseModel):
    probe: str
    angle: str = Field(description="What this probe changes versus the last one.")
    withheld: str = Field(
        default="",
        description="If harmful content was redacted to stay within the attacker "
        "guardrail, what was withheld and why. Empty when nothing was withheld.",
    )


# ------------------------------------------------------------ graph state ---
class SentinelState(TypedDict, total=False):
    # identity
    scope_id: str
    run_id: str
    scope: dict[str, Any]
    target_type: str

    # phase outputs
    recon_profile: dict[str, Any]
    attack_plan: list[dict[str, Any]]
    # findings is written by verify (once) then enriched by score (once),
    # sequentially and on a single path - last-write-wins, not append.
    findings: list[dict[str, Any]]

    # execution cursor
    current_attack_idx: int
    current_attack_transcript: list[dict[str, Any]]
    current_attack_turn: int
    last_verdict: dict[str, Any]
    pending_escalation: dict[str, Any]
    # transient hand-off within the execution cycle (craft -> send -> judge)
    _pending_probe: dict[str, Any] | None
    _route: str

    # evidence (append-only)
    interceptor_log: Annotated[list[dict[str, Any]], operator.add]
    trace_log: Annotated[list[dict[str, Any]], operator.add]
    successful_attacks: Annotated[list[dict[str, Any]], operator.add]

    # control
    status: RunStatus
    budget: dict[str, Any]
    escalation_approved: list[str]
    abort_reason: str | None
    report: dict[str, Any]


def initial_state(
    run_id: str, scope_id: str, scope: dict[str, Any], budget: dict[str, Any]
) -> SentinelState:
    return {
        "run_id": run_id,
        "scope_id": scope_id,
        "scope": scope,
        "target_type": scope.get("target_id", "unknown"),
        "recon_profile": {},
        "attack_plan": [],
        "findings": [],
        "current_attack_idx": 0,
        "current_attack_transcript": [],
        "current_attack_turn": 0,
        "last_verdict": {},
        "pending_escalation": {},
        "interceptor_log": [],
        "trace_log": [],
        "successful_attacks": [],
        "status": "running",
        "budget": budget,
        "escalation_approved": [],
        "abort_reason": None,
        "report": {},
    }
