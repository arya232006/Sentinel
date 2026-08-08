"use client";

import Link from "next/link";

/**
 * Engagement and console are two renderings of one run, both fed by the same
 * SSE stream. Switching mid-run is a supported move — the new view replays
 * history and fast-forwards to the current state.
 */
export function ViewToggle({
  runId,
  active,
}: {
  runId: string;
  active: "engagement" | "console";
}) {
  const item = (key: "engagement" | "console", href: string, label: string) => (
    <Link
      key={key}
      href={href}
      aria-current={active === key ? "page" : undefined}
      className={`rounded px-2 py-1 font-mono text-[10px] tracking-wide transition ${
        active === key
          ? "bg-accent/15 text-accent"
          : "text-ink-mute hover:text-ink-dim"
      }`}
    >
      {label}
    </Link>
  );

  return (
    <nav
      aria-label="Run view"
      className="flex items-center gap-0.5 rounded border border-line bg-surface-2 p-0.5"
    >
      {item("engagement", `/runs/${runId}/engagement`, "Engagement")}
      {item("console", `/runs/${runId}`, "Console")}
    </nav>
  );
}
