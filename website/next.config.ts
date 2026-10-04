import type { NextConfig } from "next";

// The website is a fully static distribution surface: `next build` emits a
// self-contained `out/` folder that any static file host can serve. No server
// runtime, no secrets, no client-side API dependencies. `trailingSlash` keeps
// URLs stable for plain static hosting (each route becomes a directory).
//
// NEXT_PUBLIC_BASE_PATH is set by the GitHub Pages deploy workflow (e.g.
// "/SayIt") so assets, routes, and the release-manifest fetch resolve
// under the repository sub-path. Local builds leave it unset (root).
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || undefined;

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  basePath,
  // Pin the workspace root to this package so Turbopack never walks up into
  // parent directories (e.g. a stray lockfile in the user profile).
  turbopack: {
    root: import.meta.dirname,
  },
};

export default nextConfig;
