import { describe, expect, it } from "vitest";
import { isInternalHref } from "@/components/Button";
import { BASE_PATH } from "@/lib/basePath";
import { MANIFEST_URL } from "@/lib/release";

describe("isInternalHref", () => {
  it("treats root-relative paths as internal", () => {
    expect(isInternalHref("/download")).toBe(true);
    expect(isInternalHref("/")).toBe(true);
    expect(isInternalHref("/#platforms")).toBe(true);
  });

  it("keeps protocol-relative, external, and hash-only hrefs out of next/link", () => {
    expect(isInternalHref("//evil.example")).toBe(false);
    expect(isInternalHref("https://github.com/VptrCipher/SayIt")).toBe(false);
    expect(isInternalHref("#how-it-works")).toBe(false);
  });
});

describe("basePath handling", () => {
  it("leaves local builds at the root", () => {
    // NEXT_PUBLIC_BASE_PATH is only set by the GitHub Pages deploy workflow.
    expect(BASE_PATH).toBe("");
    expect(MANIFEST_URL).toBe("/release-manifest.json");
  });
});
