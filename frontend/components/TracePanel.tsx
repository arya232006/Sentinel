"use client";

import { useEffect, useRef, useState } from "react";
import { Badge, Code, Empty, Panel } from "./ui";
import { clockTime, routeTone, tokens, usd } from "@/lib/format";
import type { Route, TraceEntry } from "@/lib/types";

/** Every Claude call, as logged by traced_call(). Real data, not a mockup. */
export function TracePanel({
  traces,
  routes,
  running,
}: {
  traces: TraceEntry[];
  routes: { route: Route; ts: string }[];
  running: boolean;
}) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const pinnedRef = useRef(true);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && pinnedRef.current) el.scrollTop = el.scrollHeight;
  }, [traces.length]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    pinnedRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
  };

  return (
    <Panel
      title="Reasoning trace"
      subtitle={traces.length ? `${traces.length} calls` : undefined}
      actions={running ? <Badge tone="accent">live</Badge> : null}
    >
      {routes.length ? (
        <div className="flex flex-wrap items-center gap-1 border-b border-line bg-surface-2/40 px-3 py-1.5">
          <span className="mr-1 font-mono text-[10px] text-ink-mute">router</span>
          {routes.slice(-14).map((r, i) => (
            <Badge key={i} tone={routeTone(r.route)}>
              {r.route.replace(/_/g, " ")}
            </Badge>
          ))}
        </div>
      ) : null}

      <div ref={scrollRef} onScroll={onScroll} className="h-full overflow-y-auto">
        {traces.length === 0 ? (
          <Empty>
            No Claude calls logged yet. Every call across every node lands here,
            with its latency, token counts and cost.
          </Empty>
        ) : (
          <table className="w-full border-collapse">
            <thead className="sticky top-0 z-10 bg-surface-2/95 backdrop-blur">
              <tr className="border-b border-line text-left font-mono text-[10px] tracking-wide text-ink-mute uppercase">
                <th className="px-2 py-1.5 font-medium">time</th>
                <th className="px-2 py-1.5 font-medium">node</th>
                <th className="px-2 py-1.5 font-medium">model</th>
                <th className="px-2 py-1.5 text-right font-medium">ms</th>
                <th className="px-2 py-1.5 text-right font-medium">tok</th>
                <th className="px-2 py-1.5 text-right font-medium">usd</th>
              </tr>
            </thead>
            <tbody>
              {traces.map((t, i) => (
                <TraceRow key={`${t.ts}-${i}`} entry={t} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Panel>
  );
}

function TraceRow({ entry }: { entry: TraceEntry }) {
  const [open, setOpen] = useState(false);
  const refused = entry.output?.refused;

  return (
    <>
      <tr
        onClick={() => setOpen((v) => !v)}
        className={`cursor-pointer border-b border-line-soft font-mono text-[11px] transition hover:bg-surface-2/60 ${
          refused ? "bg-info/5" : ""
        }`}
      >
        <td className="px-2 py-1 text-ink-mute tabular-nums">{clockTime(entry.ts)}</td>
        <td className="px-2 py-1 text-ink">
          {entry.node}
          {refused ? <span className="ml-1.5 text-info">refused</span> : null}
        </td>
        <td className="px-2 py-1 text-ink-mute">
          {entry.model.replace(/^claude-/, "")}
        </td>
        <td className="px-2 py-1 text-right text-ink-dim tabular-nums">
          {entry.latency_ms}
        </td>
        <td className="px-2 py-1 text-right text-ink-mute tabular-nums">
          {tokens(entry.tokens_in)}/{tokens(entry.tokens_out)}
        </td>
        <td className="px-2 py-1 text-right text-ink-dim tabular-nums">
          {entry.usd.toFixed(5).replace(/^0/, "")}
        </td>
      </tr>
      {open ? (
        <tr>
          <td colSpan={6} className="bg-bg/60 px-3 py-2">
            <div className="space-y-2">
              <div>
                <p className="mb-1 font-mono text-[10px] text-ink-mute uppercase">
                  cost · {usd(entry.usd, 6)}
                </p>
              </div>
              {entry.input?.messages?.length ? (
                <div>
                  <p className="mb-1 font-mono text-[10px] text-ink-mute uppercase">input</p>
                  <Code>
                    {entry.input.messages
                      .map((m) => `[${m.role}] ${m.content}`)
                      .join("\n\n")}
                  </Code>
                </div>
              ) : null}
              <div>
                <p className="mb-1 font-mono text-[10px] text-ink-mute uppercase">output</p>
                <Code>
                  {entry.output?.parsed
                    ? JSON.stringify(entry.output.parsed, null, 2)
                    : entry.output?.text || "(empty)"}
                </Code>
                {entry.output?.stop_reason ? (
                  <p className="mt-1 font-mono text-[10px] text-ink-mute">
                    stop_reason: {entry.output.stop_reason}
                    {entry.output.refusal_category
                      ? ` · ${entry.output.refusal_category}`
                      : ""}
                  </p>
                ) : null}
              </div>
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}
