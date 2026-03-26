import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // ── Next.js 16 Features ─────────────────────────────────

  // 1. Turbopack File System Cache — faster dev restarts
  //    Stores compiler artifacts on disk between runs
  experimental: {
    turbopackFileSystemCacheForDev: true,
  },

  // 2. Cache Components — requires refactoring dynamic pages
  //    Enable when admin dashboard uses real Neon queries (Phase 4)
  // cacheComponents: true,

  // 3. View Transitions — enabled via transitionTypes on <Link>
  //    CSS animations in globals.css, no config needed

  // 4. DevTools MCP — add to MCP client config:
  //    { "mcpServers": { "next-devtools": { "command": "npx", "args": ["-y", "next-devtools-mcp@latest"] } } }
};

export default nextConfig;
