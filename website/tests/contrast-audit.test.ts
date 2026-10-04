import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// ---------------------------------------------------------------------------
// WCAG contrast audit (Stage H): computed from the token values actually in
// globals.css — light and dark — so the stylesheet can never silently regress
// below AA for the text/background pairs this site composes.
// ---------------------------------------------------------------------------

const css = readFileSync(join(process.cwd(), "src", "app", "globals.css"), "utf8");

function extractBlock(afterMarker: string): string {
  const index = css.indexOf(afterMarker);
  return index === -1 ? "" : css.slice(index);
}

const lightBlock = extractBlock(":root");

// The site ships a single light theme (product decision, 2026-10-03) — there
// is no prefers-color-scheme: dark block to audit anymore.

function tokenValue(block: string, name: string): string | null {
  const match = new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`).exec(block);
  return match ? match[1].toLowerCase() : null;
}

function luminance(hex: string): number {
  const value = hex.replace("#", "");
  const channels = [0, 2, 4].map((offset) => {
    const channel = parseInt(value.slice(offset, offset + 2), 16) / 255;
    return channel <= 0.03928
      ? channel / 12.92
      : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrastRatio(foreground: string, background: string): number {
  const l1 = luminance(foreground);
  const l2 = luminance(background);
  const [lighter, darker] = l1 >= l2 ? [l1, l2] : [l2, l1];
  return (lighter + 0.05) / (darker + 0.05);
}

const THEMES = {
  light: lightBlock,
} as const;

const TEXT_PAIRS: Array<[string, string]> = [
  // [foreground token, background token] — AA normal text: 4.5:1
  ["text-body", "bg-page"],
  ["text-body", "bg-surface"],
  ["text-body", "bg-subtle"],
  ["text-strong", "bg-page"],
  ["text-strong", "bg-surface"],
  ["text-strong", "bg-subtle"],
  ["text-strong", "accent-soft"],
  ["text-muted", "bg-page"],
  ["text-muted", "bg-surface"],
  ["text-muted", "bg-subtle"],
  ["on-accent", "accent"],
  ["on-accent", "accent-hover"],
  ["accent-text", "bg-page"],
  ["accent-text", "bg-surface"],
];

const NON_TEXT_PAIRS: Array<[string, string]> = [
  // focus rings and meaningful borders: 3:1
  ["focus-ring", "bg-page"],
  ["text-body", "bg-page"],
];

describe("WCAG contrast audit", () => {
  for (const [themeName, block] of Object.entries(THEMES)) {
    it(`${themeName} theme: tokens resolve`, () => {
      for (const [foreground] of [...TEXT_PAIRS, ...NON_TEXT_PAIRS]) {
        expect(tokenValue(block, foreground), `${themeName} --${foreground}`).not.toBeNull();
      }
    });

    it.each(TEXT_PAIRS)(`${themeName}: %s on %s is at least 4.5:1`, (foreground, background) => {
      const fg = tokenValue(block, foreground);
      const bg = tokenValue(block, background);
      const ratio = contrastRatio(fg as string, bg as string);
      expect(ratio, `${themeName} ${foreground} on ${background}`).toBeGreaterThanOrEqual(4.5);
    });

    it.each(NON_TEXT_PAIRS)(`${themeName}: %s on %s is at least 3:1`, (foreground, background) => {
      const fg = tokenValue(block, foreground);
      const bg = tokenValue(block, background);
      const ratio = contrastRatio(fg as string, bg as string);
      expect(ratio, `${themeName} ${foreground} on ${background}`).toBeGreaterThanOrEqual(3);
    });
  }
});
