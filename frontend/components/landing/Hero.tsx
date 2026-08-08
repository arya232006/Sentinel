"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState, useSyncExternalStore, type RefObject } from "react";
import heroImg from "@/public/hero.png";
import { Arrow } from "./Arrow";
import { NAV_LINKS as LINKS } from "./links";
import { Mark } from "@/components/Mark";

/**
 * The wall clock is an external system, so it is subscribed to rather than
 * mirrored into state — no setState in an effect, and no cascading render.
 *
 * getServerSnapshot returns null deliberately. The server's clock and timezone
 * are not the browser's, so rendering a time during SSR is a guaranteed
 * hydration mismatch; the cluster is simply absent until hydration instead.
 */
const clock = {
  subscribe(onChange: () => void) {
    const id = setInterval(onChange, 1000);
    return () => clearInterval(id);
  },
  now: () => new Date().toLocaleTimeString("en-GB", { hour12: false }),
  onServer: () => null,
};

/**
 * The IANA city is not always the city to show. All of India is one zone, named
 * Asia/Kolkata and still reported as the legacy Asia/Calcutta alias by some
 * systems, so the label is overridden rather than derived from the zone name.
 * These are display names only — nothing here affects the time itself.
 */
const ZONE_LABELS: Record<string, string> = {
  "Asia/Calcutta": "Bangalore",
  "Asia/Kolkata": "Bangalore",
};

function Clock() {
  const now = useSyncExternalStore<string | null>(
    clock.subscribe,
    clock.now,
    clock.onServer,
  );

  if (!now) return null;
  const iana = Intl.DateTimeFormat().resolvedOptions().timeZone ?? "";
  const zone = ZONE_LABELS[iana] ?? (iana.split("/").pop() ?? "").replace(/_/g, " ");
  return (
    <span className="inline-flex items-center gap-2 font-mono text-[11px] tracking-wide text-white/80 ink-shadow">
      <svg viewBox="0 0 16 16" aria-hidden className="size-3.5" fill="none">
        <circle cx="8" cy="8" r="6.4" stroke="currentColor" strokeWidth="1.1" />
        <path d="M8 4.4V8l2.6 1.6" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
      </svg>
      {now}
      {zone ? <span className="text-white/55 uppercase">{zone}</span> : null}
    </span>
  );
}

/**
 * Whether the fixed nav has left the hero photograph and now sits over the light
 * bands below it.
 *
 * An IntersectionObserver rather than a scroll handler: Lenis moves the scroll
 * position on every frame it animates, and a handler there would do work on all
 * of them to answer a question whose answer changes twice. Pulling the root's
 * top edge down to the nav's own lower edge is what makes "the hero has stopped
 * intersecting" mean exactly "the nav has cleared it" — so the switch fires as
 * the last of the photograph passes under the pill, not a viewport later.
 *
 * Starts false, which is what the server renders and what is true at scroll 0,
 * so hydration matches and the first observer callback is a no-op.
 */
function useOverLight(
  hero: RefObject<HTMLElement | null>,
  nav: RefObject<HTMLElement | null>,
) {
  const [over, setOver] = useState(false);

  useEffect(() => {
    const heroEl = hero.current;
    const navEl = nav.current;
    if (!heroEl || !navEl) return;

    let observer: IntersectionObserver | undefined;

    // rootMargin is fixed once the observer exists, so the nav is re-measured
    // and the observer rebuilt whenever its height can have changed — the
    // section links collapse below sm, which shortens the pill.
    const watch = () => {
      observer?.disconnect();
      const edge = Math.round(navEl.getBoundingClientRect().bottom);
      observer = new IntersectionObserver(
        ([entry]) => setOver(!entry.isIntersecting),
        { rootMargin: `-${edge}px 0px 0px 0px` },
      );
      observer.observe(heroEl);
    };

    watch();
    window.addEventListener("resize", watch);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", watch);
    };
  }, [hero, nav]);

  return over;
}

/**
 * A squircle rather than a pill. The inner radii are the shell's 16px less its
 * 8px of padding — that subtraction is what keeps the CTA and the mark chip
 * concentric with the shell rather than merely rounded, and it is why these
 * three radii have to move together if any one of them changes.
 *
 * `light` inverts the chrome for the light bands below the hero. Only the
 * foreground and the veil move: the CTA is a dark chip on both grounds and so
 * keeps its own colours throughout.
 */
