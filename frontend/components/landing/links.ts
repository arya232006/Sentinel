/**
 * The page's own table of contents, in page order, shared by the nav and the
 * footer so the two cannot drift.
 *
 * Its own module rather than an export from Hero.tsx: Sections.tsx renders on
 * the server, and importing anything from a "use client" module — even a plain
 * array — pulls that module across the boundary.
 *
 * The last one leaves the page. That distinction is rendered, not cosmetic: a
 * hash has to stay a plain <a> so Lenis's anchor handling gets the click, while
 * a route wants next/link for the client transition — and Link on a bare hash
 * would run its own shallow scroll against Lenis for the same property.
 */
export const NAV_LINKS = [
  { href: "#adversary", label: "Why an adversary" },
  { href: "#threats", label: "What it finds" },
  { href: "/console", label: "Console" },
];
