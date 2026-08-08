import Image from "next/image";
import Link from "next/link";
import flowerImg from "@/public/flower.png";
import sectionImg from "@/public/section.jpeg";
import feature2Img from "@/public/feature2.webp";
import feature3Img from "@/public/feature3.webp";
import { Arrow } from "./Arrow";

/**
 * Narrative bands between the hero and the console.
 *
 * Every claim here is a claim about code that exists — the double scope filter
 * in planner.py, the interrupt() gates in gates.py, the Python severity
 * arithmetic in score.py. Keep it that way: this page sits directly above an
 * operator tool, and marketing copy that outruns the implementation would be
 * caught in the first demo.
 */

/**
 * The card gallery's contents. Titles are plain English, sub-lines are the
 * category slug the run would actually be authorized under — every one of these
 * is a real member of ATTACK_CATEGORIES in sentinel/config.py, which is what
 * keeps this a description of the taxonomy rather than a poster for it.
 */
const THREATS = [
  {
    img: feature2Img,
    title: "Tool calls it was never meant to make",
    slug: "tool_parameter_hijacking",
  },
  {
    img: feature3Img,
    title: "A planted document that supersedes your policy",
    slug: "rag_context_poisoning",
  },
  {
    img: sectionImg,
    title: "Ten turns of patient erosion",
    slug: "multiturn_erosion",
  },
];

/**
 * Statement band, first thing under the hero.
 *
 * The right column centres as one block rather than justifying to the image's
 * full height — the column is as tall as the flower, so spreading it to the
 * ends opened a void between the paragraphs and the line. The gap is set here,
 * not inherited from whatever height the artwork happens to be.
 *
 * `unoptimized` on the image, which is the opposite of the usual advice and the
 * point: the optimizer would re-encode it to lossy webp, and chroma subsampling
 * on hard-edged pixel art fringes every square with colour that was never in the
 * original. The PNG is 167KB and sits below the fold, which is the price.
 */
export function Vision() {
  return (
    <section className="bg-surface">
      <div className="mx-auto grid max-w-6xl items-stretch gap-10 px-6 py-20 sm:py-28 lg:grid-cols-2 lg:gap-16">
        <div className="flex justify-center lg:justify-start">
          <Image
            src={flowerImg}
            alt=""
            unoptimized
            sizes="(min-width: 1024px) 28rem, 80vw"
            className="pixelated h-auto w-full max-w-md self-center"
          />
        </div>

        <div className="flex flex-col justify-center gap-8 lg:py-6">
          <div className="max-w-md space-y-5 text-[15px] leading-relaxed text-ink-dim">
            <p>
              Every agent that ships to the public should have been broken in
              private first - by something that improvises, not by a checklist
              somebody last updated two model generations ago.
            </p>
            <p>
              So Sentinel runs the engagement you would run yourself if you had
              the week: it probes, escalates, proves the finding reproduces, and
              hands back the shortest prompt that still works.
            </p>
          </div>

          <h2 className="max-w-xl font-serif text-[clamp(2rem,4.6vw,3.4rem)] leading-[1.08] text-ink">
            Find out how your agent breaks before somebody else does.
          </h2>
        </div>
      </div>
    </section>
  );
}

/** Legend tick, borrowed from a measuring scale — a lead mark and four counts.
 *  Purely a typographic ornament, so it is hidden from assistive tech. */
function Ticks({ className = "text-ink-mute" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 34 12"
      aria-hidden
      className={`h-3 w-8.5 ${className}`}
      stroke="currentColor"
      strokeWidth="1"
    >
      <path d="M0.5 0v12M8.5 5v7M16.5 5v7M24.5 5v7M32.5 5v7" />
    </svg>
  );
}

