"use client";

import { useEffect, useMemo, useState } from "react";
import type {
  AttackCategory,
  Classification,
  Finding,
  InterceptCall,
  PlannedAttack,
  ReconProfile,
  Route,
  SseEnvelope,
  Turn,
} from "./types";
import type { RunState } from "./useRunStream";

/**
 * Turns the SSE feed into a paced sequence of engagement beats.
 *
 * Two facts about the stream shape this:
 *
 *  - `transcript` fires twice per turn - once when send_to_target appends the
 *    probe/response pair, once when judge_outcome annotates it with a verdict.
 *    That is already "shot fired" then "hit or deflect"; the cadence is real,
 *    not invented.
 *  - Timing is useless raw. Offline the whole run lands in milliseconds; live,
 *    Opus 5 at high effort takes 10-30s per probe. So beats are played on our
 *    own clock, compressing when a backlog builds and fast-forwarding when a
 *    client joins mid-run (the server replays full history to every subscriber).
 */

export type Beat =
  | { kind: "recon"; profile: ReconProfile }
  | { kind: "plan"; attacks: PlannedAttack[] }
  | { kind: "fire"; attackId: string; category: AttackCategory; turn: number; probe: string; facet: string }
  | { kind: "resolve"; attackId: string; category: AttackCategory; turn: number; classification: Classification; confidence: number; facet: string }
  | { kind: "intercept"; call: InterceptCall }
  | { kind: "route"; route: Route }
  | { kind: "verify"; finding: Finding; first: boolean }
  | { kind: "gate"; gate: string }
  | { kind: "end"; status: string };

/** Base milliseconds per beat before catch-up compression. */
const DURATION: Record<Beat["kind"], number> = {
  recon: 700,
  plan: 900,
  fire: 850,
  resolve: 700,
  intercept: 600,
  route: 420,
  verify: 2400,
  gate: 300,
  end: 400,
};

/** Shield strength a facet starts at, by observed refusal posture. */
const START_INTEGRITY: Record<string, number> = {
  hard_block: 1,
  soft_hedge: 0.55,
  no_refusal: 0.18,
};

/** How much a verdict moves a facet. Deflections recover a little. */
const INTEGRITY_DELTA: Record<Classification, number> = {
  succeeded: -0.5,
  partial: -0.22,
  failed: +0.06,
  refused_differently: -0.05,
};

export interface Facet {
  key: string;
  posture: string;
  integrity: number;
  breached: boolean;
}

export interface Lock {
  findingId: string;
  category: AttackCategory;
  confirmed: boolean;
  severity?: number;
  corroborated: boolean;
}

export interface Stage {
  facets: Facet[];
  /** The shot in flight, if the current beat is a fire. */
  beam: { category: AttackCategory; facet: string; probe: string } | null;
  lastResolve: { classification: Classification; confidence: number; facet: string } | null;
  locks: Lock[];
  plan: PlannedAttack[];
  activeAttackId: string | null;
  turnsFired: number;
  hits: number;
  deflected: number;
  route: Route | null;
  /** Set while a verify volley is playing, so reruns render as rapid shots. */
  verifying: Finding | null;
}

function buildBeats(feed: SseEnvelope[]): Beat[] {
  const beats: Beat[] = [];
  const seenTurn = new Set<string>();
  const seenFinding = new Set<string>();
  const seenIntercept = new Set<string>();
  let facetByAttack: Record<string, string> = {};

  for (const env of feed) {
    switch (env.type) {
      case "recon":
        beats.push({ kind: "recon", profile: env.data as ReconProfile });
        break;

      case "plan": {
        const attacks = (env.data as SseEnvelope<"plan">["data"]).attacks;
        facetByAttack = Object.fromEntries(
          attacks.map((a) => [a.id, a.target_facet ?? ""]),
        );
        beats.push({ kind: "plan", attacks });
        break;
      }

      case "transcript": {
        const { turns } = env.data as SseEnvelope<"transcript">["data"];
        // Only the newest turn can have changed; earlier ones already produced
        // their beats and are deduped by key below.
        for (const t of turns as Turn[]) {
          if (!t.probe) continue; // attacker-refusal turns carry no shot
          const base = `${t.attack_id}:${t.turn}`;
          const facet = facetByAttack[t.attack_id] ?? "";
          if (!seenTurn.has(`${base}:fire`)) {
            seenTurn.add(`${base}:fire`);
            beats.push({
              kind: "fire",
              attackId: t.attack_id,
              category: t.category,
              turn: t.turn,
              probe: t.probe,
              facet,
            });
          }
          if (t.verdict && !seenTurn.has(`${base}:resolve`)) {
            seenTurn.add(`${base}:resolve`);
            beats.push({
              kind: "resolve",
              attackId: t.attack_id,
              category: t.category,
              turn: t.turn,
              classification: t.verdict.classification,
              confidence: t.verdict.confidence,
              facet,
            });
          }
        }
        break;
      }

      case "intercept": {
        const call = env.data as InterceptCall;
        const key = `${call.attack_id}:${call.turn}:${call.tool_name}:${call.ts}`;
        if (!seenIntercept.has(key)) {
          seenIntercept.add(key);
          beats.push({ kind: "intercept", call });
        }
        break;
      }

      case "route":
        beats.push({ kind: "route", route: (env.data as SseEnvelope<"route">["data"]).route });
        break;

      case "finding": {
        // verify emits the finding, score re-emits it enriched with severity and
        // mitigation. Both are shown - the second is where the score lands - but
        // only the first gets the full volley dwell.
        const f = env.data as Finding;
        const first = !seenFinding.has(f.finding_id);
        if (first) seenFinding.add(f.finding_id);
        beats.push({ kind: "verify", finding: f, first });
        break;
      }

      case "interrupt":
        beats.push({ kind: "gate", gate: (env.data as { gate: string }).gate });
        break;

      case "done":
        beats.push({ kind: "end", status: (env.data as { status: string }).status });
        break;
    }
  }
  return beats;
}

