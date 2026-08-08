/** Typed client for the FastAPI surface in sentinel/api/main.py. */

import type {
  Finding,
  Health,
  Report,
  Scope,
  ScopeDraft,
  ScopeSummary,
  TraceEntry,
} from "./types";

export const API_BASE = (
  process.env.NEXT_PUBLIC_SENTINEL_API ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    // A dead backend is the single most common failure here, and the default
    // "Failed to fetch" gives the operator nothing to act on.
    throw new ApiError(`Cannot reach the Sentinel API at ${API_BASE}.`, 0);
  }

  if (!res.ok) {
    // FastAPI puts validation and HTTPException messages under `detail`.
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) {
        detail =
          typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail);
      }
    } catch {
      /* non-JSON error body; statusText stands */
    }
    throw new ApiError(detail, res.status);
  }

  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  health: () => request<Health>("/health"),

  createScope: (draft: ScopeDraft) =>
    request<Scope>("/scopes", { method: "POST", body: JSON.stringify(draft) }),

  /** Lean projection — see ScopeSummary. Use getScope for the full record. */
  listScopes: () => request<ScopeSummary[]>("/scopes"),

  getScope: (scopeId: string) => request<Scope>(`/scopes/${scopeId}`),

  startRun: (scopeId: string) =>
    request<{ run_id: string; scope_id: string; status: string }>("/runs", {
      method: "POST",
      body: JSON.stringify({ scope_id: scopeId }),
    }),

  listRuns: () =>
    request<{ run_id: string; scope_id: string; status: string }[]>("/runs"),

  getRun: (runId: string) =>
    request<{
      run_id: string;
      scope_id: string;
      status: string;
      pending_interrupt: unknown;
      final_state: unknown;
    }>(`/runs/${runId}`),

  /** Resolves a parked gate. `decision` is coerced server-side by _as_bool. */
  resume: (runId: string, decision: boolean, notes = "") =>
    request<{ ok: boolean; gate: string; decision: boolean }>(
      `/runs/${runId}/resume`,
      {
        method: "POST",
        body: JSON.stringify({ decision: decision ? "approve" : "reject", notes }),
      },
    ),

  getReport: (runId: string) => request<Report>(`/runs/${runId}/report`),

  getTrace: (runId: string) => request<TraceEntry[]>(`/runs/${runId}/trace`),

  /** Scope-gated: requires rag_context_poisoning to be authorized. */
  plantRagDoc: (scopeId: string, docId: string, text: string) =>
    request<Record<string, unknown>>("/targets/rag/plant", {
      method: "POST",
      body: JSON.stringify({ scope_id: scopeId, doc_id: docId, text }),
    }),

  listFindings: (runId: string) => request<Finding[]>(`/runs/${runId}/report`),

  eventsUrl: (runId: string) => `${API_BASE}/runs/${runId}/events`,
};
