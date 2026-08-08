"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { BudgetMeter } from "@/components/BudgetMeter";
import { ViewToggle } from "@/components/ViewToggle";
import { FindingsStrip } from "@/components/engagement/FindingsStrip";
import { HoldOverlay } from "@/components/engagement/HoldOverlay";
import { OpsLog } from "@/components/engagement/OpsLog";
import { Stage } from "@/components/engagement/Stage";
import { Badge, Button, Code, KV } from "@/components/ui";
import { PROVENANCE_NOTE, compactUsd, prettyCategory, severityTone, toneClass } from "@/lib/format";
import { useEngagement } from "@/lib/useEngagement";
import { useRunStream } from "@/lib/useRunStream";
import type { Finding, RunStatus } from "@/lib/types";

const STATUS_TONE: Record<RunStatus, "accent" | "med" | "good" | "crit"> = {
  running: "accent",
  paused_for_human: "med",
  completed: "good",
  aborted: "crit",
};

export default function EngagementPage() {
  const params = useParams<{ runId: string }>();
  const runId = params?.runId ?? null;
  const { state, resume, totals } = useRunStream(runId);
  const engagement = useEngagement(state, runId);
  const [selected, setSelected] = useState<Finding | null>(null);

  const paused = state.interrupt !== null;
  const targetId =
    state.interrupt?.gate === "run_start"
      ? state.interrupt.target_id
      : (state.report?.target_id ?? "target");

  return (
    <main className="flex h-dvh flex-col overflow-hidden">
      <header className="flex shrink-0 items-center gap-3 border-b border-line bg-surface px-4 py-2.5">
        <Link
          href="/"
          className="flex items-center gap-2 font-mono text-[13px] font-bold text-ink transition hover:text-accent"
        >
          <span className="inline-block size-1.5 rounded-full bg-accent" />
          Sentinel
        </Link>

        {runId ? <ViewToggle runId={runId} active="engagement" /> : null}

        <span className="font-mono text-[10px] text-ink-mute">{runId}</span>
        <Badge tone={STATUS_TONE[state.status]}>{state.status.replace(/_/g, " ")}</Badge>

        {engagement.backlog > 3 && !paused ? (
          <span className="font-mono text-[9px] text-ink-mute" title="Stage is catching up to the live stream">
            +{engagement.backlog} queued
          </span>
        ) : null}
        {!state.connected && !state.done ? (
          <span className="font-mono text-[10px] text-med">reconnecting…</span>
        ) : null}

        <div className="ml-auto">
          <BudgetMeter
            budget={state.budget}
            calls={totals.calls}
            tokensIn={totals.tokensIn}
            tokensOut={totals.tokensOut}
          />
        </div>
      </header>

      {state.budgetWarning ? (
        <div className="shrink-0 border-b border-med/30 bg-med/10 px-4 py-1.5">
          <p className="font-mono text-[11px] text-med">
            Budget soft warning crossed — past {compactUsd(state.budget?.usd_warn ?? 0)} of the{" "}
            {compactUsd(state.budget?.usd_cap ?? 0)} hard cap.
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
          <p className="wrap-any font-mono text-[11px] text-crit">aborted: {state.abortReason}</p>
        </div>
      ) : null}

      <div className="grid min-h-0 flex-1 gap-2 p-2 lg:grid-cols-[minmax(0,1fr)_23rem]">
        <div className="relative flex min-h-0 flex-col gap-2">
          <div className="relative min-h-0 flex-1">
            <Stage
              stage={engagement.stage}
              current={engagement.current}
              budget={state.budget}
              targetId={targetId}
              charging={engagement.charging}
              paused={paused}
            />
            {/* Keyed so each gate mounts clean rather than inheriting notes. */}
            <HoldOverlay
              key={state.interrupt?.gate ?? "no-gate"}
              payload={state.interrupt}
              onResolve={async (approved, notes) => {
                await resume(approved, notes);
              }}
            />
          </div>

          <FindingsStrip
            findings={state.findings}
            budget={state.budget}
            onSelect={setSelected}
          />
        </div>

        <OpsLog state={state} />
      </div>

      {selected ? (
        <FindingDrawer finding={selected} onClose={() => setSelected(null)} />
      ) : null}
    </main>
  );
}

