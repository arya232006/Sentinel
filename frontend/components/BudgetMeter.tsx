"use client";

import type { Budget } from "@/lib/types";
import { compactUsd, tokens, usd } from "@/lib/format";

/**
 * The running spend against the hard cap. DESIGN.md 15 calls this the most
 * persuasive evidence that the caps are real, so it stays visible at all times
 * rather than living in the trace panel.
 */
export function BudgetMeter({
  budget,
  calls,
  tokensIn,
  tokensOut,
}: {
  budget: Budget | null;
  calls: number;
  tokensIn: number;
  tokensOut: number;
}) {
  const spent = budget?.usd_spent ?? 0;
  const cap = budget?.usd_cap ?? 0;
  const warn = budget?.usd_warn;
  const pct = cap > 0 ? Math.min(100, (spent / cap) * 100) : 0;

  // Amber at the soft warning, red as the hard cap comes into view. The cap is
  // enforced pre-flight in budget.py; this only mirrors it.
  const warned = budget?.warned || (warn !== undefined && spent >= warn);
  const critical = cap > 0 && spent >= cap * 0.9;
  const barColor = critical ? "bg-crit" : warned ? "bg-med" : "bg-accent";
  const textColor = critical ? "text-crit" : warned ? "text-med" : "text-ink";

  return (
    <div className="flex min-w-52 flex-col gap-1">
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-mono text-[10px] tracking-[0.12em] text-ink-mute uppercase">
          spend
        </span>
        <span className={`font-mono text-[12px] font-semibold tabular-nums ${textColor}`}>
          {compactUsd(spent)}
          <span className="text-ink-mute"> / {compactUsd(cap)}</span>
        </span>
      </div>

      <div className="relative h-1.5 overflow-hidden rounded-full bg-surface-3">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${pct}%` }}
        />
        {/* Soft-warning tick, so the amber threshold is legible before it trips. */}
        {warn !== undefined && cap > 0 && warn < cap ? (
          <div
            className="absolute inset-y-0 w-px bg-ink-mute/50"
            style={{ left: `${(warn / cap) * 100}%` }}
            title={`soft warning at ${compactUsd(warn)}`}
          />
        ) : null}
      </div>

      <div className="flex justify-between font-mono text-[10px] text-ink-mute tabular-nums">
        <span>
          {calls} calls · {tokens(tokensIn)}↓ {tokens(tokensOut)}↑
        </span>
        <span title={`exact: ${usd(spent, 6)}`}>
          {budget?.profile ? `${budget.profile} profile` : "—"}
        </span>
      </div>
    </div>
  );
}
