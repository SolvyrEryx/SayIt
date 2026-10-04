import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// Vitest runs from the package root; import.meta.url is unreliable here.
const css = readFileSync(join(process.cwd(), "src", "app", "globals.css"), "utf8");

// The design system is only real if the tokens exist. This guard keeps the
// documented token contract in sync with globals.css — remove a token from the
// CSS and this test fails, so the design-system page can never go stale.
const REQUIRED_TOKENS = [
  "--bg-page",
  "--bg-surface",
  "--bg-subtle",
  "--text-strong",
  "--text-body",
  "--text-muted",
  "--border-subtle",
  "--border-strong",
  "--accent",
  "--accent-hover",
  "--accent-soft",
  "--accent-text",
  "--on-accent",
  "--record",
  "--record-soft",
  "--focus-ring",
  "--motion-fast",
  "--motion-base",
  "--motion-slow",
  "--motion-ease-soft",
  "--motion-ease-spring",
  "--shadow-card",
  "--shadow-lift",
];

describe("design tokens (globals.css)", () => {
  it.each(REQUIRED_TOKENS)("defines %s", (token) => {
    expect(css).toContain(`${token}:`);
  });

  it("ships a single light theme — no prefers-color-scheme overrides", () => {
    // Product decision (2026-10-03): the site no longer follows the OS theme;
    // every visitor gets the light design.
    expect(css).not.toMatch(/@media \(prefers-color-scheme: dark\)/);
  });

  it("collapses non-essential motion under prefers-reduced-motion", () => {
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\)/);
    expect(css).toMatch(/animation-duration: 0\.01ms !important/);
  });

  it("defines a visible global focus treatment", () => {
    expect(css).toMatch(/:focus-visible[\s\S]{0,120}outline: 2px solid var\(--focus-ring\)/);
  });

  it("maps semantic tokens into Tailwind utilities", () => {
    expect(css).toContain("@theme inline");
    expect(css).toContain("--color-accent: var(--accent)");
    expect(css).toContain("--color-page: var(--bg-page)");
  });
});
