import { describe, expect, it } from "vitest";
import { baseMetadata as layoutMetadata } from "@/lib/base-metadata";
import { metadata as designMetadata } from "@/app/design/page";
import { metadata as downloadMetadata } from "@/app/download/page";
import { metadata as featuresMetadata } from "@/app/features/page";
import { metadata as installMetadata } from "@/app/install/page";
import { metadata as privacyMetadata } from "@/app/privacy/page";

/**
 * Metadata audit (Stage H / §54): every public page carries a description and
 * a canonical path; the internal design reference is noindex.
 */
describe("metadata audit", () => {
  it("layout defines the base metadata and social cards", () => {
    expect(layoutMetadata.title).toBeDefined();
    expect(layoutMetadata.description).toBeTruthy();
    expect(layoutMetadata.openGraph).toMatchObject({ type: "website", siteName: "SayIt" });
    expect(layoutMetadata.twitter).toMatchObject({ card: "summary_large_image" });
  });

  it("every public page has a description and canonical path", () => {
    const pages = [
      ["download", downloadMetadata],
      ["features", featuresMetadata],
      ["install", installMetadata],
      ["privacy", privacyMetadata],
    ] as const;

    for (const [name, metadata] of pages) {
      expect(metadata.description, `${name} description`).toBeTruthy();
      expect(metadata.alternates?.canonical, `${name} canonical`).toEqual(`/${name}`);
    }
  });

  it("the design-system reference is excluded from search indexing", () => {
    expect(designMetadata.robots).toEqual({ index: false, follow: false });
  });
});
