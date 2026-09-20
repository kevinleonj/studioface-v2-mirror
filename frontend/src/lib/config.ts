/**
 * Public configuration. Every value here ships inside the page, so none of it is a
 * secret — CI writes these from GitHub variables into .env.production (deploy.yml).
 *
 * THERE IS NO API BASE, deliberately, and this is the fix for the third production
 * outage. `API_URL` was `https://api.studioface.app`, so every fetch went to a different
 * hostname than the page. The app installs no CORSMiddleware, so a preflight to any /api
 * path answers 405 with no access-control-allow-origin: /api/checkout preflighted and
 * died there, and /api/preview did not preflight but had its response withheld from the
 * page. Both dead, two mechanisms, one cause.
 *
 * Both hostnames are the same Cloud Run service and the same FastAPI process, which
 * serves this static export at "/" and wins on /api. So every browser request is a
 * relative path and CORS never enters into it — MDN: same-origin requests are not
 * subject to CORS at all.
 *
 * An empty API_URL would have worked too, and is exactly what must not exist: a value
 * that is "" today is one somebody sets tomorrow, and the outage returns with no code
 * change to review. api.studioface.app keeps serving the Stripe webhook and Cloud Tasks,
 * which are server-to-server, carry no Origin, and are unaffected.
 *
 * tests/test_same_origin.py fails on any absolute origin in a browser request, on the
 * name reappearing in config or in deploy.yml, and on the hostname reaching the bundle.
 */

export const TURNSTILE_SITEKEY = process.env.NEXT_PUBLIC_TURNSTILE_SITEKEY ?? "";
export const GA4_ID = process.env.NEXT_PUBLIC_GA4_ID ?? "";

export const PRICE_LABEL = "19,99 €";
// Same price as PRICE_LABEL, as a number for GA4's `value` parameter (begin_checkout)
// and for the home page's JSON-LD Product offer (page-head unit).
export const PRICE_EUR = 19.99;
export const MAX_FILES = 4;

// The production origin. Used for metadataBase (canonical, og:image resolve against
// it) and for JSON-LD, which Next's metadata API does not resolve for us.
export const SITE_URL = "https://studioface.app";
