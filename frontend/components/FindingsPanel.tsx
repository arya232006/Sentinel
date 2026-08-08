"use client";

import { useState } from "react";
import { Badge, Code, Empty, KV, Panel } from "./ui";
import {
  PROVENANCE_NOTE,
  prettyCategory,
  provenanceTone,
  severityLabel,
  severityTone,
  statusTone,
  verdictTone,
} from "@/lib/format";
import type { Finding } from "@/lib/types";

export function FindingsPanel({
  findings,
  running,
}: {
  findings: Finding[];
  running: boolean;
}) {
  const confirmed = findings.filter((f) => f.confirmed).length;

  return (
    <Panel
      title="Findings"
      subtitle={
        findings.length
          ? `${confirmed} confirmed of ${findings.length}`
          : undefined
      }
    >
      {findings.length === 0 ? (
        <Empty>
          {running
            ? "Findings appear once verification runs. A successful probe becomes a finding only after it reproduces across reruns."
            : "No findings were produced. The target held the line against every planned attack."}
        </Empty>
      ) : (
        <ul className="divide-y divide-line-soft">
          {[...findings]
            .sort((a, b) => (b.severity ?? 0) - (a.severity ?? 0))
            .map((f) => (
              <FindingCard key={f.finding_id} finding={f} />
            ))}
        </ul>
      )}
    </Panel>
  );
}

function FindingCard({ finding: f }: { finding: Finding }) {
  const [open, setOpen] = useState(false);
  const tone = severityTone(f.severity);
  const scored = f.severity !== undefined;

  return (
    <li className="enter">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start gap-2.5 px-3 py-2.5 text-left transition hover:bg-surface-2/50"
      >
        <SeverityChip severity={f.severity} />

        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-[12px] font-semibold text-ink">
              {prettyCategory(f.attack_category)}
            </span>
            {/* The confirmation rule, made visible: a tool finding says
                "confirmed" only when the interceptor agreed. */}
            <Badge tone={statusTone(f.status)} title={f.confirmation_note}>
              {f.status.replace(/_/g, " ")}
            </Badge>
            <Badge tone={provenanceTone(f.provenance)} title={PROVENANCE_NOTE[f.provenance]}>
              {f.provenance}
            </Badge>
          </div>

          <p className="wrap-any font-mono text-[11px] leading-snug text-ink-dim">
            {f.minimized_prompt || f.trigger_probe}
          </p>

          <div className="mt-1 flex flex-wrap items-center gap-2 font-mono text-[10px] text-ink-mute">
            <span>
              repro {(f.reproducibility * 100).toFixed(0)}% ({f.verify_reruns} reruns)
            </span>
            {f.corroborated_by_interceptor ? (
              <span className="text-crit">interceptor corroborated</span>
            ) : null}
            {f.minimization_steps > 0 ? <span>minimized in {f.minimization_steps} steps</span> : null}
            {!scored ? <span className="text-med">scoring…</span> : null}
          </div>
        </div>

        <span className="mt-1 font-mono text-[10px] text-ink-mute">{open ? "−" : "+"}</span>
      </button>

      {open ? <FindingDetail finding={f} tone={tone} /> : null}
    </li>
  );
}

function SeverityChip({ severity }: { severity?: number }) {
  const tone = severityTone(severity);
  const map = {
    crit: "border-crit/40 bg-crit/10 text-crit",
    high: "border-high/40 bg-high/10 text-high",
    med: "border-med/40 bg-med/10 text-med",
    low: "border-low/40 bg-low/10 text-low",
    good: "border-good/40 bg-good/10 text-good",
    info: "border-info/40 bg-info/10 text-info",
    accent: "border-accent/40 bg-accent/10 text-accent",
    mute: "border-line bg-surface-2 text-ink-mute",
  }[tone];

  return (
    <span
      className={`flex size-10 shrink-0 flex-col items-center justify-center rounded border ${map}`}
      title={severityLabel(severity)}
    >
      <span className="font-mono text-[13px] leading-none font-bold tabular-nums">
        {severity === undefined ? "—" : severity.toFixed(1)}
      </span>
      <span className="mt-0.5 font-mono text-[8px] tracking-wide uppercase opacity-70">
        {severityLabel(severity).slice(0, 4)}
      </span>
    </span>
  );
}

