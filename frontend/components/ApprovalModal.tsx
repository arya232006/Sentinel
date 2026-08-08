"use client";

import { useState } from "react";
import { Badge, Button, Code, KV, Textarea } from "./ui";
import { prettyCategory, severityTone, verdictTone } from "@/lib/format";
import type { InterruptPayload } from "@/lib/types";

/**
 * The three LangGraph interrupt points. Rejecting means something different at
 * each one, so the consequence is stated rather than left for the operator to
 * infer — see gates.py.
 */
const GATE_META: Record<
  InterruptPayload["gate"],
  { title: string; rejectLabel: string; consequence: string }
> = {
  run_start: {
    title: "Authorize this run",
    rejectLabel: "Reject run",
    consequence: "Rejecting aborts the run before any probe is sent.",
  },
  severity_escalation: {
    title: "Approve severity escalation",
    rejectLabel: "Skip this attack",
    consequence:
      "Rejecting skips to the next planned attack. The run continues.",
  },
  report_finalization: {
    title: "Finalize report",
    rejectLabel: "Reject report",
    consequence:
      "Rejecting aborts the run, and cross-run pattern learning is not updated.",
  },
};

export function ApprovalModal({
  payload,
  onResolve,
}: {
  payload: InterruptPayload | null;
  onResolve: (approved: boolean, notes: string) => Promise<void>;
}) {
  // Callers key this component on the gate name, so each gate mounts fresh and
  // cannot inherit the previous gate's notes, busy flag or error.
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg/85 p-4 backdrop-blur-sm">
      <div className="enter flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-lg border border-accent/30 bg-surface shadow-2xl shadow-black/60">
        <header className="flex items-center gap-2 border-b border-line bg-surface-2 px-4 py-3">
          <span className="size-1.5 rounded-full bg-accent live-dot" />
          <h2 className="font-mono text-[12px] font-semibold tracking-wide text-ink">
            {meta.title}
          </h2>
          <Badge tone="accent" className="ml-auto">
            {payload.gate.replace(/_/g, " ")}
          </Badge>
        </header>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
          <p className="text-[12px] leading-relaxed text-ink-dim">{payload.prompt}</p>

          {payload.gate === "run_start" ? (
            <div className="rounded border border-line bg-surface-2/50 px-3 py-2">
              <KV k="target" v={payload.target_id} />
              <KV k="endpoint" v={payload.target_endpoint} />
              <KV k="authorizer" v={payload.authorizer} />
              <div className="mt-1.5 flex flex-wrap gap-1">
                {payload.allowed_categories.map((c) => (
                  <Badge key={c} tone="low">{prettyCategory(c)}</Badge>
                ))}
              </div>
            </div>
          ) : null}

          {payload.gate === "severity_escalation" ? (
            <div className="space-y-2">
              <div className="rounded border border-med/30 bg-med/5 px-3 py-2">
                <p className="font-mono text-[11px] text-med">
                  escalating into {prettyCategory(payload.category)}
                </p>
                <p className="mt-1 text-[10px] leading-snug text-ink-mute">
                  This gate fires once per category per run.
                </p>
              </div>
              {payload.verdict?.classification ? (
                <div className="rounded border border-line bg-surface-2/50 px-3 py-2">
                  <div className="mb-1 flex items-center gap-2">
                    <span className="font-mono text-[10px] text-ink-mute">
                      triggering verdict
                    </span>
                    <Badge tone={verdictTone(payload.verdict.classification)}>
                      {payload.verdict.classification.replace(/_/g, " ")}
                    </Badge>
                  </div>
                  {payload.verdict.evidence_span ? (
                    <p className="wrap-any text-[10px] leading-snug text-ink-mute italic">
                      “{payload.verdict.evidence_span}”
                    </p>
                  ) : null}
                </div>
              ) : null}
              <KV
                k="spend"
                v={`$${payload.budget.usd_spent.toFixed(4)} of $${payload.budget.usd_cap.toFixed(2)}`}
              />
            </div>
          ) : null}

          {payload.gate === "report_finalization" ? (
            <div className="space-y-2">
              <p className="font-mono text-[11px] text-ink-dim">
                {payload.finding_count} finding
                {payload.finding_count === 1 ? "" : "s"} pending review
              </p>
              <p className="text-[10px] leading-snug text-ink-mute">
                Review before the report is marked shareable — this is the point
                to catch anything that surfaced real rather than simulated data.
              </p>
              <ul className="space-y-1.5">
                {payload.findings_preview.map((f) => (
                  <li
                    key={f.finding_id}
                    className="rounded border border-line bg-surface-2/50 px-2.5 py-1.5"
                  >
                    <div className="flex items-center gap-1.5">
                      <Badge tone={severityTone(f.severity)}>
                        {f.severity?.toFixed(1) ?? "—"}
                      </Badge>
                      <span className="font-mono text-[11px] text-ink">
                        {prettyCategory(f.category)}
                      </span>
                      {f.confirmed ? <Badge tone="crit">confirmed</Badge> : null}
                    </div>
                    <Code className="mt-1.5">{f.minimized_prompt}</Code>
                  </li>
                ))}
              </ul>
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
            <p className="rounded border border-crit/40 bg-crit/10 px-2.5 py-1.5 font-mono text-[11px] text-crit">
              {error}
            </p>
          ) : null}
        </div>

        <footer className="flex items-center gap-2 border-t border-line bg-surface-2 px-4 py-3">
          <Button variant="danger" disabled={busy} onClick={() => resolve(false)}>
            {meta.rejectLabel}
          </Button>
          <Button className="ml-auto" disabled={busy} onClick={() => resolve(true)}>
            {busy ? "Submitting…" : "Approve"}
          </Button>
        </footer>
      </div>
    </div>
  );
}
