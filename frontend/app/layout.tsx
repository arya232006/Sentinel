import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sentinel — Agentic AI Red-Team Auditor",
  description:
    "Adversarially probe a target AI agent and produce a severity-scored, reproducible vulnerability report.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      {/* System font stacks are declared in globals.css, so the console renders
          identically with no network access — it is often run offline. */}
      <body className="min-h-dvh antialiased">{children}</body>
    </html>
  );
}
