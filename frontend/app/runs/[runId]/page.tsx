"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ApprovalModal } from "@/components/ApprovalModal";
import { BudgetMeter } from "@/components/BudgetMeter";
import { FindingsPanel } from "@/components/FindingsPanel";
import { PlanPanel } from "@/components/PlanPanel";
import { TracePanel } from "@/components/TracePanel";
import { TranscriptPanel } from "@/components/TranscriptPanel";
import { ViewToggle } from "@/components/ViewToggle";
import { Badge, Button } from "@/components/ui";
import { useRunStream } from "@/lib/useRunStream";
import type { RunStatus } from "@/lib/types";
import { compactUsd } from "@/lib/format";

const STATUS_TONE: Record<RunStatus, "accent" | "med" | "good" | "crit"> = {
  running: "accent",
  paused_for_human: "med",
  completed: "good",
  aborted: "crit",
};

export default function RunPage() {
  const params = useParams<{ runId: string }>();
  const runId = params?.runId ?? null;
  const { state, resume, totals } = useRunStream(runId);
  const [traceOpen, setTraceOpen] = useState(true);

  const running = !state.done && state.status === "running";

  return (
    <main className="flex h-dvh flex-col overflow-hidden">
      <header className="flex shrink-0 items-center gap-4 border-b border-line bg-surface px-4 py-2.5">
        <Link
          href="/"
          className="flex items-center gap-2 font-mono text-[13px] font-bold text-ink transition hover:text-accent"
        >
          <span className="inline-block size-1.5 rounded-full bg-accent" />
          Sentinel
        </Link>

        {runId ? <ViewToggle runId={runId} active="console" /> : null}

        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-ink-mute">{runId}</span>
          <Badge tone={STATUS_TONE[state.status]}>
            {state.status.replace(/_/g, " ")}
          </Badge>
          {state.connected && running ? (
            <span className="flex items-center gap-1.5 font-mono text-[10px] text-ink-mute">
              <span className="size-1.5 rounded-full bg-accent live-dot" />
              streaming
            </span>
          ) : null}
          {!state.connected && !state.done ? (
            <span className="font-mono text-[10px] text-med">reconnecting…</span>
          ) : null}
        </div>

        <div className="ml-auto flex items-center gap-5">
          <BudgetMeter
            budget={state.budget}
            calls={totals.calls}
            tokensIn={totals.tokensIn}
            tokensOut={totals.tokensOut}
          />
          <Button variant="ghost" onClick={() => setTraceOpen((v) => !v)}>
            {traceOpen ? "Hide trace" : "Show trace"}
          </Button>
        </div>
      </header>

      {state.budgetWarning ? (
        <div className="shrink-0 border-b border-med/30 bg-med/10 px-4 py-1.5">
          <p className="font-mono text-[11px] text-med">
            Budget soft warning crossed — spend is past{" "}
            {compactUsd(state.budget?.usd_warn ?? 0)} of the{" "}
            {compactUsd(state.budget?.usd_cap ?? 0)} hard cap. The cap aborts the
            run; this is the lead time to stop it deliberately.
          </p>
        </div>
      ) : null}

      {state.error ? (
        <div className="shrink-0 border-b border-crit/40 bg-crit/10 px-4 py-1.5">
          <p className="wrap-any font-mono text-[11px] text-crit">{state.error}</p>
        </div>
      ) : null}

      {state.abortReason ? (
        <div className="shrink-0 border-b border-crit/30 bg-crit/5 px-4 py-1.5">
          <p className="wrap-any font-mono text-[11px] text-crit">
            aborted: {state.abortReason}
          </p>
        </div>
      ) : null}

      {state.report ? <ReportBar report={state.report} /> : null}

      <div className="grid min-h-0 flex-1 gap-2 p-2 lg:grid-cols-[19rem_minmax(0,1fr)_23rem]">
        <PlanPanel
          plan={state.plan}
          recon={state.recon}
          cursor={state.cursor}
          running={running}
        />
        <TranscriptPanel
          turnsByAttack={state.turnsByAttack}
          attackOrder={state.attackOrder}
          plan={state.plan}
          running={running}
        />
        <FindingsPanel findings={state.findings} running={running} />
      </div>

      {traceOpen ? (
        <div className="h-56 shrink-0 px-2 pb-2">
          <TracePanel
            traces={state.traces}
            routes={state.routes}
            running={running}
          />
        </div>
      ) : null}

      {/* Keyed on the gate so each interrupt mounts a clean modal rather than
          inheriting the previous gate's notes. */}
      <ApprovalModal
        key={state.interrupt?.gate ?? "no-gate"}
        payload={state.interrupt}
        onResolve={async (approved, notes) => {
          await resume(approved, notes);
        }}
      />
    </main>
  );
}

function ReportBar({
  report,
}: {
  report: NonNullable<ReturnType<typeof useRunStream>["state"]["report"]>;
}) {
  const s = report.summary;
  if (!s) return null;
  return (
    <div className="shrink-0 border-b border-good/25 bg-good/5 px-4 py-2">
      <div className="flex flex-wrap items-center gap-4">
        <span className="font-mono text-[11px] font-semibold text-good">
          report ready
        </span>
        <span className="font-mono text-[11px] text-ink-dim">
          {s.confirmed} confirmed of {s.total_findings} findings
        </span>
        <span className="font-mono text-[11px] text-ink-dim">
          max severity {s.max_severity?.toFixed(1)}
        </span>
        <span className="font-mono text-[11px] text-ink-mute">
          {compactUsd(s.budget_spent)} of {compactUsd(s.budget_cap)}
        </span>
      </div>
      {report.interceptor_limitation ? (
        <p className="mt-1 max-w-4xl text-[10px] leading-snug text-ink-mute">
          {report.interceptor_limitation}
        </p>
      ) : null}
    </div>
  );
}
