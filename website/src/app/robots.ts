import type { MetadataRoute } from "next";
import { BASE_PATH } from "@/lib/basePath";
import { SITE_ORIGIN } from "@/lib/site";

export const dynamic = "force-static";

export default function robots(): MetadataRoute.Robots {
  if (!SITE_ORIGIN) {
    // Local/default builds: allow everything, no absolute sitemap to point at.
    return { rules: { userAgent: "*", allow: "/" } };
  }
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: `${SITE_ORIGIN}${BASE_PATH}/sitemap.xml`,
  };
}
