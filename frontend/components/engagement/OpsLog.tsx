"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { categoryCode, categoryColor, clockTime, prettyCategory, usd } from "@/lib/format";
import type { RunState } from "@/lib/useRunStream";
import type { Classification } from "@/lib/types";

/**
 * The secondary truth beside the visual. Built from the same events the stage
 * animates, but written out verbatim — node names, models, latencies, costs —
 * because that is what makes the engagement view credible rather than a toy.
 *
 * Deliberately built from `state`, not from played beats: the log should show
 * what has actually happened, even when the stage is still catching up.
 */

type Filter = "all" | "traces" | "findings" | "gates";

interface Line {
  id: string;
  ts: string;
  kind: "trace" | "finding" | "gate" | "probe" | "verdict" | "intercept" | "route" | "status";
  label: string;
  text: string;
  color?: string;
  tone?: "crit" | "med" | "good" | "accent" | "info" | "mute";
}

const VERDICT_TONE: Record<Classification, Line["tone"]> = {
  succeeded: "crit",
  partial: "med",
  failed: "good",
  refused_differently: "info",
};

const TONE_CLASS: Record<NonNullable<Line["tone"]>, string> = {
  crit: "text-crit",
  med: "text-med",
  good: "text-good",
  accent: "text-accent",
  info: "text-info",
  mute: "text-ink-mute",
};

function buildLines(state: RunState): Line[] {
  const lines: Line[] = [];

  for (const env of state.feed) {
    const ts = env.ts;
    switch (env.type) {
      case "recon":
        lines.push({ id: `r${env.seq}`, ts, kind: "status", label: "recon", text: "profile complete", tone: "accent" });
        break;
      case "plan": {
        const atks = (env.data as { attacks: { category: string }[] }).attacks;
        lines.push({
          id: `p${env.seq}`, ts, kind: "status", label: "plan",
          text: `${atks.length} attacks: ${atks.map((a) => categoryCode(a.category)).join(" ")}`,
          tone: "accent",
        });
        break;
      }
      case "transcript": {
        const { turns } = env.data as { turns: { probe: string; attack_id: string; category: string; turn: number; verdict?: { classification: Classification; confidence: number } }[] };
        const t = turns[turns.length - 1];
        if (!t?.probe) break;
        if (t.verdict) {
          lines.push({
            id: `v${env.seq}`, ts, kind: "verdict", label: "judge",
            text: `${t.verdict.classification.replace(/_/g, " ")} (${(t.verdict.confidence * 100).toFixed(0)}%) · ${t.attack_id} turn ${t.turn + 1}`,
            tone: VERDICT_TONE[t.verdict.classification],
          });
        } else {
          lines.push({
            id: `q${env.seq}`, ts, kind: "probe", label: "probe",
            text: `${categoryCode(t.category)} → ${t.probe.slice(0, 88)}${t.probe.length > 88 ? "…" : ""}`,
            color: categoryColor(t.category),
          });
        }
        break;
      }
      case "intercept": {
        const c = env.data as { tool_name: string; arguments: Record<string, unknown>; flagged: boolean; flag_reason: string | null };
        lines.push({
          id: `i${env.seq}`, ts, kind: "intercept",
          label: c.flagged ? "SENSOR" : "sensor",
          text: `${c.tool_name}(${JSON.stringify(c.arguments)})${c.flag_reason ? ` — ${c.flag_reason}` : ""}`,
          tone: c.flagged ? "crit" : "mute",
        });
        break;
      }
      case "route":
        lines.push({
          id: `t${env.seq}`, ts, kind: "route", label: "router",
          text: (env.data as { route: string }).route.replace(/_/g, " "),
          tone: "mute",
        });
        break;
      case "finding": {
        const f = env.data as { finding_id: string; attack_category: string; confirmed: boolean; severity?: number; reproducibility: number; corroborated_by_interceptor: boolean };
        lines.push({
          id: `f${env.seq}`, ts, kind: "finding", label: "FINDING",
          text:
            `${prettyCategory(f.attack_category)} · ${f.confirmed ? "confirmed" : "unconfirmed"}` +
            `${f.severity !== undefined ? ` · severity ${f.severity.toFixed(1)}` : ""}` +
            ` · repro ${(f.reproducibility * 100).toFixed(0)}%` +
            `${f.corroborated_by_interceptor ? " · interceptor agrees" : ""}`,
          tone: f.confirmed ? "crit" : "med",
        });
        break;
      }
      case "interrupt":
        lines.push({
          id: `g${env.seq}`, ts, kind: "gate", label: "GATE",
          text: `${(env.data as { gate: string }).gate.replace(/_/g, " ")} — awaiting authorization`,
          tone: "accent",
        });
        break;
      case "status": {
        const s = env.data as { status: string; abort_reason?: string | null };
        lines.push({
          id: `s${env.seq}`, ts, kind: "status", label: "status",
          text: s.abort_reason ? `${s.status} — ${s.abort_reason}` : s.status,
          tone: s.status === "aborted" ? "crit" : "mute",
        });
        break;
      }
    }
  }

  // Traces are not in the feed (they are high-volume and log-only), so they are
  // merged in from state and the whole lot re-sorted by timestamp.
  for (const [i, t] of state.traces.entries()) {
    lines.push({
      id: `x${i}`, ts: t.ts, kind: "trace", label: "trace",
      text: `${t.node} · ${t.model.replace(/^claude-/, "")} · ${t.latency_ms}ms · ${t.tokens_in}/${t.tokens_out} tok · ${usd(t.usd, 5)}${t.output?.refused ? " · REFUSED" : ""}`,
      tone: t.output?.refused ? "info" : "mute",
    });
  }

  lines.sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0));
  return lines;
}

