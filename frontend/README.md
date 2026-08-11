# Sentinel console

Next.js 16 (App Router) + React 19 + Tailwind v4. The operator UI for the
Sentinel backend: scope authorization, a live three-panel run view, the
human-in-the-loop gates, and the reasoning trace.

Kept as a plain directory rather than a workspace package — the backend is
Python, so monorepo tooling would only ever manage half the repo.

```bash
npm install
npm run dev            # http://localhost:3000
```

The backend must be running separately (see the root README). The console
expects it at `http://127.0.0.1:8000`; override with `NEXT_PUBLIC_SENTINEL_API`.

`/` is the marketing landing page. The operator tool — scope authorization and
the run launcher — is at `/console`. Both run light theme; the run views below
stay dark.

## Two views of one run

A run renders two ways, both fed by the same `useRunStream` subscription:

| Route | View |
|---|---|
| `/runs/[id]/engagement` | Tactical engagement — where a run opens by default |
| `/runs/[id]` | Dense console — Plan / Transcript / Findings / Trace |

Switching mid-run is supported: the new view replays history and fast-forwards.

## Layout

```
app/
  page.tsx                          landing page (server component, light)
  console/page.tsx                  scope authorization + run launcher (light)
  runs/[runId]/page.tsx             dense console (dark)
  runs/[runId]/engagement/page.tsx  tactical engagement view (dark)
components/
  landing/               Hero  Sections  SmoothScroll  Arrow  links.ts
  ScopeForm  ApprovalModal  BudgetMeter  ModeBanner  ViewToggle  Mark
  PlanPanel  TranscriptPanel  FindingsPanel  TracePanel
  engagement/  Stage  OpsLog  FindingsStrip  HoldOverlay
  ui.tsx                 Panel / Badge / Field / Button primitives (run views)
lib/
  types.ts               mirrors the Python models; each type names its source
  api.ts                 typed client for the FastAPI surface
  useRunStream.ts        SSE subscription + reducer
  useEngagement.ts       SSE feed -> paced engagement beats
  format.ts              severity bands, tones, category colours, arc geometry
```

## The engagement view

Nothing on the stage is decorative — every element is bound to real data:

| Element | Source |
|---|---|
| Target shield facets | `recon_profile.refusal_map`; a soft hedge starts visibly weaker |
| Which facet a probe attacks | `attack_plan[].target_facet` (the planner names it) |
| Beam colour | the attack category being fired |
| Shot fired → hit/deflect | the two `transcript` events per turn |
| Shield erosion | verdict per turn; deflections recover a little |
| Budget ring | live `budget` events against the hard cap |
| HUMAN HOLD | `interrupt` — the graph really is parked server-side |
| Verification volley | `rerun_details`, `reproducibility`, `minimization_steps` |
| Confirmed lock vs unconfirmed contact | the judge + interceptor confirmation rule |

**Pacing.** Raw event timing is unwatchable at both ends — offline the run lands
in milliseconds, live an Opus 5 probe takes 10-30s. `useEngagement` plays beats
on its own clock and compresses when a backlog builds. Joining mid-run
fast-forwards rather than replaying the whole battle, and a parked gate drains
the queue hard so the stage shows the moment being authorized.

The ops log is built from `state`, not from played beats, so it always reflects
what has actually happened even while the stage is catching up.

## The SSE contract

`useRunStream` is the only stateful piece, and three details in it are
load-bearing:

- **Named events.** The backend emits `event: <type>` frames, so each type needs
  its own `addEventListener`; a bare `onmessage` receives nothing.
- **`seq` dedup.** The server replays its full history to every new subscriber
  and `EventSource` reconnects on its own, so without dropping events at or
  below the last-seen `seq` a single reconnect replays the whole run and applies
  every event twice.
- **Explicit close on `done`.** The server ends the response there. Left open,
  `EventSource` reads that as a dropped connection and reconnects forever.

Findings are upserted by `finding_id` because `verify` emits a finding first and
`score` re-emits it enriched with severity and mitigation — so a finding appears
as soon as it is verified, then gains its score. Transcript turns are grouped by
`attack_id` so completed attacks stay readable after the cursor advances.

## Conventions

- Two themes, scoped by subtree via a `.theme-light` wrapper: the landing page
  and `/console` run light (they are a form and a pitch, not an instrument
  panel), while the run views stay dark, deliberately, since the job there is
  reading a wall of live state at a glance. Components draw from semantic
  tokens in `app/globals.css` rather than literal colours, so `ui.tsx` and the
  run-view components invert correctly without knowing a wrapper exists.
- A *succeeded* attack reads red (the target leaked) and a *failed* one reads
  green (the target held). This inverts the usual convention on purpose.
- `Field` wraps exactly one labelable control. Use `FieldGroup` for button
  groups: a `<label>` binds to the first labelable control inside it, so a
  button group inside `Field` would give its first button the label's accessible
  name and let a click on the label text activate it.
- Provenance is always rendered on a finding. An `offline` or `shakedown`
  result must never be mistakable for a live Claude one.
