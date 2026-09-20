# StudioFace — round 5 design critique — verdict

**FAIL** (blocker on line 7, tap targets, overrides the 41/50 total — see rubric.md).

Server: `frontend/out` was copied to `C:\Users\KEVIN\AppData\Local\Temp\sf-review-r5` before
serving (`python -m http.server 8903` run from inside the copy). The copy, not `frontend/out`
itself, was served throughout. **The server was killed before finishing this review** (`taskkill
/PID 33136 /F`, confirmed with a follow-up `curl` returning connection-refused / `000`).

## Blockers

- **Line 7 — Thumb reach and tap targets: 1/5.** `/g/`'s "Descargar" and "Volver a intentarlo",
  and `/recuperar/`'s "Enviarme el enlace", all measure **32px** tall on the live page
  (`getBoundingClientRect`, not read from CSS). That is smaller than the 36px violation the team
  already found and fixed once on the landing page (`tests/test_tap_targets.py` docstring). It
  comes from `buttonVariants()` called without `size="lg"` — either as a bare `<a
  className={buttonVariants()}>` (`frontend/src/app/g/page.tsx:117-123`, `:239`) or a `<Button>`
  with no `size` prop (`frontend/src/app/recuperar/page.tsx`, the submit button). The existing
  regression test only regexes `<Button\b` tags inside `upload-form.tsx`, so it cannot see either
  code path. This is not a peripheral control — one is the literal action of collecting the four
  photos a customer paid 19,99 € for, and one is the only action on the page a buyer reaches after
  losing their gallery link.

No other line scored 0 or 1.

## Three highest-leverage changes, ordered by score-moved per unit of work

1. `frontend/src/app/g/page.tsx:117-123` and `:239`, and `frontend/src/app/recuperar/page.tsx`
   (the `<Button type="submit">` with no size prop) — add `size="lg"` (or, for the `<a>` tags,
   pass `size: "lg"` into `buttonVariants({ size: "lg" })`). This is a one-line-per-site change,
   directly clears the line-7 blocker, and should be caught in CI: extend
   `tests/test_tap_targets.py`'s second test to scan `g/page.tsx` and `recuperar/page.tsx` too, or
   better, grep the whole `frontend/src` tree for `buttonVariants()` calls and `<Button>` tags
   without an explicit `size`, so this class of regression cannot come back a third time.

2. `frontend/src/components/more-muestras.tsx:67` — the placeholder is `aspect-[2/1]`; change it to
   match the actual rendered pair ratio. I measured the real pair at 342px width as 279.875px tall
   (≈1.6:1, not 2:1 and not the 4:5 the comment claims), so the placeholder should be
   `aspect-[1.222/1]` (342/280) or, more robustly, sized from the same `Pair` component in a
   `visibility:hidden` state so the two can never drift apart again. This removes a measured
   63.7% height jump that fires on load for every visitor who scrolls this far, which the design
   audit script structurally cannot catch.

3. `frontend/src/app/page.tsx:70-83` — the price block with "IVA incluido, pago único" renders at
   y=819–847 on first visit at 390x844, entirely behind/below the 691px slot the consent banner
   leaves (measured: `bannerRect.top = 691`, `heroPriceRect.top = 819.25`). Only the small, muted
   14px "19,99 €" in the header is inside the visible slot, without "IVA incluido" attached to it.
   This is a real trade (line 1 asks whether it reads as decided or as a page that lost its price)
   and I judge it as decided-but-costly rather than broken: the header price exists and is genuine,
   but a first-time visitor on a phone sees a bare price with no tax/no-registration context until
   they act on the cookie banner or scroll. Cheapest fix: add "IVA incluido" after the header price
   span (`site-header.tsx:54`) so the one price a first-visit phone user can actually see carries
   the same trust information the buried one does — a text change, not a layout change.

## What I would keep

The five named motion moments (`frontend/src/app/globals.css:167-203`), specifically that the
focus ring's `box-shadow` on `.sf-focus:focus-visible` (line 142-147) has **no transition** and
therefore appears in a single frame. I Tab-confirmed this on the live checkout button
(`08-checkout-focus-390.png`): the ring is legible, on-brand (cream inner ring + red outer ring,
not the browser default), and instant. Keyboard-first attention to the one state "nobody designs"
is rare, it is verified working on the actual money-path button, and it is exactly the kind of
finding a static screenshot review would miss if I had not Tabbed to it myself.

## Captures that failed or required a workaround (full honesty list)

- **/g/ processing, delivered, refunded, refund-pending**: the backend does not exist in this
  static export. I could not reach these through the real API. I reached them by placing literal
  JSON fixture files on the served COPY at `sf-review-r5\api\orders\<order>\<token>` (e.g.
  `{"status":"delivered","images":[...]}`), which the page's own `fetch("/api/orders/<o>/<t>")`
  picks up as a genuine 200 response from the static file server — no application code, test, or
  `frontend/out` file was touched. This is a workaround, not a real backend integration test.
- **Landing preview rendering/rendered**: same limitation, same workaround, this time by
  overriding `window.fetch` inside the page via `browser_evaluate` to delay and then resolve
  `/api/preview` with a fabricated handle pointing at an existing sample JPG. The "rendered" image
  shown is therefore a sample photo, not a real generation — the UI chrome around it (labels,
  animation, wardrobe select, checkout button) is real.
- **Natural 404 on `/g/`**: navigating to `/g/?o=ord_test123&t=tok_abc` before I added fixture
  files returned a genuine static-server 404, which the page correctly renders as "Este enlace no
  es válido o ha caducado." (`12-gallery-notfound-390.png`). That capture is real, unstubbed
  behaviour, not a workaround.
- Everything else listed in the task (landing at both sizes, `/g/` delivered at both sizes,
  `/recuperar/` at both sizes, hover, file-chosen, keyboard focus, invalid email) was captured
  directly against the served static export with no stubbing.
- Legal pages, `/muestras/` route and dark mode were not requested this round and were not
  captured.

## Screenshots (in this folder)

`01-landing-390x844-firstvisit.png` (consent banner up, real first visit) ·
`01-landing-390x844.png` (banner dismissed) · `02-landing-1440x900.png` ·
`03-upload-resting-390.png` · `04-upload-hover-390.png` · `05-file-chosen-390.png` ·
`06-preview-rendering-390.png` · `07-preview-rendered-390.png` · `08-checkout-focus-390.png` ·
`09-recuperar-390x844.png` · `10-recuperar-invalid-email-390.png` ·
`11-recuperar-1440x900.png` · `12-gallery-notfound-390.png` · `12-gallery-working-390.png` ·
`13-gallery-delivered-390.png` · `14-gallery-refunded-390.png` ·
`15-gallery-refund-pending-390.png` · `16-gallery-delivered-1440x900.png` ·
`17-faq-open-390.png` · `18-mas-muestras-deferred-390.png` ·
`18-mas-muestras-placeholder-390.png` · `19-como-funciona-1440.png`
