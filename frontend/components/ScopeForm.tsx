"use client";

import { useMemo, useState } from "react";
import { API_BASE, api } from "@/lib/api";
import { prettyCategory } from "@/lib/format";
import type { Health, Scope } from "@/lib/types";

/**
 * The authorization gate. No run can start without one of these, and the record
 * is write-once and hashed — see sentinel/scope/models.py.
 *
 * Presented for someone filling it in rather than for an operator reading a
 * dense board, which is why it does not use the ui.tsx Field/Input/Panel set:
 * those are tuned for the run views, where 10px tracked mono is the right
 * density for a wall of live state. A form is not that. Labels here are sentence
 * case at a readable size, and the two fields most people never touch are behind
 * a disclosure rather than sitting at the same level as the required ones.
 *
 * Category defaults per target mirror scripts/e2e_http.py so the form produces a
 * scope that is actually exercisable against each harness agent.
 */
const DEFAULT_CATEGORIES: Record<string, string[]> = {
  support_bot: ["authority_impersonation", "multiturn_erosion"],
  tool_agent: ["tool_parameter_hijacking"],
  rag_agent: ["rag_context_poisoning", "indirect_injection"],
};

/**
 * One plain line each, summarising the deliberate weakness the harness agent
 * was built around — condensed from the module docstrings in sentinel/targets/.
 * Anything not in this map still renders; it just shows its id alone.
 */
const TARGET_BLURB: Record<string, { name: string; blurb: string }> = {
  support_bot: {
    name: "Support bot",
    blurb: "Refuses customer-data requests as a preference, not a rule.",
  },
  tool_agent: {
    name: "Tool agent",
    blurb: "Calls real mock functions; every call is recorded as it is made.",
  },
  rag_agent: {
    name: "RAG agent",
    blurb: "Answers from a document store a document can be planted in.",
  },
};

/** Most scopes want hours, not a calendar. The picker keeps the exact field. */
const PRESETS = [
  { label: "4 hours", hours: 4 },
  { label: "24 hours", hours: 24 },
  { label: "7 days", hours: 168 },
];