function Nav({ light }: { light: boolean }) {
  return (
    <nav
      className={`glass nav-cross flex items-center gap-3 rounded-2xl p-2 font-ui ${
        light ? "glass-ink" : ""
      }`}
    >
      <Link
        href="/"
        aria-label="Sentinel"
        className={`nav-cross flex size-9 items-center justify-center rounded-[10px] ${
          light
            ? // The brand teal is about 1.4:1 on white, so the mark steps down to
              // the dim accent rather than fading out with the background.
              "bg-black/5 text-accent-dim hover:bg-black/10"
            : "bg-white/20 text-accent hover:bg-white/30"
        }`}
      >
        {/* 12px, not the 16px the reticle used: the grid is 12 cells, so this
            is the size where one cell is exactly one CSS pixel and two device
            pixels at 2x. At 16px a cell is 1.33px and crispEdges has to round,
            which lands some cells 2px wide and others 3px. */}
        <Mark className="size-3" />
      </Link>

      {/* Section links collapse below sm; the mark and the CTA never do. */}
      <div className="hidden items-center gap-1 sm:flex">
        {LINKS.map((l) => {
          const Tag = l.href.startsWith("#") ? "a" : Link;
          return (
            <Tag
              key={l.href}
              href={l.href}
              className={`nav-cross rounded-[10px] px-4 py-2 text-[14px] ${
                light
                  ? "ink-shadow-clear text-black/70 hover:bg-black/6 hover:text-black"
                  : "ink-shadow text-white/85 hover:bg-white/20 hover:text-white"
              }`}
            >
              {l.label}
            </Tag>
          );
        })}
      </div>

      <Link
        href="/console"
        className="group inline-flex items-center gap-2 rounded-[10px] bg-bg/85 px-5 py-2.5 text-[13px] font-medium text-white ring-1 ring-white/15 transition hover:bg-bg"
      >
        Start an audit
        <Arrow />
      </Link>
    </nav>
  );
}

export function Hero() {
  const heroRef = useRef<HTMLElement>(null);
  const navRef = useRef<HTMLDivElement>(null);
  const overLight = useOverLight(heroRef, navRef);

  return (
    <>
      {/*
       * Fixed, and deliberately outside the section below. Two reasons it cannot
       * simply be a class on the old header:
       *
       * `sticky` would not work — the hero clips its background image with
       * overflow-hidden, which makes it a scroll container, so a sticky nav
       * inside it would unpin as soon as the hero scrolled away.
       *
       * And the fixed element has to be the *ancestor* of `.rise`, not a
       * descendant: while that animation runs it holds a transform, and a
       * transformed ancestor becomes the containing block for a fixed
       * descendant, so the nav would be positioned against the wrapper and then
       * jump to the viewport the moment the animation resolved to `none`.
       */}
      <div
        ref={navRef}
        className="fixed inset-x-0 top-0 z-50 flex justify-center px-5 pt-6 sm:px-8"
      >
        {/* No `rise` wrapper here, unlike the masthead and the card. That
            animation holds a transform, and a transformed ancestor becomes the
            backdrop root for a backdrop-filter beneath it — the nav's blur would
            sample an empty subtree instead of the page and flatten to a plain
            translucent white. Browsers also tend to keep the promoted layer
            after the animation settles, so it does not reliably recover. */}
        <Nav light={overLight} />
      </div>

      <section
        ref={heroRef}
        className="relative isolate flex min-h-dvh flex-col overflow-hidden"
      >
        <Image
          src={heroImg}
          alt=""
          fill
          priority
          placeholder="blur"
          sizes="100vw"
          className="-z-10 object-cover object-center"
        />

        {/* No scrims. The nav and the card carry their own frosted backing, and a
            dark wash behind the nav was the reason its glass read flat and grey
            while the card over open sky read light and colourful — the veil can
            only pick up the colour that is actually behind it. */}

        {/* The nav is fixed and so contributes nothing to the flow; this reserves
            its footprint (24px inset + the ~58px pill) so the masthead keeps the
            vertical rhythm it had, and so the clock is not left sitting under the
            nav on the narrow screens where the two share the centre. */}
        <header className="relative px-5 pt-20 sm:px-8">
          {/* Static on small screens so it cannot collide with the nav pill. */}
          <div className="mt-4 flex justify-center lg:absolute lg:top-8 lg:right-8 lg:mt-0 lg:justify-end">
            <Clock />
          </div>
        </header>

        <div className="relative flex flex-1 flex-col justify-between gap-16 px-5 pt-16 pb-10 sm:px-8 sm:pt-20">
          {/* glow-text sits on the spans, not the h1: the spans are what set the
              font-size, and the glow is measured in em. */}
          <h1
            className="rise text-center font-display leading-[1.08] text-white"
            style={{ animationDelay: "120ms" }}
          >
            <span className="glow-text block text-[clamp(1.9rem,4.8vw,3.5rem)]">
              Sentinel
            </span>
            <span className="glow-text mt-1 block text-[clamp(0.8rem,1.8vw,1.3rem)] text-white/85">
              Agentic AI Red-Team Auditor
            </span>
          </h1>

          {/* Bottom-left glass card, as in the reference layout. */}
          <div
            className="rise glass max-w-lg rounded-3xl p-7 sm:p-9"
            style={{ animationDelay: "260ms" }}
          >
            <h2 className="font-display text-[clamp(1.8rem,4vw,2.75rem)] leading-[1.12] text-white ink-shadow">
              AI that red-teams AI
            </h2>
            <p className="mt-4 max-w-md text-[13.5px] leading-relaxed text-white/85 ink-shadow">
              Sentinel adversarially probes a target agent for jailbreaks,
              guardrail bypasses, data leaks and unsafe tool calls — then produces
              a severity-scored report with a minimized prompt you can rerun
              yourself.
            </p>
            {/* Stays on the page — this one is an invitation to read on, not a
                shortcut past everything to the tool. */}
            <a
              href="#adversary"
              className="group mt-6 inline-flex items-center gap-2 border-b border-white/35 pb-0.5 text-[13.5px] text-white transition hover:border-white"
            >
              Get to know it
              <Arrow />
            </a>
          </div>
        </div>
      </section>
    </>
  );
}
