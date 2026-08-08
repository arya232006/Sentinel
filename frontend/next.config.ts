import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emits .next/standalone with a self-contained server.js and only the
  // node_modules actually reached, so the runtime image does not carry the full
  // dependency tree. `npm run dev` and `npm run start` are unaffected.
  output: "standalone",
};

export default nextConfig;
