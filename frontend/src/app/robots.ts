import type { MetadataRoute } from "next";

// Next.js file convention: this file becomes /robots.txt in the static export.
// `dynamic = 'force-static'` is required — without it the static export build fails
// (verified on Next.js 16.3.5, docs/verified.md).
export const dynamic = "force-static";

// Public, fixed production domain — not a secret and not an env-configurable client
// value. Same constant already hardcoded this way in app/core.py (GALLERY_BASE),
// app/emails.py (SITE) and scripts/check.py (BASE); docs/DECISIONS.md settles the
// one-service-one-domain shape, so this does not vary per environment.
const SITE = "https://studioface.app";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // /g/ is a customer's gallery (order id + delivery token in the query string,
      // see tests/test_gallery_states.py). /api/ and /internal/ are not pages.
      // /recuperar/ only ever sends a delivery link to an address someone typed in.
      disallow: ["/g/", "/api/", "/internal/", "/recuperar/"],
    },
    sitemap: `${SITE}/sitemap.xml`,
  };
}
