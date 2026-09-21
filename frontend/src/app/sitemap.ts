import type { MetadataRoute } from "next";

// Next.js file convention: this file becomes /sitemap.xml in the static export.
// `dynamic = 'force-static'` is required — without it the static export build fails
// (verified on Next.js 16.3.5, docs/verified.md).
export const dynamic = "force-static";

// Public, fixed production domain — not a secret and not an env-configurable client
// value. Same constant already hardcoded this way in app/core.py (GALLERY_BASE),
// app/emails.py (SITE) and scripts/check.py (BASE); docs/DECISIONS.md settles the
// one-service-one-domain shape, so this does not vary per environment.
const SITE = "https://studioface.app";

// Only pages worth a crawler's time: the sale page and the four legal pages a search
// engine may show directly. /g/ (a customer's own gallery), /recuperar/ and /api/,
// /internal/ are excluded from crawling in robots.ts and have no listing here either.
const LEGAL_PAGES = ["aviso-legal", "privacidad", "terminos", "cookies"];

// Task 23. The two Google Ads landing pages (frontend/src/app/foto-cv/page.tsx,
// frontend/src/app/foto-linkedin/page.tsx) — sale pages, same as home, so a crawler
// should reach them the same way.
const AD_PAGES = ["foto-cv", "foto-linkedin"];

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return [
    { url: `${SITE}/`, lastModified: now },
    ...AD_PAGES.map((slug) => ({ url: `${SITE}/${slug}/`, lastModified: now })),
    ...LEGAL_PAGES.map((slug) => ({
      url: `${SITE}/legal/${slug}/`,
      lastModified: now,
    })),
  ];
}
