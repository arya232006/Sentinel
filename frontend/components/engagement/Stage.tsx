"use client";

import { arcPath, categoryCode, categoryColor, prettyCategory } from "@/lib/format";
import type { Beat, Stage as StageState } from "@/lib/useEngagement";
import type { Budget, Classification } from "@/lib/types";

/**
 * The engagement stage.
 *
 * Nothing here is decorative: the target's shield facets ARE the recon
 * profile's refusal map, a facet's strength is its observed posture, and a
 * beam's colour is the attack category actually being fired. If the visual
 * shows a weak facet, recon really did report a soft hedge there.
 */

// Aspect is deliberately close to the pane it sits in (~1.6). A wider viewBox
// letterboxes into large dead bands once `meet` scales it to fit the width.
const W = 1000;
const H = 610;
const ATTACKER = { x: 205, y: 268 };
const TARGET = { x: 795, y: 268 };
const BEAM_FROM = ATTACKER.x + 70;
const BEAM_TO = TARGET.x - 128;
const BEAM_LEN = BEAM_TO - BEAM_FROM;

const RESOLVE_COLOR: Record<Classification, string> = {
  succeeded: "#ff4d5e",
  partial: "#ff8f3f",
  failed: "#35d07f",
  refused_differently: "#5b9cff",
};

const RESOLVE_LABEL: Record<Classification, string> = {
  succeeded: "BYPASS",
  partial: "PARTIAL",
  failed: "DEFLECTED",
  refused_differently: "REROUTED",
};

