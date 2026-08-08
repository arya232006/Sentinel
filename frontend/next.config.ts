import type { NextConfig } from "next";

// `output: "standalone"` emits .next/standalone — a self-contained server.js
// plus only the node_modules actually reached — which is exactly what the
// Dockerfile copies, and the reason the runtime image does not carry the full
// dependency tree.
//
// It is opt-in rather than always-on because it must NOT be set when Vercel
// builds this app. Vercel does its own output tracing and packages the server
// itself; its post-build step reads .next/next-server.js.nft.json, and a
// standalone build relocates that server output, so the deploy dies with
//
//     ENOENT: no such file or directory, open
//     '/vercel/path0/frontend/.next/next-server.js.nft.json'
//
// at "Running onBuildComplete from Vercel" — after an otherwise clean build,
// which is what makes it read as a mystery. Vercel gains nothing from
// standalone; it produces the equivalent itself.
//
// So the Dockerfile is the only thing that opts in. `npm run dev`, `npm run
// start` and a plain `npm run build` are unaffected.
const nextConfig: NextConfig = {
  ...(process.env.NEXT_OUTPUT_STANDALONE === "1" && !process.env.VERCEL
    ? { output: "standalone" as const }
    : {}),
};

export default nextConfig;
