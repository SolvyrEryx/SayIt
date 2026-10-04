import type { MetadataRoute } from "next";
import { BASE_PATH } from "@/lib/basePath";
import { SITE_ORIGIN } from "@/lib/site";

export const dynamic = "force-static";

// Public product pages only. The /design system reference is intentionally
// excluded (noindex) per the Stage H demotion decision.
const ROUTES = ["", "/download", "/install", "/features", "/privacy"];

export default function sitemap(): MetadataRoute.Sitemap {
  if (!SITE_ORIGIN) return [];
  const lastModified = new Date();
  return ROUTES.map((route) => ({
    url: `${SITE_ORIGIN}${BASE_PATH}${route || "/"}`,
    lastModified,
    changeFrequency: "weekly",
    priority: route === "" ? 1 : 0.7,
  }));
}
