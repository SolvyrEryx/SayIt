import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { act, render } from "@testing-library/react";
import type { ReactElement } from "react";
import HomePage from "@/app/page";
import FeaturesPage from "@/app/features/page";
import PrivacyPage from "@/app/privacy/page";
import DesignSystemPage from "@/app/design/page";
import DownloadPage from "@/app/download/page";
import InstallPage from "@/app/install/page";
import { site } from "@/lib/site";

// The download page checks for a release manifest on mount; give it the
// honest "missing" answer instead of a real network request.
beforeAll(() => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false })));
});

afterAll(() => {
  vi.unstubAllGlobals();
});

// Every route the site serves. The /design reference is included here so its
// in-page links stay honest even though it is noindex.
const ROUTES = new Set(["/", "/download", "/install", "/features", "/privacy", "/design"]);

const EXTERNAL_ALLOWED = new Set<string>([
  site.repositoryUrl,
  site.releasesUrl,
  site.issuesUrl,
]);

const PAGES: Array<[string, () => ReactElement]> = [
  ["home", () => <HomePage />],
  ["features", () => <FeaturesPage />],
  ["privacy", () => <PrivacyPage />],
  ["design", () => <DesignSystemPage />],
  ["download", () => <DownloadPage />],
  ["install", () => <InstallPage />],
];

describe("link audit — no dead links anywhere (§82)", () => {
  it.each(PAGES)("%s page links only to real targets", async (_name, renderPage) => {
    const { container } = render(renderPage());
    // Flush the download page's async manifest check inside act().
    await act(async () => {});

    const anchors = [...container.querySelectorAll("a")];
    expect(anchors.length).toBeGreaterThan(0);

    for (const anchor of anchors) {
      const href = anchor.getAttribute("href");
      expect(href, "every anchor has an href").not.toBeNull();
      const value = href as string;

      if (value.startsWith("#")) {
        // In-page anchors must resolve to a real id in the rendered page.
        const target = document.getElementById(value.slice(1));
        expect(target, `anchor target ${value} exists on the page`).not.toBeNull();
        continue;
      }

      if (value.startsWith("//") || value.startsWith("http")) {
        expect(EXTERNAL_ALLOWED.has(value), `${value} is an allowlisted external URL`).toBe(true);
        continue;
      }

      // Internal path: strip hash and trailing slash, then match a real route.
      const [pathPart] = value.split("#");
      const normalized = pathPart.length > 1 ? pathPart.replace(/\/$/, "") : "/";
      expect(ROUTES.has(normalized), `${value} points at a real route`).toBe(true);
    }
  });
});
