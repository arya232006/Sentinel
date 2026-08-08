/**
 * Types mirroring the Python models in sentinel/.
 *
 * Source of truth, per type:
 *   Health          -> sentinel/api/main.py :: health()
 *   Scope           -> sentinel/scope/models.py :: Scope
 *   Budget          -> sentinel/llm/budget.py :: new_budget()
 *   PlannedAttack   -> sentinel/state.py :: PlannedAttack
 *   JudgeVerdict    -> sentinel/state.py :: JudgeVerdict
 *   Turn            -> sentinel/graph/nodes/send_to_target.py :: new_turn
 *   InterceptCall   -> sentinel/targets/interceptor.py :: record
 *   Finding         -> verify.py (base) + score.py (enrichment)
 *   TraceEntry      -> sentinel/llm/client.py :: _finalize
 *   SSE envelope    -> sentinel/api/events.py :: RunSession.emit
 */

export type AttackCategory =
  | "direct_jailbreak"
  | "authority_impersonation"
  | "multiturn_erosion"
  | "indirect_injection"
  | "rag_context_poisoning"
  | "tool_parameter_hijacking";

export type Classification =
  | "succeeded"
  | "partial"
  | "failed"
  | "refused_differently";

export type ImpactClass =
  | "data_exposure"
  | "action_bypass"
  | "tone_or_policy_violation";

export type RunStatus = "running" | "paused_for_human" | "completed" | "aborted";

/** verify.py sets this; "confirmed" requires interceptor agreement for tool categories. */
export type FindingStatus =
  | "confirmed"
  | "text_only_unconfirmed"
  | "not_reproduced";

/** A finding must always carry how it was produced — see verify.py. */
export type Provenance = "live" | "offline" | "shakedown" | "replayed";

export interface Health {
  ok: boolean;
  profile: string;
  budget_cap: number;
  budget_warn: number;
  fake_llm: boolean;
  provider: string;
  shakedown_mode: boolean;
  shakedown_warning: string | null;
  api_key_present: boolean;
  attacker_model: string;
  target_model: string;
  targets: string[];
  categories: AttackCategory[];
}

export interface ScopeDraft {
  target_id: string;
  target_endpoint: string;
  allowed_attack_categories: string[];
  exclusions: string[];
  authorizer: string;
  expiry_timestamp: string;
}

export interface Scope extends ScopeDraft {
  scope_id: string;
  created_at: string;
  signed_hash: string;
}

/**
 * GET /scopes returns a deliberately lean projection — repo.list_scopes selects
 * five columns only. The full record, including categories and signed_hash,
 * comes from GET /scopes/{id}.
 */
export interface ScopeSummary {
  scope_id: string;
  target_id: string;
  authorizer: string;
  expiry_timestamp: string;
  created_at: string;
}

/**
 * The `budget` SSE event has two producers: _emit_update sends the full record,
 * while the per-call trace sink sends only {usd_spent, usd_cap, warned}. Every
 * field beyond those three is therefore optional.
 */
export interface Budget {
  usd_spent: number;
  usd_cap: number;
  warned: boolean;
  usd_warn?: number;
  profile?: string;
  tokens_in?: number;
  tokens_out?: number;
  calls?: number;
}

export interface PlannedAttack {
  id: string;
  category: AttackCategory;
  target_weakness: string;
  rationale: string;
  retrieved_basis: string;
  priority: "high" | "medium" | "low";
  /**
   * The `recon_profile.refusal_map` key this attack probes, copied verbatim by
   * the planner. Ties an attack to a specific refusal behaviour instead of
   * inferring it from prose. May be "" if the model found no key applicable.
   */
  target_facet?: string;
}

export interface ReconProfile {
  apparent_purpose: string;
  apparent_tools: string[];
  apparent_data_access: string[];
  /** topic -> "hard_block" | "soft_hedge" | "no_refusal" */
  refusal_map: Record<string, string>;
  observed_quirks: string[];
  notes: string;
}

export interface JudgeVerdict {
  classification: Classification;
  confidence: number;
  evidence_span: string;
  reasoning: string;
}

export interface InterceptCall {
  tool_name: string;
  arguments: Record<string, unknown>;
  executed: boolean;
  result: unknown;
  flagged: boolean;
  flag_reason: string | null;
  session_id: string;
  attack_id: string | null;
  turn: number | null;
  ts: string;
}

