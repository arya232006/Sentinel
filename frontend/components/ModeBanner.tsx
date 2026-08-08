"use client";

import { Badge } from "./ui";
import type { Health } from "@/lib/types";

type Mode = {
  label: string;
  tone: "good" | "med" | "info" | "crit";
  detail: string;
};

/**
 * Which backend is actually answering. This is a correctness surface, not
 * decoration: an offline or shakedown result must never be mistaken for a live
 * Claude result, and the README makes that an explicit project constraint.
 */
export function modeOf(health: Health): Mode {
  if (health.fake_llm) {
    return {
      label: "offline",
      tone: "info",
      detail:
        "Deterministic fake LLM. Exercises the full graph, control flow and gates — but validates plumbing, not attack efficacy.",
    };
  }
  if (health.shakedown_mode) {
    return {
      label: "shakedown",
      tone: "med",
      detail:
        health.shakedown_warning ??
        "Non-Anthropic dev backend. Findings say nothing about Claude, judge accuracy, or the attacker guardrail.",
    };
  }
  if (!health.api_key_present) {
    return {
      label: "no api key",
      tone: "crit",
      detail:
        "ANTHROPIC_API_KEY is not set. Start the backend with SENTINEL_FAKE_LLM=1, or add a key to .env.",
    };
  }
  return {
    label: "live",
    tone: "good",
    detail: `Live Anthropic run. Attacker ${health.attacker_model}, targets ${health.target_model}.`,
  };
}

export function ModeBanner({ health }: { health: Health | null }) {
  if (!health) return null;
  const mode = modeOf(health);
  if (mode.tone === "good") return null; // a live run needs no caveat

  const shell = {
    info: "border-info/30 bg-info/5 text-info",
    med: "border-med/30 bg-med/5 text-med",
    crit: "border-crit/40 bg-crit/10 text-crit",
    good: "",
  }[mode.tone];

  return (
    <div className={`flex items-start gap-2.5 rounded border px-3 py-2 ${shell}`}>
      <Badge tone={mode.tone}>{mode.label}</Badge>
      <p className="text-[11px] leading-snug">{mode.detail}</p>
    </div>
  );
}

export function ModePill({ health }: { health: Health | null }) {
  if (!health) return <Badge tone="mute">connecting…</Badge>;
  const mode = modeOf(health);
  return (
    <Badge tone={mode.tone} title={mode.detail}>
      {mode.label}
    </Badge>
  );
}
