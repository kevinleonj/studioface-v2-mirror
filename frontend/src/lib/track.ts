/**
 * The funnel, declared once.
 *
 * Before this the only event in the product was a server-side `purchase` through the
 * Measurement Protocol, so everything between arriving and paying was unmeasured and
 * every claim in docs/CONVERSION.md was an opinion. The UI rule is that we never argue
 * about conversion, we instrument it.
 *
 * The list is the contract, and tests/test_conversion_events.py holds both ends of it:
 * no call site may use a key that is not here, and no key may sit here unfired. The
 * second is the expensive failure — a name nobody sends shows up in GA4 as a flat line,
 * and a flat line reads as "this never happens" rather than "this was never measured".
 *
 * Naming rules verified 2026-09-18 (docs/verified.md): case sensitive, must start with
 * a letter, letters/numbers/underscores only, 40 characters, 25 parameters. None of
 * these may collide with an automatically collected name, which is why the step after
 * checkout is `checkout_click` and not `click`.
 */

export const EVENTS = {
  /** The before/after entered the viewport. H1: proof before price. */
  viewProof: "view_proof",
  /** The "¿me voy a parecer a mí?" answer was opened. H2. */
  faqIdentityOpen: "faq_identity_open",
  /** Files chosen. The first act that costs the visitor anything. H3. */
  uploadStart: "upload_start",
  /** The free preview was requested. H3, and the denominator for H7. */
  previewStarted: "preview_started",
  /** The preview IMAGE finished loading and the visitor saw their own face. H7.
   *  Fired on the img load event, not on the HTTP 200: P5 - an event named after a
   *  visible result fires when the result is visible. I1 was invisible in the data
   *  because this said "ready" while the browser was refusing the image. */
  previewReady: "preview_ready",
  /** A preview attempt did not put a face on the screen. Carries `reason`: the
   *  server's detail, `image_blocked` when the image itself would not load, or
   *  `network`. The denominator half of H3 that was never measured. */
  previewFailed: "preview_failed",
  /** The first-screen button, or the sticky one. Carries `location`: fold | sticky. */
  ctaClick: "cta_click",
  /** Checkout was asked for. The last click before Stripe owns the session. H5. */
  checkoutClick: "checkout_click",
  /** Somebody landed on /recuperar/ — every one of these is a lost gallery link. H6. */
  recuperarView: "recuperar_view",
  /** The gallery reported four delivered images to the person who bought them. H7. */
  orderDelivered: "order_delivered",
} as const;

export type EventName = (typeof EVENTS)[keyof typeof EVENTS];

/**
 * Fire and forget.
 *
 * `window.gtag` is absent far more often than it is present: consent defaults to denied,
 * GA4_ID is empty in every local build, and blockers remove the script outright. A
 * tracker that throws in that state takes the click handler down with it, and the event
 * is the least important thing on that line.
 */
export function track(
  name: EventName,
  params?: Record<string, string | number>,
): void {
  window.gtag?.("event", name, params);
}
