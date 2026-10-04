/**
 * Site-wide constants. Only real, verifiable URLs live here — download URLs
 * and versions will be introduced from the release manifest in a later stage
 * and must never be hardcoded per-page.
 */
import { BASE_PATH } from "./basePath";

export const site = {
  name: "SayIt",
  tagline: "Your voice. Your words. Typed anywhere.",
  description:
    "SayIt is a local push-to-talk voice-typing utility for Windows and Linux. Hold a hotkey, speak, release — the transcribed text is inserted at your cursor. Speech recognition runs on-device.",
  repositoryUrl: "https://github.com/VptrCipher/SayIt",
  releasesUrl: "https://github.com/VptrCipher/SayIt/releases",
  issuesUrl: "https://github.com/VptrCipher/SayIt/issues",
} as const;

/**
 * Absolute origin for canonical URLs, Open Graph images, robots.txt and
 * sitemap.xml. Set NEXT_PUBLIC_SITE_ORIGIN in the deploy workflow
 * (https://vptrcipher.github.io); local builds leave it unset and simply
 * omit absolute-URL metadata rather than fabricate one.
 */
export const SITE_ORIGIN: string = process.env.NEXT_PUBLIC_SITE_ORIGIN ?? "";

/** Absolute URL for a site-root-relative path, or null without an origin. */
export function absoluteUrl(path: string): string | null {
  if (!SITE_ORIGIN) return null;
  return `${SITE_ORIGIN}${BASE_PATH}${path}`;
}
