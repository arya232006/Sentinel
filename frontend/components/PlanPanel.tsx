"use client";

import { Badge, Empty, Panel } from "./ui";
import { prettyCategory } from "@/lib/format";
import type { PlannedAttack, ReconProfile } from "@/lib/types";

const PRIORITY_TONE = { high: "crit", medium: "med", low: "low" } as const;

const REFUSAL_TONE: Record<string, "crit" | "med" | "good" | "mute"> = {
  hard_block: "good", // the target refusing firmly is good for the target
  soft_hedge: "med",
  no_refusal: "crit",
};

export function PlanPanel({
  plan,
  recon,
  cursor,
  running,
}: {
  plan: PlannedAttack[];
  recon: ReconProfile | null;
  cursor: number;
  running: boolean;
}) {
  return (
    <Panel
      title="Plan"
      subtitle={plan.length ? `${plan.length} attacks` : undefined}
      actions={
        plan.length ? (
          <Badge tone="mute">
            {Math.min(cursor + 1, plan.length)}/{plan.length}
          </Badge>
        ) : null
      }
    >
      {recon ? <ReconCard recon={recon} /> : null}

      {plan.length === 0 ? (
        <Empty>
          {running
            ? "Waiting for recon to finish and the planner to return an attack plan."
            : "No attack plan was produced for this run."}
        </Empty>
      ) : (
        <ol className="divide-y divide-line-soft">
          {plan.map((atk, i) => (
            <PlanItem
              key={atk.id}
              attack={atk}
              index={i}
              active={i === cursor && running}
              done={i < cursor}
            />
          ))}
        </ol>
      )}
    </Panel>
  );
}

function PlanItem({
  attack,
  index,
  active,
  done,
}: {
  attack: PlannedAttack;
  index: number;
  active: boolean;
  done: boolean;
}) {
  return (
    <li
      className={`enter relative px-3 py-2.5 transition ${
        active ? "bg-accent/5" : done ? "opacity-55" : ""
      }`}
    >
      {active ? (
        <span className="absolute inset-y-0 left-0 w-0.5 bg-accent" aria-hidden />
      ) : null}

      <div className="mb-1 flex items-center gap-2">
        <span className="font-mono text-[10px] text-ink-mute tabular-nums">
          {String(index + 1).padStart(2, "0")}
        </span>
        <span className="truncate font-mono text-[12px] font-semibold text-ink">
          {prettyCategory(attack.category)}
        </span>
        <Badge tone={PRIORITY_TONE[attack.priority]} className="ml-auto">
          {attack.priority}
        </Badge>
        {active ? <Badge tone="accent">running</Badge> : null}
      </div>

      <p className="mb-1.5 text-[11px] leading-snug text-ink-dim">
        <span className="text-ink-mute">weakness · </span>
        {attack.target_weakness}
      </p>
      <p className="mb-1.5 text-[11px] leading-snug text-ink-mute">{attack.rationale}</p>

      {/* The brief requires retrieved_basis to be visible — it is what makes the
          planner retrieval-augmented rather than freehand. */}
      {attack.retrieved_basis ? (
        <p className="wrap-any font-mono text-[10px] text-accent-dim">
          basis: {attack.retrieved_basis}
        </p>
      ) : null}
    </li>
  );
}

function ReconCard({ recon }: { recon: ReconProfile }) {
  const refusals = Object.entries(recon.refusal_map ?? {});
  return (
    <div className="enter border-b border-line bg-surface-2/40 px-3 py-2.5">
      <p className="mb-1.5 font-mono text-[10px] tracking-[0.12em] text-ink-mute uppercase">
        recon profile
      </p>
      <p className="mb-2 text-[11px] leading-snug text-ink-dim">{recon.apparent_purpose}</p>

      {recon.apparent_tools?.length ? (
        <div className="mb-1.5 flex flex-wrap items-center gap-1">
          <span className="font-mono text-[10px] text-ink-mute">tools</span>
          {recon.apparent_tools.map((t) => (
            <Badge key={t} tone="info">{t}</Badge>
          ))}
        </div>
      ) : null}

      {recon.apparent_data_access?.length ? (
        <div className="mb-1.5 flex flex-wrap items-center gap-1">
          <span className="font-mono text-[10px] text-ink-mute">data</span>
          {recon.apparent_data_access.map((d) => (
            <Badge key={d} tone="low">{d}</Badge>
          ))}
        </div>
      ) : null}

      {refusals.length ? (
        <div className="mt-2">
          <p className="mb-1 font-mono text-[10px] text-ink-mute">
            refusal map · soft hedges are the attack surface
          </p>
          <div className="flex flex-wrap gap-1">
            {refusals.map(([topic, kind]) => (
              <Badge key={topic} tone={REFUSAL_TONE[kind] ?? "mute"} title={kind}>
                {topic}: {kind.replace(/_/g, " ")}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}

      {recon.observed_quirks?.length ? (
        <ul className="mt-2 space-y-0.5">
          {recon.observed_quirks.map((q, i) => (
            <li key={i} className="text-[10px] leading-snug text-ink-mute">· {q}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
