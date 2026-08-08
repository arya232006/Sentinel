import type { Classification, FindingStatus, Provenance, Route } from "./types";

export type Tone =
  | "crit" | "high" | "med" | "low" | "good" | "info" | "accent" | "mute";

const TONE_CLASSES: Record<Tone, string> = {
  crit: "text-crit border-crit/35 bg-crit/10",
  high: "text-high border-high/35 bg-high/10",
  med: "text-med border-med/35 bg-med/10",
  low: "text-low border-low/35 bg-low/10",
  good: "text-good border-good/35 bg-good/10",
  info: "text-info border-info/35 bg-info/10",
  accent: "text-accent border-accent/35 bg-accent/10",
  mute: "text-ink-mute border-line bg-surface-2",
};

export const toneClass = (t: Tone) => TONE_CLASSES[t];

/** Bands match the severity formula in score.py: base 9 / 7 / 3 scaled down. */
export function severityTone(severity?: number): Tone {
  if (severity === undefined || severity <= 0) return "mute";
  if (severity >= 8) return "crit";
  if (severity >= 6) return "high";
  if (severity >= 3) return "med";
  return "low";
}

export function severityLabel(severity?: number): string {
  if (severity === undefined) return "unscored";
  if (severity <= 0) return "none";
  if (severity >= 8) return "critical";
  if (severity >= 6) return "high";
  if (severity >= 3) return "medium";
  return "low";
}

/**
 * Inverted on purpose: a succeeded attack means the target leaked, which is the
 * bad outcome; a failed attack means it held the line.
 */
export function verdictTone(c?: Classification): Tone {
  switch (c) {
    case "succeeded": return "crit";
    case "partial": return "high";
    case "failed": return "good";
    case "refused_differently": return "low";
    default: return "mute";
  }
}

export function statusTone(s: FindingStatus): Tone {
  switch (s) {
    case "confirmed": return "crit";
    case "text_only_unconfirmed": return "med";
    case "not_reproduced": return "mute";
  }
}

/** Anything that is not a live Claude run must be visually distinct from one. */
export function provenanceTone(p: Provenance): Tone {
  switch (p) {
    case "live": return "good";
    case "shakedown": return "high";
    case "offline": return "info";
    case "replayed": return "med";
  }
}

export const PROVENANCE_NOTE: Record<Provenance, string> = {
  live: "Produced by a live Anthropic run.",
  offline: "Produced by the deterministic offline fake. Validates plumbing, not attack efficacy.",
  shakedown: "Produced by a non-Anthropic dev backend. Says nothing about Claude, judge accuracy, or the attacker guardrail.",
  replayed: "Replayed from a recorded run, not produced live.",
};

export function routeTone(r: Route): Tone {
  switch (r) {
    case "escalate": return "high";
    case "pivot": return "info";
    case "next_attack": return "mute";
    case "verify": return "accent";
    case "escalation_gate": return "med";
    case "abort": return "crit";
  }
}

export const prettyCategory = (c: string) => c.replace(/_/g, " ");

/**
 * Weapon colour per attack category, for the engagement view. Raw hex because
 * these feed SVG stroke/fill and gradient stops, not Tailwind classes.
 */
export const CATEGORY_COLOR: Record<string, string> = {
  authority_impersonation: "#ffb03d",
  multiturn_erosion: "#2ee6cd",
  tool_parameter_hijacking: "#ff5cc8",
  indirect_injection: "#8b7dff",
  rag_context_poisoning: "#5fe08a",
  direct_jailbreak: "#ff6b5e",
};

export const categoryColor = (c: string) => CATEGORY_COLOR[c] ?? "#8b93a3";

/** Short callsign-style label for a category, for tight UI slots. */
export const CATEGORY_CODE: Record<string, string> = {
  authority_impersonation: "AUTH",
  multiturn_erosion: "EROS",
  tool_parameter_hijacking: "HIJK",
  indirect_injection: "INJC",
  rag_context_poisoning: "POIS",
  direct_jailbreak: "JAIL",
};

export const categoryCode = (c: string) => CATEGORY_CODE[c] ?? c.slice(0, 4).toUpperCase();

/** SVG arc path. Angles in degrees, 0 = +x, increasing clockwise (SVG y-down). */
export function arcPath(
  cx: number,
  cy: number,
  r: number,
  startDeg: number,
  endDeg: number,
): string {
  const pt = (deg: number) => {
    const rad = (deg * Math.PI) / 180;
    return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)] as const;
  };
  const [x1, y1] = pt(startDeg);
  const [x2, y2] = pt(endDeg);
  const large = Math.abs(endDeg - startDeg) > 180 ? 1 : 0;
  return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
}

export const usd = (n: number, dp = 4) =>
  `$${n.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp })}`;

export const compactUsd = (n: number) =>
  `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export const tokens = (n: number) =>
  n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);

export function clockTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "--:--:--"
    : d.toLocaleTimeString("en-GB", { hour12: false });
}

export const truncate = (s: string, n: number) =>
  s.length <= n ? s : `${s.slice(0, n)}…`;
