/**
 * Task 95a. When each page's CONTENT last changed: the one source for <lastmod> in
 * sitemap.xml. Never the build time - a lastmod that moves on every deploy tells crawlers
 * nothing, and IndexNow (task 95b) resubmits exactly the URLs whose lastmod changed.
 *
 * Seeded on 23 September 2026 from each page's last content commit
 * (`git log -1 --format=%cs -- <the page's own files>`). Change a page's words, change
 * its date here, in the same commit. A layout-only or styling change is not new content.
 *
 * Order is the order the sitemap lists them in. tests/test_sitemap_dates.py checks that
 * every built <lastmod> equals the date written here.
 */
export const PAGE_DATES = {
  "/": "2026-09-22",
  "/foto-cv/": "2026-09-21",
  "/foto-linkedin/": "2026-09-21",
  "/legal/aviso-legal/": "2026-09-18",
  "/legal/privacidad/": "2026-09-23",
  "/legal/terminos/": "2026-09-22",
  "/legal/cookies/": "2026-09-17",
} as const satisfies Record<string, string>;
