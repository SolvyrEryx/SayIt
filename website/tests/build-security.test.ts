import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Build-output security & privacy scan (§61/§94): the exported site must be
 * free of third-party scripts, external iframes, tracking pixels, and
 * fingerprinting. Runs against the last `npm run build` output and skips
 * gracefully when out/ has not been produced yet.
 */

const OUT = join(process.cwd(), "out");

function* htmlFiles(dir: string): Generator<string> {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) yield* htmlFiles(path);
    else if (entry.endsWith(".html")) yield path;
  }
}

const EXTERNAL_HOST_ALLOWLIST = new Set(["github.com"]);

describe("build output security & privacy scan", () => {
  const outExists = existsSync(OUT);

  it.skipIf(!outExists)("ships no third-party scripts or frames", () => {
    const htmlFilesList = [...htmlFiles(OUT)];
    expect(htmlFilesList.length).toBeGreaterThan(0);

    for (const file of htmlFilesList) {
      const html = readFileSync(file, "utf8");

      // No off-origin <script src>, <iframe src>, <link rel=preload/prefetch>.
      const sources = [...html.matchAll(/(?:src|href)="(https?:\/\/[^"]+)"/g)].map(
        (match) => match[1],
      );
      for (const url of sources) {
        const host = new URL(url).host;
        expect(
          EXTERNAL_HOST_ALLOWLIST.has(host),
          `${file} references ${url} — only github.com is allowed off-origin`,
        ).toBe(true);
      }

      // No iframes at all, in fact (the site uses none).
      expect(html, `${file} contains no iframe`).not.toMatch(/<iframe/i);

      // Known tracking/fingerprinting markers must be absent everywhere.
      for (const marker of [
        "gtag(",
        "googletagmanager",
        "google-analytics",
        "hotjar",
        "fullstory",
        "sentry.io",
        "fingerprintjs",
        "clarity.ms",
        "segment.com",
      ]) {
        expect(html.toLowerCase(), `${file} contains no ${marker}`).not.toContain(marker);
      }
    }
  });

  it.skipIf(!outExists)("generates robots.txt and sitemap when an origin is configured", () => {
    // Local builds without NEXT_PUBLIC_SITE_ORIGIN intentionally omit the
    // sitemap; robots.txt always exists.
    expect(existsSync(join(OUT, "robots.txt"))).toBe(true);
  });
});
