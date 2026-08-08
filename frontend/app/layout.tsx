import type { Metadata } from "next";
import { Instrument_Sans, Instrument_Serif } from "next/font/google";
import { GeistPixelGrid } from "geist/font/pixel";
import "./globals.css";

/** Nav chrome only. Variable axes, so one file covers every weight the nav uses. */
const instrumentSans = Instrument_Sans({
  subsets: ["latin"],
  variable: "--font-instrument-sans",
  display: "swap",
});

/**
 * The statement band under the hero, and nothing else — a high-contrast serif is
 * the wrong face for an operator console. Its sans sibling is already loaded, so
 * the two share proportions and the pairing costs one more file.
 *
 * Not a variable font, so next/font needs the weight naming a single cut; 400 is
 * the only upright Instrument Serif ships.
 */
const instrumentSerif = Instrument_Serif({
  subsets: ["latin"],
  weight: "400",
  variable: "--font-instrument-serif",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Sentinel — Agentic AI Red-Team Auditor",
  description:
    "Adversarially probe a target AI agent and produce a severity-scored, reproducible vulnerability report.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${GeistPixelGrid.variable} ${instrumentSans.variable} ${instrumentSerif.variable}`}
    >
      {/* Body and mono stacks stay system fonts in globals.css, so the console
          renders identically with no network access — it is often run offline.
          Both webfonts are self-hosted out of .next by next/font, so nothing is
          fetched at runtime either; only `next build` needs to reach Google. */}
      <body className="min-h-dvh antialiased">{children}</body>
    </html>
  );
}