function reduceStage(beats: Beat[], recon: ReconProfile | null): Stage {
  const stage: Stage = {
    facets: [],
    beam: null,
    lastResolve: null,
    locks: [],
    plan: [],
    activeAttackId: null,
    turnsFired: 0,
    hits: 0,
    deflected: 0,
    route: null,
    verifying: null,
  };

  // Shields are the recon profile rendered: each refusal-map topic is a facet,
  // and a soft hedge starts weaker because that is literally the attack surface.
  const map = recon?.refusal_map ?? {};
  const integrity: Record<string, number> = {};
  const breached: Record<string, boolean> = {};
  for (const [key, posture] of Object.entries(map)) {
    integrity[key] = START_INTEGRITY[posture] ?? 0.6;
    breached[key] = false;
  }

  for (const b of beats) {
    switch (b.kind) {
      case "plan":
        stage.plan = b.attacks;
        break;
      case "fire":
        stage.beam = { category: b.category, facet: b.facet, probe: b.probe };
        stage.activeAttackId = b.attackId;
        stage.turnsFired += 1;
        break;
      case "resolve": {
        stage.beam = null;
        stage.lastResolve = {
          classification: b.classification,
          confidence: b.confidence,
          facet: b.facet,
        };
        if (b.classification === "succeeded") stage.hits += 1;
        else if (b.classification === "failed") stage.deflected += 1;
        if (b.facet && b.facet in integrity) {
          integrity[b.facet] = Math.max(
            0,
            Math.min(1, integrity[b.facet] + INTEGRITY_DELTA[b.classification]),
          );
        }
        break;
      }
      case "route":
        stage.route = b.route;
        break;
      case "verify": {
        const f = b.finding;
        stage.verifying = f;
        if (f.confirmed && f.attack_category) {
          const facet = stage.plan.find((p) => p.id === f.attack_id)?.target_facet;
          if (facet && facet in breached) {
            breached[facet] = true;
            integrity[facet] = 0;
          }
        }
        const i = stage.locks.findIndex((l) => l.findingId === f.finding_id);
        const lock: Lock = {
          findingId: f.finding_id,
          category: f.attack_category,
          confirmed: f.confirmed,
          severity: f.severity,
          corroborated: f.corroborated_by_interceptor,
        };
        if (i === -1) stage.locks = [...stage.locks, lock];
        else stage.locks = stage.locks.map((l, j) => (j === i ? { ...l, ...lock } : l));
        break;
      }
      case "end":
        stage.beam = null;
        stage.verifying = null;
        break;
    }
  }

  stage.facets = Object.entries(map).map(([key, posture]) => ({
    key,
    posture,
    integrity: integrity[key] ?? 0.6,
    breached: breached[key] ?? false,
  }));
  return stage;
}

/** Playback speed as a coarse tier rather than a raw backlog number. */
type Tier = "sync" | "fast" | "brisk" | "normal";
const TIER_SPEED: Record<Tier, number> = {
  sync: 0.12,   // a gate is parked - catch the visual up to the decision point
  fast: 0.12,   // joined mid-run, or a large burst
  brisk: 0.4,
  normal: 1,
};

export function useEngagement(state: RunState, runId: string | null) {
  const beats = useMemo(() => buildBeats(state.feed), [state.feed]);
  const [played, setPlayed] = useState(0);

  // Switching between runs reuses this component, so the playhead is reset
  // during render rather than in an effect - the render-phase reset avoids a
  // frame where the new run is drawn with the old run's beats applied.
  const [prevRunId, setPrevRunId] = useState(runId);
  if (runId !== prevRunId) {
    setPrevRunId(runId);
    setPlayed(0);
  }

  const total = beats.length;
  const backlog = Math.max(0, total - played);
  const gatePending = state.interrupt !== null;

  const tier: Tier = gatePending
    ? "sync"
    : backlog > 14
      ? "fast"
      : backlog > 6
        ? "brisk"
        : "normal";

  // Depend only on primitives that change rarely. `beats` is rebuilt on every
  // event, and depending on its identity (or on raw backlog) would restart the
  // in-flight timer on each arrival and stall playback under a burst.
  const next = played < total ? beats[played] : null;
  const nextKind: Beat["kind"] | null = next?.kind ?? null;
  // The scored re-emission of a finding updates the card rather than replaying
  // the whole volley, so it gets a shorter dwell than the first arrival.
  const nextBase =
    next === null
      ? 0
      : next.kind === "verify" && !next.first
        ? 700
        : DURATION[next.kind];

  useEffect(() => {
    if (nextKind === null) return;
    const ms = Math.max(70, nextBase * TIER_SPEED[tier]);
    const timer = setTimeout(() => setPlayed((p) => p + 1), ms);
    return () => clearTimeout(timer);
  }, [played, nextKind, nextBase, tier]);

  const stage = useMemo(
    () => reduceStage(beats.slice(0, played), state.recon),
    [beats, played, state.recon],
  );

  const current = played > 0 ? beats[played - 1] : null;

  return {
    stage,
    current,
    played,
    total,
    backlog,
    /** True while the graph is working and no beat is mid-flight. */
    charging: backlog === 0 && !state.done && state.status === "running",
  };
}