const MATCHES: Record<Filter, (l: Line) => boolean> = {
  all: () => true,
  traces: (l) => l.kind === "trace",
  findings: (l) => l.kind === "finding" || l.kind === "intercept",
  gates: (l) => l.kind === "gate" || l.kind === "status",
};

export function OpsLog({ state }: { state: RunState }) {
  const [filter, setFilter] = useState<Filter>("all");
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const pinnedRef = useRef(true);

  const lines = useMemo(() => buildLines(state), [state]);
  const shown = useMemo(() => lines.filter(MATCHES[filter]), [lines, filter]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && pinnedRef.current) el.scrollTop = el.scrollHeight;
  }, [shown.length]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    pinnedRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 70;
  };

  return (
    <section className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-line bg-surface">
      <header className="flex shrink-0 items-center gap-2 border-b border-line bg-surface-2/60 px-2.5 py-1.5">
        <h2 className="font-mono text-[10px] font-semibold tracking-[0.16em] text-ink-dim uppercase">
          ops log
        </h2>
        <div role="group" aria-label="Log filter" className="ml-auto flex gap-0.5">
          {(["all", "traces", "findings", "gates"] as Filter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              aria-pressed={filter === f}
              className={`rounded px-1.5 py-0.5 font-mono text-[9px] tracking-wide uppercase transition ${
                filter === f
                  ? "bg-accent/15 text-accent"
                  : "text-ink-mute hover:text-ink-dim"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </header>

      <div ref={scrollRef} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto px-2 py-1.5">
        {shown.length === 0 ? (
          <p className="px-1 py-4 font-mono text-[10px] text-ink-mute">
            No entries yet.
          </p>
        ) : (
          <ul className="space-y-0.5">
            {shown.map((l) => (
              <li key={l.id} className="log-in flex gap-1.5 font-mono text-[10px] leading-relaxed">
                <span className="shrink-0 text-ink-mute tabular-nums">{clockTime(l.ts)}</span>
                <span
                  className={`w-14 shrink-0 ${l.tone ? TONE_CLASS[l.tone] : "text-ink-mute"}`}
                  style={l.color ? { color: l.color } : undefined}
                >
                  {l.label}
                </span>
                <span className="wrap-any min-w-0 flex-1 text-ink-dim">{l.text}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