/**
 * Fig. 1 — the adversarial loop drawn around the target it runs against.
 *
 * The shape is the argument the band is making: three nodes on a cycle, not a
 * row of boxes with an end. Craft and judge sit outside on the ring, the two
 * inner arrows are the only moment the target is touched, and the long arc back
 * up the left is what a checklist does not have.
 *
 * Everything is in the 800x340 user space and scaled by the viewBox, font sizes
 * included — at the ~0.8 the panel renders it, 14 user units land near 11px,
 * which is the size the mono labels are set at everywhere else on the page. The
 * box is 340 rather than 420 tall because the linework ends at y=298 and the
 * leftover was reading as the figure sitting high in its frame.
 *
 * `stroke="none"` on every <text>: the svg sets a stroke for the linework and
 * text would otherwise inherit it and render outlined.
 */
function Fig1() {
  const label = "font-mono tracking-[0.12em] uppercase";
  return (
    <svg
      viewBox="0 0 800 340"
      aria-hidden
      className="h-auto w-full text-ink-dim"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
    >
      <defs>
        {/* userSpaceOnUse rather than the default strokeWidth units, so the head
            is sized in the same coordinates as everything else instead of being
            multiplied by the 1.4 stroke. */}
        <marker
          id="fig1-head"
          viewBox="0 0 12 12"
          markerUnits="userSpaceOnUse"
          markerWidth="12"
          markerHeight="12"
          refX="10"
          refY="6"
          orient="auto"
        >
          <path d="M2.5 2 L10 6 L2.5 10" strokeWidth="1.4" strokeLinecap="round" />
        </marker>
      </defs>

      {/* The target, and the only filled-in thing here: it is what the loop is
          about, so it holds the centre. */}
      <circle cx="400" cy="205" r="54" />
      <text
        x="400"
        y="205"
        className={label}
        fontSize="14"
        fill="currentColor"
        stroke="none"
        textAnchor="middle"
        dominantBaseline="central"
      >
        Target
      </text>

      <rect x="344" y="40" width="112" height="40" rx="6" />
      <rect x="470" y="258" width="112" height="40" rx="6" />
      <rect x="218" y="258" width="112" height="40" rx="6" />

      {[
        { x: 400, y: 60, t: "Craft" },
        { x: 526, y: 278, t: "Send" },
        { x: 274, y: 278, t: "Judge" },
      ].map((n) => (
        <text
          key={n.t}
          x={n.x}
          y={n.y}
          className={label}
          fontSize="14"
          fill="currentColor"
          stroke="none"
          textAnchor="middle"
          dominantBaseline="central"
        >
          {n.t}
        </text>
      ))}

      <g markerEnd="url(#fig1-head)">
        {/* Craft → Send, swinging outside the ring on the right. */}
        <path d="M456 60 Q648 130 562 252" />
        {/* The two inner arrows: the probe in, and what came back out. */}
        <path d="M491 258 L449 233" />
        <path d="M351 233 L309 258" />
        {/* Judge → Craft. The long way round, which is the whole point. */}
        <path d="M240 256 Q120 140 340 62" />
      </g>

      {/* Set against the return arc's widest point, which is (198, 179), with a
          short leader into it — floating the label in open space read as a
          caption for the figure rather than for the one path it names. */}
      <path d="M186 179 H196" opacity="0.55" />
      <text
        x="176"
        y="179"
        className={label}
        fontSize="13"
        fill="currentColor"
        stroke="none"
        textAnchor="end"
        dominantBaseline="central"
        opacity="0.75"
      >
        escalate · pivot
      </text>
    </svg>
  );
}

/**
 * The argument band: a statement set large, then the figure that carries it.
 *
 * The second line is a <p>, not a second <h2> — it reads as the same voice at
 * the same size, but it is a continuation of the sentence above rather than a
 * heading of its own, and two h2s here would put a section break in the outline
 * that does not exist on the page.
 */