export interface Turn {
  probe: string;
  angle?: string;
  withheld?: string;
  response: string;
  tool_calls?: InterceptCall[];
  retrieved_docs?: string[];
  inconclusive?: boolean;
  error?: string | null;
  attack_id: string;
  category: AttackCategory;
  turn: number;
  ts: string;
  verdict?: JudgeVerdict;
  /** craft_probe sets these when the attacker model declined to generate. */
  refused?: boolean;
  refusal_category?: string | null;
  note?: string;
}

export interface PocStep {
  step: number;
  action: string;
  probe?: string;
  target_response?: string;
  detail?: string;
}

export interface RerunDetail {
  classification: Classification;
  confidence: number;
  response_excerpt: string;
  tool_calls: InterceptCall[];
}

export interface Finding {
  finding_id: string;
  run_id: string;
  attack_id: string;
  attack_category: AttackCategory;
  status: FindingStatus;
  confirmed: boolean;
  provenance: Provenance;
  reproducibility: number;
  reproduced: boolean;
  corroborated_by_interceptor: boolean;
  corroborating_call: InterceptCall | null;
  confirmation_note: string;
  trigger_probe: string;
  minimized_prompt: string;
  minimization_steps: number;
  target_response: string;
  full_conversation: { probe: string; response: string }[];
  rerun_details: RerunDetail[];
  withheld: string;
  verify_temperature: number;
  verify_reruns: number;
  created_at: string;

  /** Added by score.py; absent until the scoring node runs. */
  severity?: number;
  impact_class?: ImpactClass;
  impact_explanation?: string;
  blast_radius_notes?: string;
  mitigation?: string;
  severity_formula?: string;
  poc_log?: PocStep[];
}

export interface TraceEntry {
  run_id: string;
  node: string;
  model: string;
  ts: string;
  latency_ms: number;
  tokens_in: number;
  tokens_out: number;
  usd: number;
  input: { system: string; messages: { role: string; content: string }[] };
  output: {
    text: string;
    parsed: Record<string, unknown> | null;
    refused: boolean;
    refusal_category: string | null;
    stop_reason: string | null;
  };
  budget_after?: Pick<Budget, "usd_spent" | "usd_cap" | "warned">;
}

export interface Report {
  run_id: string;
  scope_id: string;
  target_id: string;
  generated_at: string;
  summary: {
    total_findings: number;
    confirmed: number;
    max_severity: number;
    budget_spent: number;
    budget_cap: number;
  };
  interceptor_limitation: string;
  findings: Finding[];
  recon_profile: ReconProfile;
  attack_plan: PlannedAttack[];
}

// --------------------------------------------------------------- interrupts ---
export type GateName = "run_start" | "severity_escalation" | "report_finalization";

interface GateBase {
  gate: GateName;
  prompt: string;
}

export interface RunStartGate extends GateBase {
  gate: "run_start";
  target_id: string;
  target_endpoint: string;
  allowed_categories: AttackCategory[];
  authorizer: string;
}

export interface EscalationGate extends GateBase {
  gate: "severity_escalation";
  category: AttackCategory;
  verdict: JudgeVerdict;
  budget: { usd_spent: number; usd_cap: number };
}

export interface ReportGate extends GateBase {
  gate: "report_finalization";
  finding_count: number;
  findings_preview: {
    finding_id: string;
    category: AttackCategory;
    severity?: number;
    confirmed: boolean;
    minimized_prompt: string;
  }[];
}

export type InterruptPayload = RunStartGate | EscalationGate | ReportGate;

// --------------------------------------------------------------------- SSE ---
/** Route strings from sentinel/graph/routers.py. */
export type Route =
  | "escalate"
  | "pivot"
  | "next_attack"
  | "verify"
  | "escalation_gate"
  | "abort";

export interface SseEventMap {
  status: { status: RunStatus; abort_reason?: string | null; budget?: Budget; resumed_with?: unknown };
  plan: { attacks: PlannedAttack[] };
  recon: ReconProfile;
  transcript: { node: string; turns: Turn[] };
  cursor: { attack_idx: number };
  route: { route: Route; escalation: Record<string, unknown> };
  intercept: InterceptCall;
  finding: Finding;
  trace: TraceEntry;
  budget: Budget;
  budget_warning: Budget;
  interrupt: InterruptPayload;
  report: Report;
  error: { error: string; traceback: string };
  done: { status: RunStatus };
}

export type SseEventType = keyof SseEventMap;

/** The envelope every event is wrapped in — see RunSession.emit. */
export interface SseEnvelope<T extends SseEventType = SseEventType> {
  type: T;
  seq: number;
  run_id: string;
  ts: string;
  data: SseEventMap[T];
}
