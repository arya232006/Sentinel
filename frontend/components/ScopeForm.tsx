"use client";

import { useMemo, useState } from "react";
import { API_BASE, api } from "@/lib/api";
import { prettyCategory } from "@/lib/format";
import type { Health, Scope } from "@/lib/types";
import { Badge, Button, Field, FieldGroup, Input, Textarea } from "./ui";

/**
 * The authorization gate. No run can start without one of these, and the record
 * is write-once and hashed — see sentinel/scope/models.py.
 *
 * Category defaults per target mirror scripts/e2e_http.py so the form produces a
 * scope that is actually exercisable against each harness agent.
 */
const DEFAULT_CATEGORIES: Record<string, string[]> = {
  support_bot: ["authority_impersonation", "multiturn_erosion"],
  tool_agent: ["tool_parameter_hijacking"],
  rag_agent: ["rag_context_poisoning", "indirect_injection"],
};

function defaultExpiry(hours = 4): string {
  const d = new Date(Date.now() + hours * 3600_000);
  // datetime-local wants a local-time string with no zone suffix.
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

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
  const [expiry, setExpiry] = useState(defaultExpiry);
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

  const valid = selected.length > 0 && authorizer.trim() !== "" && expiry !== "";

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
    <form onSubmit={submit} className="space-y-4">
      <FieldGroup label="Target agent">
        <div className="grid grid-cols-3 gap-1.5">
          {targets.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => pickTarget(t)}
              className={`rounded border px-2 py-2 font-mono text-[11px] transition ${
                targetId === t
                  ? "border-accent bg-accent/10 text-accent"
                  : "border-line bg-surface-2 text-ink-dim hover:border-ink-mute"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </FieldGroup>

      <Field
        label="Target endpoint"
        hint="Defaults to this Sentinel instance's harness. Any HTTP endpoint speaking the same contract works."
      >
        <Input
          value={endpoint}
          onChange={(e) => setEndpoint(e.target.value)}
          placeholder={`${API_BASE}/targets/${targetId}/chat`}
        />
      </Field>

      <FieldGroup
        label="Allowed attack categories"
        hint="Enforced at every phase transition, not just at run start. The planner cannot generate outside this set."
      >
        <div className="grid grid-cols-2 gap-1.5">
          {categories.map((c) => {
            const on = selected.includes(c);
            return (
              <button
                key={c}
                type="button"
                onClick={() => toggle(c)}
                className={`flex items-center gap-2 rounded border px-2 py-1.5 text-left font-mono text-[10px] transition ${
                  on
                    ? "border-accent/50 bg-accent/10 text-accent"
                    : "border-line bg-surface-2 text-ink-mute hover:border-ink-mute"
                }`}
              >
                <span
                  className={`flex size-3 shrink-0 items-center justify-center rounded-xs border ${
                    on ? "border-accent bg-accent text-bg" : "border-ink-mute"
                  }`}
                >
                  {on ? "✓" : ""}
                </span>
                {prettyCategory(c)}
              </button>
            );
          })}
        </div>
      </FieldGroup>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Authorizer">
          <Input
            value={authorizer}
            onChange={(e) => setAuthorizer(e.target.value)}
            placeholder="jane.doe@acme.com"
            required
          />
        </Field>
        <Field label="Expiry">
          <Input
            type="datetime-local"
            value={expiry}
            onChange={(e) => setExpiry(e.target.value)}
            required
          />
        </Field>
      </div>

      <Field label="Exclusions" hint="One per line. Checked on every scope validation.">
        <Textarea
          rows={2}
          value={exclusions}
          onChange={(e) => setExclusions(e.target.value)}
          placeholder="production_db&#10;pii_records"
        />
      </Field>

      {error ? (
        <p className="rounded border border-crit/40 bg-crit/10 px-2.5 py-2 font-mono text-[11px] text-crit">
          {error}
        </p>
      ) : null}

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={!valid || busy}>
          {busy ? "Authorizing…" : "Create authorization"}
        </Button>
        {!valid ? (
          <span className="font-mono text-[10px] text-ink-mute">
            {selected.length === 0
              ? "select at least one category"
              : "authorizer and expiry are required"}
          </span>
        ) : (
          <Badge tone="mute">write-once · sha256 hashed</Badge>
        )}
      </div>
    </form>
  );
}
