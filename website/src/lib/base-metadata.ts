import type { Metadata } from "next";
import { BASE_PATH } from "./basePath";
import { SITE_ORIGIN, site } from "./site";

const SOCIAL_IMAGE = `${BASE_PATH}/og-image.png`;

/**
 * Site-wide base metadata (§54): title template, description, canonical root,
 * and social cards (static, brand-true 1200×630 card from public/og-image.png;
 * metadataBase is only set when a deploy origin exists so local builds never
 * fabricate absolute URLs).
 */
export const baseMetadata: Metadata = {
  metadataBase: SITE_ORIGIN ? new URL(`${SITE_ORIGIN}${BASE_PATH}`) : undefined,
  title: {
    default: "SayIt — local voice typing for Windows and Linux",
    template: "%s — SayIt",
  },
  description: site.description,
  alternates: {
    canonical: "/",
  },
  openGraph: {
    type: "website",
    siteName: "SayIt",
    title: "SayIt — local voice typing for Windows and Linux",
    description: site.description,
    images: [{ url: SOCIAL_IMAGE, width: 1200, height: 630, alt: "SayIt — local push-to-talk voice typing" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "SayIt — local voice typing for Windows and Linux",
    description: site.description,
    images: [SOCIAL_IMAGE],
  },
};
