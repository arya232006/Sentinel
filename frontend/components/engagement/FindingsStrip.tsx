"use client";

import {
  PROVENANCE_NOTE,
  categoryColor,
  compactUsd,
  prettyCategory,
  provenanceTone,
  severityLabel,
  severityTone,
  toneClass,
} from "@/lib/format";
import type { Budget, Finding } from "@/lib/types";
import { Badge } from "../ui";

/**
 * The end state: engagement freezes, evidence surfaces. Each card is a lock
 * that survived verification, ordered by severity.
 */
export function FindingsStrip({
  findings,
  budget,
  onSelect,
}: {
  findings: Finding[];
  budget: Budget | null;
  onSelect: (f: Finding) => void;
}) {
  const sorted = [...findings].sort((a, b) => (b.severity ?? 0) - (a.severity ?? 0));
  const confirmed = sorted.filter((f) => f.confirmed).length;

  return (
    <section className="flex shrink-0 items-stretch gap-2 overflow-x-auto rounded-lg border border-line bg-surface px-2.5 py-2">
      <div className="flex shrink-0 flex-col justify-center pr-3">
        <span className="font-mono text-[10px] tracking-[0.16em] text-ink-dim uppercase">
          findings
        </span>
        <span className="font-mono text-[10px] text-ink-mute tabular-nums">
          {confirmed} confirmed / {sorted.length}
        </span>
        {budget ? (
          <span className="font-mono text-[10px] text-ink-mute tabular-nums">
            {compactUsd(budget.usd_spent)} / {compactUsd(budget.usd_cap)}
          </span>
        ) : null}
      </div>

      {sorted.length === 0 ? (
        <p className="flex items-center font-mono text-[10px] text-ink-mute">
          No findings yet — a bypass becomes a finding only after it reproduces.
        </p>
      ) : (
        sorted.map((f) => (
          <button
            key={f.finding_id}
            onClick={() => onSelect(f)}
            title={PROVENANCE_NOTE[f.provenance]}
            className="enter flex w-56 shrink-0 flex-col gap-1 rounded border border-line bg-surface-2/60 px-2.5 py-2 text-left transition hover:border-ink-mute"
          >
            <div className="flex items-center gap-1.5">
              <span
                className={`rounded border px-1 py-0.5 font-mono text-[10px] font-bold tabular-nums ${toneClass(severityTone(f.severity))}`}
              >
                {f.severity?.toFixed(1) ?? "—"}
              </span>
              <span
                className="truncate font-mono text-[10px]"
                style={{ color: categoryColor(f.attack_category) }}
              >
                {prettyCategory(f.attack_category)}
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-1">
              <Badge tone={f.confirmed ? "crit" : "med"}>
                {f.confirmed ? "◆ confirmed" : "◇ unconfirmed"}
              </Badge>
              <Badge tone={provenanceTone(f.provenance)}>{f.provenance}</Badge>
            </div>

            <p className="wrap-any line-clamp-2 font-mono text-[9px] leading-snug text-ink-mute">
              {f.minimized_prompt || f.trigger_probe}
            </p>
            <span className="font-mono text-[9px] text-ink-mute tabular-nums">
              {severityLabel(f.severity)} · repro {(f.reproducibility * 100).toFixed(0)}%
            </span>
          </button>
        ))
      )}
    </section>
  );
}