export function Stage({
  stage,
  current,
  budget,
  targetId,
  charging,
  paused,
}: {
  stage: StageState;
  current: Beat | null;
  budget: Budget | null;
  targetId: string;
  charging: boolean;
  paused: boolean;
}) {
  const firing = current?.kind === "fire" ? current : null;
  const resolving = current?.kind === "resolve" ? current : null;
  const intercepting = current?.kind === "intercept" ? current : null;

  const beamColor = categoryColor(
    firing?.category ?? stage.beam?.category ?? stage.lastResolve?.facet ?? "",
  );

  const spent = budget?.usd_spent ?? 0;
  const cap = budget?.usd_cap ?? 0;
  const budgetPct = cap > 0 ? Math.min(1, spent / cap) : 0;

  return (
    <div className="relative h-full w-full overflow-hidden rounded-lg border border-line bg-bg">
      <div className="bg-grid absolute inset-0 opacity-40" aria-hidden />

      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="relative h-full w-full"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`Engagement view: SENTINEL-1 versus ${targetId}. ${stage.hits} bypasses, ${stage.deflected} deflected.`}
      >
        <defs>
          <radialGradient id="atkGlow">
            <stop offset="0%" stopColor="#2ee6cd" stopOpacity="0.5" />
            <stop offset="100%" stopColor="#2ee6cd" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="tgtGlow">
            <stop offset="0%" stopColor="#5b9cff" stopOpacity="0.34" />
            <stop offset="100%" stopColor="#5b9cff" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="beamGrad" x1="0" x2="1">
            <stop offset="0%" stopColor={beamColor} stopOpacity="0" />
            <stop offset="35%" stopColor={beamColor} stopOpacity="0.85" />
            <stop offset="100%" stopColor={beamColor} stopOpacity="1" />
          </linearGradient>
          <filter id="soften" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="5" />
          </filter>
        </defs>

        {/* ---------------------------------------------------------- axis --- */}
        <line
          x1={BEAM_FROM} y1={ATTACKER.y} x2={BEAM_TO} y2={ATTACKER.y}
          stroke="#1f242e" strokeWidth={1} strokeDasharray="3 7"
        />

        {/* ------------------------------------------------------ attacker --- */}
        <g>
          <circle cx={ATTACKER.x} cy={ATTACKER.y} r={126} fill="url(#atkGlow)" />
          {charging && !paused ? (
            <circle
              cx={ATTACKER.x} cy={ATTACKER.y} r={74}
              fill="none" stroke="#2ee6cd" strokeWidth={1.5}
              className="charge-pulse"
            />
          ) : null}

          {/* Budget ring: real spend against the hard cap the graph enforces. */}
          <BudgetRing cx={ATTACKER.x} cy={ATTACKER.y} r={60} pct={budgetPct} warned={!!budget?.warned} />

          {/* Attacker mark: a forward chevron, abstract rather than a craft. */}
          <path
            d={`M ${ATTACKER.x - 27} ${ATTACKER.y - 29} L ${ATTACKER.x + 36} ${ATTACKER.y} L ${ATTACKER.x - 27} ${ATTACKER.y + 29} L ${ATTACKER.x - 12} ${ATTACKER.y} Z`}
            fill="#0e1014" stroke="#2ee6cd" strokeWidth={2.2} strokeLinejoin="round"
          />
          <text x={ATTACKER.x} y={ATTACKER.y + 104} textAnchor="middle"
                className="fill-accent font-mono text-[13px] font-bold tracking-[0.16em]">
            SENTINEL-1
          </text>
          <text x={ATTACKER.x} y={ATTACKER.y + 124} textAnchor="middle"
                className="fill-ink-mute font-mono text-[10px] tracking-[0.1em]">
            {paused ? "HOLD" : charging ? "CHARGING" : "ENGAGEMENT COMPLETE"}
          </text>
        </g>

        {/* --------------------------------------------------------- beam --- */}
        {firing ? (
          <g key={`beam-${firing.attackId}-${firing.turn}`}>
            <line
              x1={BEAM_FROM} y1={ATTACKER.y} x2={BEAM_TO} y2={ATTACKER.y}
              stroke="url(#beamGrad)" strokeWidth={9} strokeLinecap="round"
              opacity={0.35} filter="url(#soften)"
              className="beam-travel"
              style={{ ["--beam-len" as string]: `${BEAM_LEN}`, ["--beam-ms" as string]: "620ms" }}
            />
            <line
              x1={BEAM_FROM} y1={ATTACKER.y} x2={BEAM_TO} y2={ATTACKER.y}
              stroke="url(#beamGrad)" strokeWidth={2.4} strokeLinecap="round"
              className="beam-travel"
              style={{ ["--beam-len" as string]: `${BEAM_LEN}`, ["--beam-ms" as string]: "620ms" }}
            />
            <text
              x={(BEAM_FROM + BEAM_TO) / 2} y={ATTACKER.y - 26} textAnchor="middle"
              className="font-mono text-[11px] tracking-[0.16em]"
              fill={beamColor}
            >
              {categoryCode(firing.category)} · TURN {firing.turn + 1}
            </text>
          </g>
        ) : null}

        {/* ------------------------------------------------------- target --- */}
        <g>
          <circle cx={TARGET.x} cy={TARGET.y} r={142} fill="url(#tgtGlow)" />

          <ShieldArcs facets={stage.facets} activeFacet={stage.lastResolve?.facet ?? firing?.facet} />

          <Hexagon cx={TARGET.x} cy={TARGET.y} r={42} />
          <text x={TARGET.x} y={TARGET.y + 108} textAnchor="middle"
                className="fill-low font-mono text-[13px] font-bold tracking-[0.16em]">
            TARGET
          </text>
          <text x={TARGET.x} y={TARGET.y + 128} textAnchor="middle"
                className="fill-ink-mute font-mono text-[10px] tracking-[0.1em]">
            {targetId}
          </text>

          {resolving ? (
            <g key={`impact-${resolving.attackId}-${resolving.turn}`}>
              <circle
                cx={TARGET.x - 62} cy={TARGET.y}
                fill="none" stroke={RESOLVE_COLOR[resolving.classification]}
                className="impact-burst"
              />
              <text
                x={TARGET.x} y={TARGET.y - 150} textAnchor="middle"
                className="font-mono text-[13px] font-bold tracking-[0.18em]"
                fill={RESOLVE_COLOR[resolving.classification]}
              >
                {RESOLVE_LABEL[resolving.classification]}
              </text>
              <text
                x={TARGET.x} y={TARGET.y - 132} textAnchor="middle"
                className="fill-ink-mute font-mono text-[10px]"
              >
                confidence {(resolving.confidence * 100).toFixed(0)}%
              </text>
            </g>
          ) : null}

          {intercepting ? (
            <g key={`int-${intercepting.call.ts}`}>
              <circle
                cx={TARGET.x} cy={TARGET.y}
                fill="none" stroke="#ff5cc8" className="impact-burst"
              />
              <text x={TARGET.x} y={TARGET.y + 152} textAnchor="middle"
                    className="font-mono text-[10px] tracking-[0.14em]" fill="#ff5cc8">
                {intercepting.call.flagged ? "SENSOR: FLAGGED CALL" : "SENSOR: TOOL CALL"}
              </text>
            </g>
          ) : null}
        </g>

        {/* Radar idle sweep, so a charging pause does not read as a hang. */}
        {charging && !paused ? (
          <g className="radar-sweep" style={{ transformOrigin: `${TARGET.x}px ${TARGET.y}px` }}>
            <line
              x1={TARGET.x} y1={TARGET.y} x2={TARGET.x} y2={TARGET.y - 142}
              stroke="#5b9cff" strokeWidth={1} opacity={0.28}
            />
          </g>
        ) : null}
      </svg>

      <StageOverlays stage={stage} firing={firing} charging={charging} paused={paused} />
    </div>
  );
}

