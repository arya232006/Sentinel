"use client";

import { useState } from "react";
import { Button, Code, Textarea } from "../ui";
import { categoryColor, prettyCategory, severityTone, toneClass, verdictTone } from "@/lib/format";
import type { InterruptPayload } from "@/lib/types";

/**
 * The gate, as a battlefield freeze. Same three interrupts and the same
 * consequences as the console's ApprovalModal — this is the cinematic skin,
 * not a second code path.
 *
 * Callers key this on the gate name so each interrupt mounts clean.
 */
const GATE_META: Record<
  InterruptPayload["gate"],
  { title: string; sub: string; reject: string; consequence: string }
> = {
  run_start: {
    title: "HUMAN HOLD",
    sub: "authorize engagement",
    reject: "Abort run",
    consequence: "Rejecting aborts the run before any probe is sent.",
  },
  severity_escalation: {
    title: "HUMAN HOLD",
    sub: "escalation to high-severity ordnance",
    reject: "Skip attack",
    consequence: "Rejecting skips to the next planned attack. The run continues.",
  },
  report_finalization: {
    title: "HUMAN HOLD",
    sub: "release findings",
    reject: "Reject report",
    consequence: "Rejecting aborts the run; cross-run pattern learning is not updated.",
  },
};

export function HoldOverlay({
  payload,
  onResolve,
}: {
  payload: InterruptPayload | null;
  onResolve: (approved: boolean, notes: string) => Promise<void>;
}) {
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!payload) return null;
  const meta = GATE_META[payload.gate];

  const resolve = async (approved: boolean) => {
    setBusy(true);
    setError(null);
    try {
      await onResolve(approved, notes);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  return (
    <div className="absolute inset-0 z-40 flex items-center justify-center bg-bg/80 p-4 backdrop-blur-[3px]">
      <div className="enter w-full max-w-md overflow-hidden rounded-lg border border-med/50 bg-surface shadow-2xl shadow-black/70">
        {/* Hazard bar — the run really is parked server-side. */}
        <div className="flex items-center gap-2 border-b border-med/40 bg-med/10 px-4 py-2.5">
          <span className="hold-flash size-2 rounded-full bg-med" />
          <span className="font-mono text-[13px] font-bold tracking-[0.22em] text-med">
            {meta.title}
          </span>
          <span className="ml-auto font-mono text-[9px] tracking-[0.12em] text-med/80 uppercase">
            {meta.sub}
          </span>
        </div>

        <div className="max-h-[52vh] space-y-3 overflow-y-auto px-4 py-3">
          <p className="text-[12px] leading-relaxed text-ink-dim">{payload.prompt}</p>

          {payload.gate === "run_start" ? (
            <dl className="rounded border border-line bg-surface-2/50 px-3 py-2 font-mono text-[10px]">
              <Row k="target" v={payload.target_id} />
              <Row k="endpoint" v={payload.target_endpoint} />
              <Row k="authorizer" v={payload.authorizer} />
              <div className="mt-1.5 flex flex-wrap gap-1">
                {payload.allowed_categories.map((c) => (
                  <span
                    key={c}
                    className="rounded border border-current px-1 py-0.5 text-[9px]"
                    style={{ color: categoryColor(c) }}
                  >
                    {prettyCategory(c)}
                  </span>
                ))}
              </div>
            </dl>
          ) : null}

          {payload.gate === "severity_escalation" ? (
            <div className="space-y-2">
              <div
                className="rounded border px-3 py-2"
                style={{
                  borderColor: `${categoryColor(payload.category)}55`,
                  background: `${categoryColor(payload.category)}12`,
                }}
              >
                <p className="font-mono text-[11px]" style={{ color: categoryColor(payload.category) }}>
                  arming {prettyCategory(payload.category)}
                </p>
                <p className="mt-1 text-[10px] leading-snug text-ink-mute">
                  Fires once per category per run.
                </p>
              </div>
              {payload.verdict?.classification ? (
                <p className="font-mono text-[10px] text-ink-mute">
                  triggering verdict:{" "}
                  <span className={toneClass(verdictTone(payload.verdict.classification)).split(" ")[0]}>
                    {payload.verdict.classification.replace(/_/g, " ")}
                  </span>
                </p>
              ) : null}
              <p className="font-mono text-[10px] text-ink-mute tabular-nums">
                spend ${payload.budget.usd_spent.toFixed(4)} of ${payload.budget.usd_cap.toFixed(2)}
              </p>
            </div>
          ) : null}

          {payload.gate === "report_finalization" ? (
            <div className="space-y-1.5">
              <p className="font-mono text-[11px] text-ink-dim">
                {payload.finding_count} finding{payload.finding_count === 1 ? "" : "s"} pending release
              </p>
              <p className="text-[10px] leading-snug text-ink-mute">
                Last point to catch anything that surfaced real rather than simulated data.
              </p>
              {payload.findings_preview.map((f) => (
                <div key={f.finding_id} className="rounded border border-line bg-surface-2/50 px-2 py-1.5">
                  <div className="flex items-center gap-1.5">
                    <span
                      className={`rounded border px-1 font-mono text-[9px] font-bold ${toneClass(severityTone(f.severity))}`}
                    >
                      {f.severity?.toFixed(1) ?? "—"}
                    </span>
                    <span className="font-mono text-[10px]" style={{ color: categoryColor(f.category) }}>
                      {prettyCategory(f.category)}
                    </span>
                    {f.confirmed ? (
                      <span className="font-mono text-[9px] text-crit">◆ confirmed</span>
                    ) : null}
                  </div>
                  <Code className="mt-1">{f.minimized_prompt}</Code>
                </div>
              ))}
            </div>
          ) : null}

          <Textarea
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Notes (recorded with the decision)"
          />
          <p className="text-[10px] leading-snug text-ink-mute">{meta.consequence}</p>

          {error ? (
            <p className="rounded border border-crit/40 bg-crit/10 px-2 py-1.5 font-mono text-[10px] text-crit">
              {error}
            </p>
          ) : null}
        </div>

        <footer className="flex items-center gap-2 border-t border-line bg-surface-2 px-4 py-3">
          <Button variant="danger" disabled={busy} onClick={() => resolve(false)}>
            {meta.reject}
          </Button>
          <Button className="ml-auto" disabled={busy} onClick={() => resolve(true)}>
            {busy ? "Submitting…" : "Authorize"}
          </Button>
        </footer>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-2 py-0.5">
      <dt className="shrink-0 text-ink-mute">{k}</dt>
      <dd className="wrap-any min-w-0 text-ink-dim">{v}</dd>
    </div>
  );
}
