"use client";

import { useEffect, useRef } from "react";
import { Badge, Empty, Panel } from "./ui";
import { prettyCategory, verdictTone } from "@/lib/format";
import type { InterceptCall, PlannedAttack, Turn } from "@/lib/types";

export function TranscriptPanel({
  turnsByAttack,
  attackOrder,
  plan,
  running,
}: {
  turnsByAttack: Record<string, Turn[]>;
  attackOrder: string[];
  plan: PlannedAttack[];
  running: boolean;
}) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const pinnedRef = useRef(true);

  const totalTurns = attackOrder.reduce(
    (n, id) => n + (turnsByAttack[id]?.length ?? 0),
    0,
  );

  // Follow the tail while the operator is at the bottom, but stop fighting them
  // the moment they scroll up to read an earlier exchange.
  useEffect(() => {
    const el = scrollRef.current;
    if (el && pinnedRef.current) el.scrollTop = el.scrollHeight;
  }, [totalTurns, turnsByAttack]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    pinnedRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  };

  return (
    <Panel
      title="Transcript"
      subtitle={totalTurns ? `${totalTurns} turns` : undefined}
      actions={running ? <Badge tone="accent">live</Badge> : null}
      bodyClassName="scroll-smooth"
    >
      <div ref={scrollRef} onScroll={onScroll} className="h-full overflow-y-auto">
        {attackOrder.length === 0 ? (
          <Empty>
            {running
              ? "No probes sent yet. The first exchange appears here the moment craft_probe returns."
              : "No probes were exchanged during this run."}
          </Empty>
        ) : (
          attackOrder.map((attackId) => {
            const turns = turnsByAttack[attackId] ?? [];
            const spec = plan.find((p) => p.id === attackId);
            return (
              <section key={attackId}>
                <header className="sticky top-0 z-10 flex items-center gap-2 border-y border-line bg-surface-2/95 px-3 py-1.5 backdrop-blur">
                  <span className="font-mono text-[10px] text-ink-mute">{attackId}</span>
                  {spec ? (
                    <span className="truncate font-mono text-[11px] text-ink-dim">
                      {prettyCategory(spec.category)}
                    </span>
                  ) : null}
                  <span className="ml-auto font-mono text-[10px] text-ink-mute">
                    {turns.length} turn{turns.length === 1 ? "" : "s"}
                  </span>
                </header>
                <div className="space-y-3 px-3 py-3">
                  {turns.map((t, i) => (
                    <TurnBlock key={`${attackId}-${t.turn}-${i}`} turn={t} />
                  ))}
                </div>
              </section>
            );
          })
        )}
      </div>
    </Panel>
  );
}

