"use client";

import { ReactLenis } from "lenis/react";
import "lenis/dist/lenis.css";

/**
 * Lenis smooth scroll, for the landing page.
 *
 * `root` binds to the window scroller rather than wrapping the page in Lenis's
 * own scroll container, so the layout, the hero's absolute positioning and the
 * section anchors all stay exactly as they were.
 *
 * Mounted on the landing page rather than in app/layout.tsx deliberately. Lenis
 * takes over the wheel by calling preventDefault on it, and the run and
 * engagement views are grids of fixed-height panels that scroll internally and
 * update live — hijacking the wheel there would fight the operator for no gain,
 * since those pages barely scroll at the document level.
 *
 * prefers-reduced-motion needs nothing here: Lenis honours it by default
 * (respectReducedMotion), dropping to 1:1 tracking with instant anchor jumps.
 */
export function SmoothScroll() {
  return (
    <ReactLenis
      root
      options={{
        // A little heavier than the 0.1 default. The hero is a full viewport, so
        // the glide carries better slightly longer without feeling laggy.
        lerp: 0.085,
        // Hands the #adversary / #threats nav links to Lenis. Its
        // scrollTo reads the target's computed scroll-margin-top, so the
        // sections' existing scroll-mt-24 is respected and no offset is needed.
        anchors: true,
        // The console section's Panel bodies scroll inside themselves. Without
        // this, Lenis's preventDefault would swallow those wheel gestures and
        // the scope list could not be scrolled at all.
        allowNestedScroll: true,
      }}
    />
  );
}