function FindingDetail({ finding: f }: { finding: Finding; tone: string }) {
  return (
    <div className="space-y-3 border-t border-line-soft bg-bg/40 px-3 py-3">
      {f.provenance !== "live" ? (
        <div className="rounded border border-med/30 bg-med/5 px-2.5 py-1.5">
          <p className="text-[10px] leading-snug text-med">
            {PROVENANCE_NOTE[f.provenance]}
          </p>
        </div>
      ) : null}

      {f.impact_explanation ? (
        <div>
          <SectionLabel>impact</SectionLabel>
          <p className="text-[11px] leading-relaxed text-ink-dim">{f.impact_explanation}</p>
          {f.blast_radius_notes ? (
            <p className="mt-1 text-[11px] leading-relaxed text-ink-mute">
              {f.blast_radius_notes}
            </p>
          ) : null}
        </div>
      ) : null}

      {/* The formula is the auditable answer to "why is this a 7.2?" */}
      {f.severity_formula ? (
        <div>
          <SectionLabel>severity formula</SectionLabel>
          <Code>{f.severity_formula}</Code>
        </div>
      ) : null}

      <div>
        <SectionLabel>minimized trigger</SectionLabel>
        <Code>{f.minimized_prompt || "(not minimized)"}</Code>
        {f.minimized_prompt && f.minimized_prompt !== f.trigger_probe ? (
          <details className="mt-1.5">
            <summary className="cursor-pointer font-mono text-[10px] text-ink-mute">
              original trigger ({f.trigger_probe.length} chars →{" "}
              {f.minimized_prompt.length})
            </summary>
            <Code className="mt-1">{f.trigger_probe}</Code>
          </details>
        ) : null}
      </div>

      {f.corroborating_call ? (
        <div>
          <SectionLabel>interceptor corroboration</SectionLabel>
          <div className="rounded border border-crit/40 bg-crit/5 px-2.5 py-2">
            <p className="wrap-any font-mono text-[11px] text-ink">
              {f.corroborating_call.tool_name}(
              {JSON.stringify(f.corroborating_call.arguments)})
            </p>
            {f.corroborating_call.flag_reason ? (
              <p className="mt-1 text-[10px] leading-snug text-crit/90">
                {f.corroborating_call.flag_reason}
              </p>
            ) : null}
            <p className="mt-1 font-mono text-[10px] text-ink-mute">
              executed: {String(f.corroborating_call.executed)}
            </p>
          </div>
        </div>
      ) : null}

      <div>
        <SectionLabel>verification</SectionLabel>
        <KV k="status" v={f.confirmation_note} />
        <KV
          k="reruns"
          v={`${f.verify_reruns} at temperature ${f.verify_temperature} · ${(f.reproducibility * 100).toFixed(0)}% reproduced`}
        />
        {f.rerun_details?.length ? (
          <div className="mt-1 flex flex-wrap gap-1">
            {f.rerun_details.map((r, i) => (
              <Badge key={i} tone={verdictTone(r.classification)}>
                {r.classification.replace(/_/g, " ")}
              </Badge>
            ))}
          </div>
        ) : null}
      </div>

      {f.poc_log?.length ? (
        <div>
          <SectionLabel>proof-of-concept log</SectionLabel>
          <ol className="space-y-1.5">
            {f.poc_log.map((s) => (
              <li key={s.step} className="flex gap-2">
                <span className="shrink-0 font-mono text-[10px] text-ink-mute tabular-nums">
                  {String(s.step).padStart(2, "0")}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="font-mono text-[10px] tracking-wide text-accent-dim uppercase">
                    {s.action}
                  </p>
                  {s.probe ? (
                    <p className="wrap-any mt-0.5 font-mono text-[10px] text-ink-dim">
                      → {s.probe}
                    </p>
                  ) : null}
                  {s.target_response ? (
                    <p className="wrap-any mt-0.5 text-[10px] text-ink-mute">
                      ← {s.target_response}
                    </p>
                  ) : null}
                  {s.detail ? (
                    <p className="wrap-any mt-0.5 text-[10px] text-ink-mute">{s.detail}</p>
                  ) : null}
                </div>
              </li>
            ))}
          </ol>
        </div>
      ) : null}

      {f.mitigation ? (
        <div>
          <SectionLabel>suggested mitigation</SectionLabel>
          <div className="rounded border border-good/30 bg-good/5 px-2.5 py-2">
            <p className="wrap-any text-[11px] leading-relaxed whitespace-pre-wrap text-ink-dim">
              {f.mitigation}
            </p>
          </div>
        </div>
      ) : null}

      {f.withheld ? (
        <div>
          <SectionLabel>withheld by the attacker guardrail</SectionLabel>
          <p className="text-[10px] leading-snug text-med">{f.withheld}</p>
        </div>
      ) : null}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-1 font-mono text-[10px] tracking-[0.12em] text-ink-mute uppercase">
      {children}
    </p>
  );
}
