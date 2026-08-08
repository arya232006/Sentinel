import type { ReactNode } from "react";
import { toneClass, type Tone } from "@/lib/format";

export function Badge({
  tone = "mute",
  children,
  title,
  className = "",
}: {
  tone?: Tone;
  children: ReactNode;
  title?: string;
  className?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[10px] leading-none tracking-wide uppercase ${toneClass(tone)} ${className}`}
    >
      {children}
    </span>
  );
}

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className = "",
  bodyClassName = "",
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section
      className={`flex min-h-0 flex-col overflow-hidden rounded-lg border border-line bg-surface ${className}`}
    >
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-line bg-surface-2/60 px-3 py-2">
        <div className="flex min-w-0 items-baseline gap-2">
          <h2 className="font-mono text-[11px] font-semibold tracking-[0.14em] text-ink-dim uppercase">
            {title}
          </h2>
          {subtitle ? (
            <span className="truncate font-mono text-[11px] text-ink-mute">
              {subtitle}
            </span>
          ) : null}
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-1.5">{actions}</div> : null}
      </header>
      <div className={`min-h-0 flex-1 overflow-y-auto ${bodyClassName}`}>{children}</div>
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full min-h-24 items-center justify-center px-4 py-8 text-center">
      <p className="max-w-xs font-mono text-[11px] leading-relaxed text-ink-mute">
        {children}
      </p>
    </div>
  );
}

const FIELD_LABEL =
  "font-mono text-[10px] tracking-[0.12em] text-ink-dim uppercase";
const FIELD_HINT = "text-[11px] leading-snug text-ink-mute";

/**
 * Wraps exactly ONE labelable control (input, textarea, select).
 *
 * Do not use this for a group of buttons: a <label> binds to the first
 * labelable control inside it, so the group's first button would inherit the
 * label text as its accessible name and a click anywhere on the label or hint
 * would silently activate it. Use FieldGroup for those.
 */
export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className={FIELD_LABEL}>{label}</span>
      {children}
      {hint ? <span className={FIELD_HINT}>{hint}</span> : null}
    </label>
  );
}

/** Same layout as Field, for a set of controls rather than a single one. */
export function FieldGroup({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-col gap-1.5">
      <span className={FIELD_LABEL} aria-hidden>
        {label}
      </span>
      {children}
      {hint ? <span className={FIELD_HINT}>{hint}</span> : null}
    </div>
  );
}

const INPUT_BASE =
  "w-full rounded border border-line bg-surface-2 px-2.5 py-2 font-mono text-[12px] text-ink outline-none transition placeholder:text-ink-mute focus:border-accent-dim focus:ring-1 focus:ring-accent-dim/40";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${INPUT_BASE} ${props.className ?? ""}`} />;
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`${INPUT_BASE} resize-y ${props.className ?? ""}`} />;
}

export function Button({
  variant = "primary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger" | "quiet";
}) {
  const variants = {
    primary:
      "bg-accent text-bg hover:bg-accent/90 border-accent disabled:bg-accent-dim disabled:text-bg/60",
    danger:
      "bg-crit/15 text-crit border-crit/40 hover:bg-crit/25",
    ghost:
      "bg-transparent text-ink-dim border-line hover:border-ink-mute hover:text-ink",
    quiet:
      "bg-surface-2 text-ink-dim border-line hover:bg-surface-3 hover:text-ink",
  }[variant];

  return (
    <button
      {...props}
      className={`inline-flex items-center justify-center gap-1.5 rounded border px-3 py-1.5 font-mono text-[11px] font-semibold tracking-wide transition disabled:cursor-not-allowed disabled:opacity-50 ${variants} ${className}`}
    />
  );
}

/** Definition row used across the finding and recon views. */
export function KV({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex gap-2 py-0.5 text-[11px]">
      <span className="shrink-0 font-mono text-ink-mute">{k}</span>
      <span className="wrap-any min-w-0 text-ink-dim">{v}</span>
    </div>
  );
}

export function Code({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <pre
      className={`wrap-any rounded border border-line-soft bg-bg/60 p-2.5 font-mono text-[11px] leading-relaxed whitespace-pre-wrap text-ink-dim ${className}`}
    >
      {children}
    </pre>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 font-mono text-[11px] text-ink-mute">
      <span className="size-1.5 rounded-full bg-accent live-dot" />
      {label}
    </span>
  );
}