function Hexagon({ cx, cy, r }: { cx: number; cy: number; r: number }) {
  const pts = Array.from({ length: 6 }, (_, i) => {
    const a = (Math.PI / 3) * i - Math.PI / 2;
    return `${(cx + r * Math.cos(a)).toFixed(1)},${(cy + r * Math.sin(a)).toFixed(1)}`;
  }).join(" ");
  return <polygon points={pts} fill="#0e1014" stroke="#5b9cff" strokeWidth={1.8} strokeLinejoin="round" />;
}

/**
 * One arc per refusal-map topic, on the face toward the attacker. Strength and
 * dashing follow the observed posture, so a soft hedge is visibly the weak
 * point before a single probe is fired.
 */
function ShieldArcs({
  facets,
  activeFacet,
}: {
  facets: StageState["facets"];
  activeFacet?: string;
}) {
  if (!facets.length) {
    return (
      <circle
        cx={TARGET.x} cy={TARGET.y} r={86}
        fill="none" stroke="#1f242e" strokeWidth={2} strokeDasharray="4 8"
      />
    );
  }

  const SPAN = 150;
  const START = 180 - SPAN / 2;
  const seg = SPAN / facets.length;

  return (
    <g>
      {facets.map((f, i) => {
        const gap = Math.min(5, seg * 0.14);
        const a0 = START + i * seg + gap / 2;
        const a1 = START + (i + 1) * seg - gap / 2;
        const active = activeFacet === f.key;
        const color = f.breached ? "#ff4d5e" : f.integrity > 0.7 ? "#5fe08a" : "#ffc93d";

        return (
          <g key={f.key}>
            {/* Ghost track, so a depleted facet still reads as a position. */}
            <path d={arcPath(TARGET.x, TARGET.y, 86, a0, a1)}
                  fill="none" stroke="#1f242e" strokeWidth={9} strokeLinecap="round" />
            <path
              d={arcPath(TARGET.x, TARGET.y, 86, a0, a1)}
              fill="none"
              stroke={color}
              strokeWidth={2.5 + 6 * f.integrity}
              strokeLinecap="round"
              strokeOpacity={f.breached ? 0.35 : 0.28 + 0.72 * f.integrity}
              strokeDasharray={f.breached ? "3 6" : f.integrity < 0.62 ? "10 5" : undefined}
            />
            {active ? (
              <path d={arcPath(TARGET.x, TARGET.y, 97, a0, a1)}
                    fill="none" stroke={color} strokeWidth={1.2} strokeOpacity={0.8} />
            ) : null}
          </g>
        );
      })}
    </g>
  );
}

