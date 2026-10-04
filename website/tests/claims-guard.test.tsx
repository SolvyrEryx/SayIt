import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { act, render } from "@testing-library/react";
import type { ReactElement } from "react";
import HomePage from "@/app/page";
import FeaturesPage from "@/app/features/page";
import PrivacyPage from "@/app/privacy/page";
import DesignSystemPage from "@/app/design/page";
import DownloadPage from "@/app/download/page";
import InstallPage from "@/app/install/page";

// The download page checks for a release manifest on mount; give it the
// honest "missing" answer instead of a real network request.
beforeAll(() => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false })));
});

afterAll(() => {
  vi.unstubAllGlobals();
});

/**
 * Content guard: no unsupported marketing claims anywhere (master plan §56,
 * §25, §36). Every page must stay free of fabricated superlatives, absolute
 * privacy/offline claims, and competitor references.
 */
const BANNED_PATTERNS: RegExp[] = [
  /perfect/i,
  /best/i,
  /industry-leading/i,
  /world-class/i,
  /state-of-the-art/i,
  /unmatched/i,
  /100% private/i,
  /fully offline/i,
  /works everywhere/i,
  /zero latency/i,
  /lightning|blazing/i,
  /thousands of users/i,
  /millions of/i,
  /wispr/i,
];

const PAGES: Array<[string, () => ReactElement]> = [
  ["home", () => <HomePage />],
  ["features", () => <FeaturesPage />],
  ["privacy", () => <PrivacyPage />],
  ["design", () => <DesignSystemPage />],
  ["download", () => <DownloadPage />],
  ["install", () => <InstallPage />],
];

describe("content claims guard", () => {
  it.each(PAGES)("%s page makes no unsupported claims", async (_name, renderPage) => {
    const { container } = render(renderPage());
    // Flush any deferred async work (e.g. the download page's manifest
    // check) so the guard scans the settled page, inside act().
    await act(async () => {});
    const text = container.textContent ?? "";
    for (const pattern of BANNED_PATTERNS) {
      expect(text, `expected no match for ${pattern}`).not.toMatch(pattern);
    }
  });

  it.each(PAGES.slice(0, 3))("%s page shows no version numbers", (_name, renderPage) => {
    const { container } = render(renderPage());
    expect(container.textContent ?? "").not.toMatch(/v?\d+\.\d+\.\d+/);
  });
});
