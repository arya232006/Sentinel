import { Hero } from "@/components/landing/Hero";
import {
  Adversary,
  Field,
  Footer,
  Threats,
  Vision,
} from "@/components/landing/Sections";
import { SmoothScroll } from "@/components/landing/SmoothScroll";

/**
 * The landing page, and nothing else — the console moved to /console, and with
 * it went every piece of state this file used to hold. That is why there is no
 * "use client" here any more: it renders on the server and ships no JS of its
 * own, with Hero and SmoothScroll carrying their own client boundaries.
 */
export default function HomePage() {
  return (
    <main className="min-h-dvh">
      <SmoothScroll />
      <Hero />

      {/* Everything past the hero runs light. One opaque wrapper rather than a
          class per section: the bands below draw from the semantic tokens and
          some of them paint translucent surfaces, which need an opaque light
          ground behind them or they would mix with the dark body and come out
          grey. The console and the run views stay dark — the theme is scoped to
          this subtree, so they never see it. */}
      <div className="theme-light">
        <Vision />
        <Adversary />
        <Field />
        <Threats />
        <Footer />
      </div>
    </main>
  );
}