function BudgetRing({
  cx, cy, r, pct, warned,
}: { cx: number; cy: number; r: number; pct: number; warned: boolean }) {
  const c = 2 * Math.PI * r;
  return (
    <g>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="#1f242e" strokeWidth={3} />
      <circle
        cx={cx} cy={cy} r={r} fill="none"
        stroke={warned ? "#ffc93d" : "#2ee6cd"}
        strokeWidth={3}
        strokeLinecap="round"
        strokeDasharray={`${(c * pct).toFixed(2)} ${c.toFixed(2)}`}
        transform={`rotate(-90 ${cx} ${cy})`}
        style={{ transition: "stroke-dasharray 500ms ease-out" }}
      />
    </g>
  );
}

/** HTML overlays — crisper text than SVG for dense readouts. */
function StageOverlays({
  stage,
  firing,
  charging,
  paused,
}: {
  stage: StageState;
  firing: Extract<Beat, { kind: "fire" }> | null;
  charging: boolean;
  paused: boolean;
}) {
  return (
    <>
      {/*
        The probe itself, under the beam. The pitch is "every shot is a logged
        probe" — showing the literal text in flight is what makes that true on
        screen rather than only in the log.
      */}
      <div className="pointer-events-none absolute inset-x-0 bottom-[16%] flex justify-center px-8">
        {firing ? (
          <div
            key={`${firing.attackId}-${firing.turn}`}
            className="enter w-full max-w-xl rounded border bg-surface/80 px-3 py-2 backdrop-blur"
            style={{ borderColor: `${categoryColor(firing.category)}55` }}
          >
            <p
              className="mb-1 font-mono text-[9px] tracking-[0.16em] uppercase"
              style={{ color: categoryColor(firing.category) }}
            >
              probe in flight · {prettyCategory(firing.category)}
              {firing.facet ? ` → ${firing.facet}` : ""}
            </p>
            <p className="wrap-any line-clamp-3 font-mono text-[11px] leading-relaxed text-ink-dim">
              {firing.probe}
            </p>
          </div>
        ) : charging && !paused ? (
          <p className="font-mono text-[10px] tracking-[0.16em] text-ink-mute uppercase">
            <span className="live-dot">▮</span> sentinel-1 composing next probe
          </p>
        ) : null}
      </div>

      {/* Loadout: the plan, as remaining ordnance. */}
      {stage.plan.length ? (
        <div className="absolute top-3 left-3 flex flex-col gap-1">
          <span className="font-mono text-[9px] tracking-[0.16em] text-ink-mute uppercase">
            loadout
          </span>
          <div className="flex flex-wrap gap-1">
            {stage.plan.map((a) => {
              const spent = stage.activeAttackId
                ? stage.plan.findIndex((p) => p.id === stage.activeAttackId) >
                  stage.plan.findIndex((p) => p.id === a.id)
                : false;
              const active = a.id === stage.activeAttackId;
              return (
                <span
                  key={a.id}
                  title={`${prettyCategory(a.category)} — ${a.target_weakness}`}
                  className={`rounded border px-1.5 py-0.5 font-mono text-[9px] tracking-wide transition ${
                    active ? "border-current" : "border-line"
                  }`}
                  style={{
                    color: categoryColor(a.category),
                    opacity: active ? 1 : spent ? 0.3 : 0.62,
                    background: active ? `${categoryColor(a.category)}18` : "transparent",
                  }}
                >
                  {categoryCode(a.category)}
                </span>
              );
            })}
          </div>
        </div>
      ) : null}

      {/* Tally */}
      <div className="absolute top-3 right-3 flex flex-col items-end gap-0.5 font-mono text-[10px] tabular-nums">
        <span className="text-ink-mute">
          <span className="text-crit">{stage.hits}</span> bypass ·{" "}
          <span className="text-good">{stage.deflected}</span> deflected
        </span>
        <span className="text-ink-mute">{stage.turnsFired} probes fired</span>
      </div>

      {/* Router decision, bottom-left: the graph choosing, made visible. */}
      {stage.route ? (
        <div className="absolute bottom-3 left-3">
          <span className="font-mono text-[9px] tracking-[0.16em] text-ink-mute uppercase">
            router · {stage.route.replace(/_/g, " ")}
          </span>
        </div>
      ) : null}

      {/* Facet legend, bottom-right. */}
      {stage.facets.length ? (
        <div className="absolute right-3 bottom-3 flex flex-col items-end gap-0.5">
          {stage.facets.map((f) => (
            <span key={f.key} className="font-mono text-[9px] tracking-wide">
              <span className={f.breached ? "text-crit" : "text-ink-mute"}>{f.key}</span>
              <span className="text-ink-mute">
                {" "}
                {f.breached ? "BREACHED" : `${Math.round(f.integrity * 100)}%`}
              </span>
            </span>
          ))}
        </div>
      ) : null}

      {stage.verifying ? <VerifyCard stage={stage} /> : null}
    </>
  );
}