function expiryAfter(hours: number): string {
  const d = new Date(Date.now() + hours * 3600_000);
  // datetime-local wants a local-time string with no zone suffix.
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const LABEL = "block text-[14px] font-medium text-ink";
const HINT = "mt-1 text-[13px] leading-relaxed text-ink-mute";
const INPUT =
  "w-full rounded-lg border border-line bg-surface px-3.5 py-2.5 text-[14px] text-ink outline-none transition placeholder:text-ink-mute focus:border-accent focus:ring-2 focus:ring-accent/15";

export function ScopeForm({
  health,
  onAuthorized,
}: {
  health: Health | null;
  onAuthorized: (scope: Scope) => void;
}) {
  const targets = health?.targets ?? ["support_bot", "tool_agent", "rag_agent"];
  const categories = health?.categories ?? [];

  const [targetId, setTargetId] = useState(targets[0] ?? "support_bot");
  const [endpoint, setEndpoint] = useState("");
  const [selected, setSelected] = useState<string[]>(
    DEFAULT_CATEGORIES[targets[0] ?? "support_bot"] ?? [],
  );
  const [exclusions, setExclusions] = useState("");
  const [authorizer, setAuthorizer] = useState("");
  const [expiry, setExpiry] = useState(() => expiryAfter(4));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const resolvedEndpoint = useMemo(
    () => endpoint.trim() || `${API_BASE}/targets/${targetId}/chat`,
    [endpoint, targetId],
  );

  const pickTarget = (id: string) => {
    setTargetId(id);
    // Re-seed categories to the ones this target is actually vulnerable to,
    // unless the operator has already diverged from a known default set.
    const prevDefault = DEFAULT_CATEGORIES[targetId] ?? [];
    const untouched =
      selected.length === prevDefault.length &&
      selected.every((c) => prevDefault.includes(c));
    if (untouched) setSelected(DEFAULT_CATEGORIES[id] ?? []);
  };

  const toggle = (c: string) =>
    setSelected((prev) =>
      prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c],
    );

  const valid =
    selected.length > 0 && authorizer.trim() !== "" && expiry !== "";

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    setBusy(true);
    setError(null);
    try {
      const scope = await api.createScope({
        target_id: targetId,
        target_endpoint: resolvedEndpoint,
        allowed_attack_categories: selected,
        exclusions: exclusions
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
        authorizer: authorizer.trim(),
        // The backend coerces naive datetimes to UTC; send an explicit instant.
        expiry_timestamp: new Date(expiry).toISOString(),
      });
      onAuthorized(scope);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-9">
      <fieldset>
        <legend className={LABEL}>Which agent are you testing?</legend>
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          {targets.map((t) => {
            const on = targetId === t;
            const meta = TARGET_BLURB[t];
            return (
              <button
                key={t}
                type="button"
                onClick={() => pickTarget(t)}
                aria-pressed={on}
                className={`rounded-xl border px-4 py-3.5 text-left transition ${
                  on
                    ? "border-accent bg-accent/8 ring-1 ring-accent/30"
                    : "border-line bg-surface hover:border-ink-mute"
                }`}
              >
                <span className="block text-[14px] font-medium text-ink">
                  {meta?.name ?? t}
                </span>
                {meta ? (
                  <span className="mt-1 block text-[12.5px] leading-snug text-ink-mute">
                    {meta.blurb}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      </fieldset>

      <fieldset>
        <legend className={LABEL}>What is it allowed to try?</legend>
        <p className={HINT}>
          The run can never go outside this list — it is checked at every step,
          not just when the run starts. Sensible defaults are already picked for
          the agent you chose.
        </p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {categories.map((c) => {
            const on = selected.includes(c);
            return (
              <button
                key={c}
                type="button"
                onClick={() => toggle(c)}
                aria-pressed={on}
                className={`flex items-center gap-2.5 rounded-lg border px-3.5 py-2.5 text-left text-[13.5px] transition ${
                  on
                    ? "border-accent/60 bg-accent/8 text-ink"
                    : "border-line bg-surface text-ink-dim hover:border-ink-mute"
                }`}
              >
                <span
                  aria-hidden
                  className={`flex size-4 shrink-0 items-center justify-center rounded border text-[10px] ${
                    on
                      ? "border-accent bg-accent text-white"
                      : "border-ink-mute/60"
                  }`}
                >
                  {on ? "✓" : ""}
                </span>
                {prettyCategory(c)}
              </button>
            );
          })}
        </div>
      </fieldset>

      <div className="grid gap-6 sm:grid-cols-2">
        <div>
          <label className={LABEL} htmlFor="authorizer">
            Who is authorizing this?
          </label>
          <p className={HINT}>Recorded on the permission record.</p>
          <input
            id="authorizer"
            className={`${INPUT} mt-3`}
            value={authorizer}
            onChange={(e) => setAuthorizer(e.target.value)}
            placeholder="jane.doe@acme.com"
            required
          />
        </div>

        <div>
          <span className={LABEL}>How long does permission last?</span>
          <p className={HINT}>After this, the scope stops authorizing runs.</p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {PRESETS.map((p) => {
              // Compared to the minute, so a preset stays lit only until the
              // exact field is edited away from it.
              const on = expiry === expiryAfter(p.hours);
              return (
                <button
                  key={p.hours}
                  type="button"
                  onClick={() => setExpiry(expiryAfter(p.hours))}
                  aria-pressed={on}
                  className={`rounded-lg border px-3 py-1.5 text-[13px] transition ${
                    on
                      ? "border-accent bg-accent/8 text-ink"
                      : "border-line bg-surface text-ink-dim hover:border-ink-mute"
                  }`}
                >
                  {p.label}
                </button>
              );
            })}
          </div>
          <input
            type="datetime-local"
            aria-label="Exact expiry"
            className={`${INPUT} mt-2`}
            value={expiry}
            onChange={(e) => setExpiry(e.target.value)}
            required
          />
        </div>
      </div>

      {/* The two fields most people never touch. The endpoint defaults to this
          instance's own harness and the exclusion list is optional, so putting
          them inline was making the form look twice as long as it is. */}
      <details className="group rounded-xl border border-line bg-surface-2/40 px-4 py-3">
        <summary className="cursor-pointer list-none text-[13.5px] font-medium text-ink-dim transition select-none hover:text-ink">
          <span className="inline-block w-4 transition group-open:rotate-90">
            ›
          </span>
          Advanced
        </summary>

        <div className="mt-5 space-y-6 pb-1">
          <div>
            <label className={LABEL} htmlFor="endpoint">
              Target endpoint
            </label>
            <p className={HINT}>
              Leave blank to test this instance&rsquo;s built-in agent. Any HTTP
              endpoint speaking the same contract works.
            </p>
            <input
              id="endpoint"
              className={`${INPUT} mt-3 font-mono text-[13px]`}
              value={endpoint}
              onChange={(e) => setEndpoint(e.target.value)}
              placeholder={`${API_BASE}/targets/${targetId}/chat`}
            />
          </div>

          <div>
            <label className={LABEL} htmlFor="exclusions">
              Off-limits
            </label>
            <p className={HINT}>
              One per line. Checked every time the scope is validated.
            </p>
            <textarea
              id="exclusions"
              rows={3}
              className={`${INPUT} mt-3 resize-y font-mono text-[13px]`}
              value={exclusions}
              onChange={(e) => setExclusions(e.target.value)}
              placeholder={"production_db\npii_records"}
            />
          </div>
        </div>
      </details>

      {error ? (
        <p className="rounded-lg border border-crit/40 bg-crit/10 px-3.5 py-2.5 text-[13px] text-crit">
          {error}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-4 border-t border-line pt-6">
        <button
          type="submit"
          disabled={!valid || busy}
          className="rounded-lg bg-accent px-5 py-2.5 text-[14px] font-medium text-white transition hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-45"
        >
          {busy ? "Authorizing…" : "Create authorization"}
        </button>
        <span className="text-[13px] text-ink-mute">
          {valid
            ? "Written once, then sealed with a checksum."
            : selected.length === 0
              ? "Pick at least one thing it may try."
              : "Add who is authorizing, and how long for."}
        </span>
      </div>
    </form>
  );
}
