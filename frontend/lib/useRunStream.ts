"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import { api } from "./api";
import type {
  Budget,
  Finding,
  InterceptCall,
  InterruptPayload,
  PlannedAttack,
  ReconProfile,
  Report,
  Route,
  RunStatus,
  SseEnvelope,
  SseEventType,
  TraceEntry,
  Turn,
} from "./types";

/** Keeps a long run from growing the trace list without bound. */
const MAX_TRACES = 1000;
/** Same, for the raw feed the engagement view paces into beats. */
const MAX_FEED = 2000;

/** Event types the engagement view turns into beats; the rest are log-only. */
const BEAT_TYPES: ReadonlySet<SseEventType> = new Set<SseEventType>([
  "plan", "recon", "transcript", "route", "intercept", "finding", "interrupt", "status", "done",
]);

export interface RunState {
  status: RunStatus;
  connected: boolean;
  plan: PlannedAttack[];
  recon: ReconProfile | null;
  /** Turns grouped by attack, so completed attacks stay readable after the cursor moves on. */
  turnsByAttack: Record<string, Turn[]>;
  attackOrder: string[];
  cursor: number;
  findings: Finding[];
  traces: TraceEntry[];
  intercepts: InterceptCall[];
  routes: { route: Route; ts: string }[];
  budget: Budget | null;
  budgetWarning: boolean;
  interrupt: InterruptPayload | null;
  report: Report | null;
  error: string | null;
  abortReason: string | null;
  done: boolean;
  lastSeq: number;
  eventCounts: Partial<Record<SseEventType, number>>;
  /**
   * Ordered, deduped envelopes for the event types the engagement view paces
   * into beats. The reducer already collapses these into `state`; beats need
   * the discrete moments back, which derived state cannot reconstruct (two
   * transcript events per turn become one array either way).
   */
  feed: SseEnvelope[];
}

const initialState: RunState = {
  status: "running",
  connected: false,
  plan: [],
  recon: null,
  turnsByAttack: {},
  attackOrder: [],
  cursor: 0,
  findings: [],
  traces: [],
  intercepts: [],
  routes: [],
  budget: null,
  budgetWarning: false,
  interrupt: null,
  report: null,
  error: null,
  abortReason: null,
  done: false,
  lastSeq: 0,
  eventCounts: {},
  feed: [],
};

type Action =
  | { kind: "event"; env: SseEnvelope }
  | { kind: "connected"; value: boolean }
  | { kind: "reset" };