/**
 * The verification volley. Reproducibility and minimization are the audit's
 * strongest claims and the hardest to convey in prose, so they get the centre
 * of the stage when they happen.
 */
function VerifyCard({ stage }: { stage: StageState }) {
  const f = stage.verifying!;
  const shrunk =
    f.trigger_probe && f.minimized_prompt && f.minimized_prompt !== f.trigger_probe;
  const ratio = shrunk
    ? Math.max(0.06, f.minimized_prompt.length / Math.max(1, f.trigger_probe.length))
    : 1;

  return (
    <div className="enter absolute top-1/2 left-1/2 w-64 -translate-x-1/2 -translate-y-1/2 rounded-lg border border-accent/40 bg-surface/95 p-3 shadow-2xl shadow-black/70 backdrop-blur">
      <p className="mb-2 font-mono text-[9px] tracking-[0.16em] text-accent uppercase">
        verification volley
      </p>

      <div className="mb-2 flex items-center gap-1.5">
        {(f.rerun_details ?? []).map((r, i) => (
          <span
            key={i}
            title={r.classification}
            className="h-1.5 flex-1 rounded-full"
            style={{ background: RESOLVE_COLOR[r.classification] }}
          />
        ))}
      </div>
      <p className="mb-2 font-mono text-[10px] text-ink-dim tabular-nums">
        {(f.reproducibility * 100).toFixed(0)}% reproduced · {f.verify_reruns} reruns @ temp{" "}
        {f.verify_temperature}
      </p>

      {shrunk ? (
        <div className="mb-2">
          <p className="mb-1 font-mono text-[9px] tracking-wide text-ink-mute uppercase">
            trigger minimized
          </p>
          <div className="h-1 rounded-full bg-surface-3">
            <div
              className="h-full rounded-full bg-accent transition-all duration-700"
              style={{ width: `${ratio * 100}%` }}
            />
          </div>
          <p className="mt-1 font-mono text-[9px] text-ink-mute tabular-nums">
            {f.trigger_probe.length} → {f.minimized_prompt.length} chars ·{" "}
            {f.minimization_steps} steps
          </p>
        </div>
      ) : null}

      <div
        className={`rounded border px-2 py-1.5 ${
          f.confirmed ? "border-crit/50 bg-crit/10" : "border-med/40 bg-med/10"
        }`}
      >
        <p className={`font-mono text-[10px] font-bold tracking-[0.12em] ${f.confirmed ? "text-crit" : "text-med"}`}>
          {f.confirmed ? "◆ CONFIRMED LOCK" : "◇ UNCONFIRMED CONTACT"}
        </p>
        {/*
          verify.py phrases this per category: interceptor corroboration is
          required for tool categories and irrelevant elsewhere. Rendering its
          note verbatim avoids implying a non-tool finding is missing evidence
          it was never supposed to need.
        */}
        <p className="mt-0.5 text-[9px] leading-snug text-ink-mute">
          {f.confirmation_note}
        </p>
      </div>
    </div>
  );
}