function TurnBlock({ turn }: { turn: Turn }) {
  // craft_probe records a turn with no probe when the attacker model itself
  // declined. That is a first-class outcome, not a gap in the transcript.
  if (turn.refused) {
    return (
      <div className="enter rounded border border-info/30 bg-info/5 px-2.5 py-2">
        <Badge tone="info">attacker refused</Badge>
        <p className="mt-1.5 text-[11px] leading-snug text-ink-dim">
          {turn.note ?? "The attacker model declined to craft this probe."}
          {turn.refusal_category ? (
            <span className="text-ink-mute"> · {turn.refusal_category}</span>
          ) : null}
        </p>
      </div>
    );
  }

  return (
    <div className="enter space-y-1.5">
      <div className="flex items-center gap-2">
        <span className="font-mono text-[10px] text-ink-mute tabular-nums">
          turn {turn.turn + 1}
        </span>
        {turn.angle ? (
          <span className="truncate font-mono text-[10px] text-accent-dim">
            {turn.angle}
          </span>
        ) : null}
        {turn.verdict ? (
          <Badge
            tone={verdictTone(turn.verdict.classification)}
            className="ml-auto"
            title={turn.verdict.reasoning}
          >
            {turn.verdict.classification.replace(/_/g, " ")}
            <span className="opacity-70">
              {" "}
              {(turn.verdict.confidence * 100).toFixed(0)}%
            </span>
          </Badge>
        ) : (
          <Badge tone="mute" className="ml-auto">judging…</Badge>
        )}
      </div>

      {/* probe */}
      <div className="rounded border border-line-soft bg-surface-2/70 px-2.5 py-2">
        <p className="mb-1 font-mono text-[10px] tracking-wider text-ink-mute uppercase">
          probe
        </p>
        <p className="wrap-any font-mono text-[11px] leading-relaxed whitespace-pre-wrap text-ink-dim">
          {turn.probe}
        </p>
      </div>

      {/* The attacker guardrail redacting itself is worth showing, not hiding —
          it is spec section 9 working. */}
      {turn.withheld ? (
        <div className="rounded border border-med/30 bg-med/5 px-2.5 py-1.5">
          <Badge tone="med">withheld</Badge>
          <p className="mt-1 text-[10px] leading-snug text-ink-dim">{turn.withheld}</p>
        </div>
      ) : null}

      {/* response */}
      <div className="rounded border border-line-soft bg-bg/50 px-2.5 py-2">
        <p className="mb-1 font-mono text-[10px] tracking-wider text-ink-mute uppercase">
          target
        </p>
        {turn.error ? (
          <p className="font-mono text-[11px] text-crit">transport error: {turn.error}</p>
        ) : (
          <p className="wrap-any text-[11px] leading-relaxed whitespace-pre-wrap text-ink">
            {turn.response || <span className="text-ink-mute">(empty response)</span>}
          </p>
        )}
        {turn.inconclusive ? (
          <div className="mt-1.5">
            <Badge tone="med">inconclusive · retry ceiling hit</Badge>
          </div>
        ) : null}
      </div>

      {turn.tool_calls?.length ? <ToolCalls calls={turn.tool_calls} /> : null}

      {turn.retrieved_docs?.length ? (
        <details className="rounded border border-line-soft bg-surface-2/40 px-2.5 py-1.5">
          <summary className="cursor-pointer font-mono text-[10px] text-ink-mute">
            {turn.retrieved_docs.length} retrieved doc
            {turn.retrieved_docs.length === 1 ? "" : "s"}
          </summary>
          <ul className="mt-1.5 space-y-1">
            {turn.retrieved_docs.map((d, i) => (
              <li key={i} className="wrap-any font-mono text-[10px] leading-snug text-ink-mute">
                {d}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {turn.verdict?.evidence_span ? (
        <p className="wrap-any border-l-2 border-line pl-2 text-[10px] leading-snug text-ink-mute italic">
          evidence: “{turn.verdict.evidence_span}”
        </p>
      ) : null}
    </div>
  );
}

/**
 * Tool calls get their own treatment because the interceptor's record is
 * independent evidence — it is what confirms a tool finding that the target's
 * prose merely claims.
 */
function ToolCalls({ calls }: { calls: InterceptCall[] }) {
  return (
    <div className="space-y-1">
      {calls.map((c, i) => (
        <div
          key={i}
          className={`rounded border px-2.5 py-1.5 ${
            c.flagged ? "border-crit/40 bg-crit/5" : "border-low/30 bg-low/5"
          }`}
        >
          <div className="flex items-center gap-2">
            <Badge tone={c.flagged ? "crit" : "low"}>
              {c.flagged ? "flagged call" : "tool call"}
            </Badge>
            {c.executed ? (
              <span className="font-mono text-[10px] text-ink-mute">executed</span>
            ) : (
              <span className="font-mono text-[10px] text-med">not executed</span>
            )}
          </div>
          <p className="wrap-any mt-1 font-mono text-[11px] text-ink">
            {c.tool_name}({JSON.stringify(c.arguments)})
          </p>
          {c.flag_reason ? (
            <p className="mt-0.5 text-[10px] leading-snug text-crit/90">{c.flag_reason}</p>
          ) : null}
        </div>
      ))}
    </div>
  );
}
