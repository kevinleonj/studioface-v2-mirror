import type { MetadataRoute } from "next";
import { PAGE_DATES } from "@/content/page-dates";

// Next.js file convention: this file becomes /sitemap.xml in the static export.
// `dynamic = 'force-static'` is required — without it the static export build fails
// (verified on Next.js 16.3.5, docs/verified.md).
export const dynamic = "force-static";

// Public, fixed production domain — not a secret and not an env-configurable client
// value. Same constant already hardcoded this way in app/core.py (GALLERY_BASE),
// app/emails.py (SITE) and scripts/check.py (BASE); docs/DECISIONS.md settles the
// one-service-one-domain shape, so this does not vary per environment.
const SITE = "https://studioface.app";

// Only pages worth a crawler's time, each with the date its content last changed
// (content/page-dates.ts, task 95a) - never the build time, so two builds of the same
// commit produce the same bytes. /g/ (a customer's own gallery), /recuperar/, /api/ and
// /internal/ are excluded from crawling in robots.ts and have no listing here either.
export default function sitemap(): MetadataRoute.Sitemap {
  return Object.entries(PAGE_DATES).map(([path, date]) => ({
    url: `${SITE}${path}`,
    lastModified: date,
  }));
}
