/**
 * Build-time base path (inlined by Next from NEXT_PUBLIC_BASE_PATH). Empty
 * for local/default builds; "/<repo>" on GitHub Pages. Every hand-written
 * absolute fetch or asset path must go through this — client-side routing
 * handles it automatically via next/link.
 */
export const BASE_PATH: string = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