/** Visual → evidence. The strip is the hook; this is the auditable detail. */
function FindingDrawer({ finding: f, onClose }: { finding: Finding; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-bg/70 backdrop-blur-sm" onClick={onClose}>
      <aside
        className="enter flex h-full w-full max-w-md flex-col overflow-hidden border-l border-line bg-surface"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex shrink-0 items-center gap-2 border-b border-line bg-surface-2 px-4 py-3">
          <span
            className={`rounded border px-1.5 py-0.5 font-mono text-[12px] font-bold tabular-nums ${toneClass(severityTone(f.severity))}`}
          >
            {f.severity?.toFixed(1) ?? "—"}
          </span>
          <h2 className="font-mono text-[12px] font-semibold text-ink">
            {prettyCategory(f.attack_category)}
          </h2>
          <Button variant="ghost" className="ml-auto" onClick={onClose}>
            Close
          </Button>
        </header>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
          <div className="flex flex-wrap gap-1">
            <Badge tone={f.confirmed ? "crit" : "med"}>
              {f.confirmed ? "◆ confirmed" : "◇ unconfirmed"}
            </Badge>
            <Badge tone="mute">{f.provenance}</Badge>
          </div>

          {f.provenance !== "live" ? (
            <p className="rounded border border-med/30 bg-med/5 px-2.5 py-1.5 text-[10px] leading-snug text-med">
              {PROVENANCE_NOTE[f.provenance]}
            </p>
          ) : null}

          {f.impact_explanation ? (
            <Section label="impact">
              <p className="text-[11px] leading-relaxed text-ink-dim">{f.impact_explanation}</p>
            </Section>
          ) : null}

          {f.severity_formula ? (
            <Section label="severity formula">
              <Code>{f.severity_formula}</Code>
            </Section>
          ) : null}

          <Section label="minimized trigger">
            <Code>{f.minimized_prompt || "(not minimized)"}</Code>
          </Section>

          <Section label="verification">
            <KV k="status" v={f.confirmation_note} />
            <KV
              k="reruns"
              v={`${f.verify_reruns} at temperature ${f.verify_temperature} · ${(f.reproducibility * 100).toFixed(0)}% reproduced`}
            />
          </Section>

          {f.corroborating_call ? (
            <Section label="interceptor corroboration">
              <div className="rounded border border-crit/40 bg-crit/5 px-2.5 py-2">
                <p className="wrap-any font-mono text-[11px] text-ink">
                  {f.corroborating_call.tool_name}({JSON.stringify(f.corroborating_call.arguments)})
                </p>
                {f.corroborating_call.flag_reason ? (
                  <p className="mt-1 text-[10px] text-crit/90">{f.corroborating_call.flag_reason}</p>
                ) : null}
              </div>
            </Section>
          ) : null}

          {f.poc_log?.length ? (
            <Section label="proof-of-concept log">
              <ol className="space-y-1.5">
                {f.poc_log.map((s) => (
                  <li key={s.step} className="flex gap-2">
                    <span className="shrink-0 font-mono text-[10px] text-ink-mute tabular-nums">
                      {String(s.step).padStart(2, "0")}
                    </span>
                    <div className="min-w-0">
                      <p className="font-mono text-[10px] tracking-wide text-accent-dim uppercase">
                        {s.action}
                      </p>
                      {s.probe ? (
                        <p className="wrap-any font-mono text-[10px] text-ink-dim">→ {s.probe}</p>
                      ) : null}
                      {s.detail ? (
                        <p className="wrap-any text-[10px] text-ink-mute">{s.detail}</p>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ol>
            </Section>
          ) : null}

          {f.mitigation ? (
            <Section label="suggested mitigation">
              <div className="rounded border border-good/30 bg-good/5 px-2.5 py-2">
                <p className="wrap-any text-[11px] leading-relaxed whitespace-pre-wrap text-ink-dim">
                  {f.mitigation}
                </p>
              </div>
            </Section>
          ) : null}
        </div>
      </aside>
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1 font-mono text-[10px] tracking-[0.12em] text-ink-mute uppercase">
        {label}
      </p>
      {children}
    </div>
  );
}