export function Adversary() {
  return (
    /* scroll-mt clears the fixed nav, which is 24px of inset plus a ~58px pill.
       Lenis reads the computed scroll-margin-top on its anchor jumps, so this is
       all the offset the nav links need — see SmoothScroll.tsx. */
    <section id="adversary" className="scroll-mt-24 bg-surface">
      <div className="mx-auto max-w-6xl px-6 py-20 sm:py-28">
        <h2 className="max-w-4xl font-serif text-[clamp(1.9rem,4.4vw,3.2rem)] leading-[1.14] text-ink">
          Refusal training, system prompts and output filters hold against{" "}
          <span className="text-ink-mute underline decoration-1 underline-offset-[0.18em]">
            the attacks somebody already thought of
          </span>
          , but these are all static defences.
        </h2>
        <p className="mt-8 font-serif text-[clamp(1.9rem,4.4vw,3.2rem)] leading-[1.14] text-ink">
          They need an adversary.
        </p>

        <div className="mt-16 grid gap-10 sm:mt-24 lg:grid-cols-[19rem_1fr] lg:gap-16">
          <div>
            <Ticks />
            <h3 className="mt-7 text-[13.5px] font-semibold text-ink">
              The adversarial loop
            </h3>
            <div className="mt-4 space-y-4 text-[13.5px] leading-relaxed text-ink-dim">
              <p>
                A filter answers one question, and answers it the same way however
                many times it is asked. This decides what to do next from what the
                target just did - press the same seam, pivot to another category,
                or drop the thread and move on.
              </p>
              <p>
                Every tool call the target attempts is intercepted on the way
                through and logged whether or not it runs. A leak is as often
                there as in anything the target said.
              </p>
            </div>
          </div>

          <figure>
            {/* Two frames, not one with thick padding: the outer holds the tint
                and the inner holds the white plate, which is what gives the
                panel an edge you can see on a white page. */}
            <div className="rounded-[28px] bg-surface-2/70 p-3">
              <div className="rounded-[20px] border border-line bg-surface px-6 py-10 sm:px-10">
                <Fig1 />
              </div>
            </div>
          </figure>
        </div>
      </div>
    </section>
  );
}

/**
 * The notice that floats over the top-right of the field. A system notification
 * is the right shape for it: the whole promise of the band below is that you
 * point Sentinel at something and it tells you when it got in.
 *
 * The wording is a real finding — rag_context_poisoning is an authorizable
 * category, findings are rerun to prove they reproduce, and the severity is
 * arithmetic. Nothing here is a number the page invented.
 */
function Notice() {
  return (
    <div className="w-full max-w-xs shrink-0 rounded-2xl bg-white/75 p-3.5 shadow-[0_18px_50px_rgba(8,20,40,0.22)] backdrop-blur-md sm:w-80">
      <div className="flex gap-3">
        <span
          aria-hidden
          className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-[10px] bg-crit/15 font-mono text-[15px] text-crit"
        >
          !
        </span>
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <p className="text-[13px] font-semibold text-ink">Finding confirmed</p>
            <span className="ml-auto font-mono text-[10px] text-ink-mute">now</span>
          </div>
          <p className="mt-1 text-[12.5px] leading-snug text-ink-dim">
            rag_context_poisoning reproduced on every rerun. Severity 8.4,
            critical.
          </p>
        </div>
      </div>
    </div>
  );
}

/**
 * Closing field. Full-bleed pixel art with the copy set over it.
 *
 * Rounded and inset from the page edge rather than edge-to-edge, so it reads as
 * a plate laid on the white rather than the page changing colour — which is what
 * lets it follow two white bands without a rule between them.
 *
 * The artwork is 736x415 and runs at roughly twice that here. That is the point
 * of choosing pixel art for it: `pixelated` turns the upscale into bigger
 * squares instead of a soft blur, and `unoptimized` keeps Next from re-encoding
 * an already-lossy JPEG a second time. `object-bottom` because the flowers are
 * along the lower edge — cropping from the centre would cut their heads off on a
 * wide viewport.
 */