function reducer(state: RunState, action: Action): RunState {
  if (action.kind === "reset") return initialState;
  if (action.kind === "connected") return { ...state, connected: action.value };

  const env = action.env;

  // The server replays its whole history to every new subscriber, and
  // EventSource reconnects on its own. Without this guard a dropped connection
  // replays the entire run and every event is applied twice.
  if (env.seq <= state.lastSeq) return state;

  const next: RunState = {
    ...state,
    lastSeq: env.seq,
    eventCounts: {
      ...state.eventCounts,
      [env.type]: (state.eventCounts[env.type] ?? 0) + 1,
    },
    feed: BEAT_TYPES.has(env.type)
      ? (state.feed.length >= MAX_FEED
          ? [...state.feed.slice(1), env]
          : [...state.feed, env])
      : state.feed,
  };

  switch (env.type) {
    case "status": {
      const d = env.data as SseEnvelope<"status">["data"];
      next.status = d.status;
      if (d.abort_reason) next.abortReason = d.abort_reason;
      if (d.budget) next.budget = d.budget;
      // Any status event means the gate that was parked has been resolved.
      next.interrupt = null;
      break;
    }

    case "plan":
      next.plan = (env.data as SseEnvelope<"plan">["data"]).attacks;
      break;

    case "recon":
      next.recon = env.data as ReconProfile;
      break;

    case "transcript": {
      const { turns } = env.data as SseEnvelope<"transcript">["data"];
      if (!turns.length) break;
      // Each emission carries the full transcript for the attack in flight, so
      // the group is replaced rather than appended. A craft_probe refusal turn
      // carries no attack_id, hence the cursor-derived fallback key.
      const attackId =
        turns.find((t) => t.attack_id)?.attack_id ?? `attack_${state.cursor}`;
      next.turnsByAttack = { ...state.turnsByAttack, [attackId]: turns };
      next.attackOrder = state.attackOrder.includes(attackId)
        ? state.attackOrder
        : [...state.attackOrder, attackId];
      break;
    }

    case "cursor":
      next.cursor = (env.data as SseEnvelope<"cursor">["data"]).attack_idx;
      break;

    case "route": {
      const d = env.data as SseEnvelope<"route">["data"];
      next.routes = [...state.routes, { route: d.route, ts: env.ts }];
      break;
    }

    case "intercept":
      next.intercepts = [...state.intercepts, env.data as InterceptCall];
      break;

    case "finding": {
      const f = env.data as Finding;
      // verify emits the raw finding; score re-emits it with severity and
      // mitigation attached. Upserting shows it land, then gain its score.
      const i = state.findings.findIndex((x) => x.finding_id === f.finding_id);
      next.findings =
        i === -1
          ? [...state.findings, f]
          : state.findings.map((x, j) => (j === i ? { ...x, ...f } : x));
      break;
    }

    case "trace": {
      const t = env.data as TraceEntry;
      const traces = [...state.traces, t];
      next.traces = traces.length > MAX_TRACES ? traces.slice(-MAX_TRACES) : traces;
      break;
    }

    case "budget":
      next.budget = { ...state.budget, ...(env.data as Budget) };
      break;

    case "budget_warning":
      next.budget = { ...state.budget, ...(env.data as Budget) };
      next.budgetWarning = true;
      break;

    case "interrupt":
      next.interrupt = env.data as InterruptPayload;
      next.status = "paused_for_human";
      break;

    case "report":
      next.report = env.data as Report;
      break;

    case "error":
      next.error = (env.data as SseEnvelope<"error">["data"]).error;
      break;

    case "done":
      next.done = true;
      next.status = (env.data as SseEnvelope<"done">["data"]).status;
      next.connected = false;
      break;
  }

  return next;
}

const EVENT_TYPES: SseEventType[] = [
  "status", "plan", "recon", "transcript", "cursor", "route", "intercept",
  "finding", "trace", "budget", "budget_warning", "interrupt", "report",
  "error", "done",
];

export function useRunStream(runId: string | null) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!runId) return;
    dispatch({ kind: "reset" });

    const es = new EventSource(api.eventsUrl(runId));
    sourceRef.current = es;

    es.onopen = () => dispatch({ kind: "connected", value: true });
    es.onerror = () => dispatch({ kind: "connected", value: false });

    const handlers = EVENT_TYPES.map((type) => {
      const fn = (e: MessageEvent) => {
        let env: SseEnvelope;
        try {
          env = JSON.parse(e.data) as SseEnvelope;
        } catch {
          return; // a malformed frame must not kill the stream
        }
        dispatch({ kind: "event", env });
        if (env.type === "done") {
          // The server ends the response here. Left open, EventSource would
          // treat that as a drop and reconnect, replaying the run forever.
          es.close();
          sourceRef.current = null;
        }
      };
      es.addEventListener(type, fn as EventListener);
      return [type, fn] as const;
    });

    return () => {
      handlers.forEach(([type, fn]) =>
        es.removeEventListener(type, fn as EventListener),
      );
      es.close();
      sourceRef.current = null;
    };
  }, [runId]);

  const resume = useCallback(
    async (decision: boolean, notes = "") => {
      if (!runId) return;
      await api.resume(runId, decision, notes);
    },
    [runId],
  );

  const totals = useMemo(() => {
    const usd = state.traces.reduce((a, t) => a + (t.usd ?? 0), 0);
    return {
      calls: state.traces.length,
      // Prefer the authoritative server figure; fall back to summing traces.
      usd: state.budget?.usd_spent ?? usd,
      tokensIn: state.traces.reduce((a, t) => a + (t.tokens_in ?? 0), 0),
      tokensOut: state.traces.reduce((a, t) => a + (t.tokens_out ?? 0), 0),
    };
  }, [state.traces, state.budget]);

  return { state, resume, totals };
}