export function Field() {
  return (
    <section className="bg-surface px-4 pb-6 sm:px-6 sm:pb-8">
      <div className="relative isolate overflow-hidden rounded-[28px]">
        <Image
          src={sectionImg}
          alt=""
          fill
          unoptimized
          sizes="100vw"
          className="pixelated -z-10 object-cover object-bottom"
        />

        <div className="flex min-h-[34rem] flex-col justify-between gap-14 p-8 sm:p-12 lg:min-h-[42rem]">
          <div className="flex flex-col gap-10 sm:flex-row sm:items-start sm:justify-between">
            <div className="max-w-2xl">
              <h2 className="font-serif text-[clamp(2.1rem,5vw,3.8rem)] leading-[1.06] text-white ink-shadow">
                Sentinel goes after your agent the way somebody eventually will.
              </h2>
              {/* The same frosted material as the CTA below it. The art is at
                  its busiest right here — flower heads against sky — and a text
                  shadow alone cannot hold 14px type over that much contrast
                  change within a single line. */}
              <p className="mt-7 max-w-md rounded-2xl bg-white/15 px-5 py-4 text-[14px] leading-relaxed text-white ring-1 ring-white/25 backdrop-blur-md ink-shadow">
                Jailbreaks, guardrail bypasses, data leaks and unsafe tool calls
                — probed under a scope you signed, on a budget you capped.
              </p>
              <Link
                href="/console"
                className="group mt-8 inline-flex items-center gap-2 rounded-xl bg-white/20 px-5 py-3 text-[13.5px] font-medium text-white ring-1 ring-white/30 backdrop-blur-md transition hover:bg-white/30"
              >
                Start an audit
                <Arrow />
              </Link>
            </div>

            <Notice />
          </div>

          <div className="max-w-60">
            <Ticks className="text-white/70" />
            <p className="mt-4 text-[14px] leading-snug text-white ink-shadow">
              Every agent needs an adversary. Not every team has the week.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

/**
 * Card gallery of what a run goes after.
 *
 * The caption plate is the same frosted material as the field band above, for
 * the same reason: these are photographs with weather in them, and a title set
 * straight onto one would cross three different luminances in a single line.
 * It floats clear of the card's lower edge rather than sitting flush, so the
 * artwork reads as continuing behind it.
 */
export function Threats() {
  return (
    <section id="threats" className="scroll-mt-24 bg-surface">
      <div className="mx-auto max-w-6xl px-6 py-20 sm:py-28">
        <h2 className="max-w-3xl font-serif text-[clamp(1.9rem,4.4vw,3.2rem)] leading-[1.14] text-ink">
          What Sentinel goes looking for
        </h2>
        <Link
          href="/console"
          className="group mt-7 inline-flex items-center gap-2 border-b border-ink/25 pb-0.5 text-[13.5px] text-ink transition hover:border-ink"
        >
          Authorize a scope
          <Arrow className="bg-ink/10 group-hover:bg-ink/20" />
        </Link>

        <ul className="mt-14 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {THREATS.map((t) => (
            <li
              key={t.slug}
              className="relative isolate aspect-7/6 overflow-hidden rounded-2xl"
            >
              <Image
                src={t.img}
                alt=""
                fill
                unoptimized
                sizes="(min-width: 1024px) 22rem, (min-width: 640px) 45vw, 90vw"
                className="pixelated -z-10 object-cover"
              />
              {/* min-h is the two-line case measured out — 2×20.6 of title,
                  10 of gap, 16.5 of slug and 32 of padding, so a card whose
                  title fits on one line still matches the one that wraps.
                  justify-center is what keeps the short titles optically
                  centred in that box rather than riding its top edge, and it
                  is min- rather than fixed so a third line at a narrow width
                  grows the plate instead of spilling out of it. */}
              <div className="absolute inset-x-3 bottom-5 flex min-h-25 flex-col justify-center rounded-xl bg-white/15 px-5 py-4 text-center ring-1 ring-white/25 backdrop-blur-md">
                <p className="text-[15px] leading-snug font-medium text-white ink-shadow">
                  {t.title}
                </p>
                <p className="mt-2.5 font-mono text-[11px] text-white/75">
                  {t.slug}
                </p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export function Footer() {
  return (
    <footer className="border-t border-line bg-bg">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-6 py-10 sm:flex-row sm:items-center sm:justify-between">
        <p className="font-mono text-[11px] text-ink-mute">
          Sentinel — authorized testing only.
        </p>
        <p className="max-w-md font-mono text-[10px] leading-relaxed text-ink-mute">
          Run it against targets you own or have written permission to test.
        </p>
      </div>
    </footer>
  );
}
