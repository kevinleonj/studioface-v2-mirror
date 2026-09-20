# Morning report — 18 September 2026

Eleven commits, each with a failing test first, the local gate green before it, and
`gh run watch` green after it. No red deploy, no self-heal triggered.

**Read this part first.**

---

## Nobody could buy, and I found it by accident

I set out to automate the 4242 test purchase (issue #4). It never got past the first
step, and the reason was not the automation.

**The Turnstile widget never rendered in production.** Measured against
`studioface.app` with an uninstrumented browser, six time points:

    t=    0ms  window.turnstile=undefined  widget children=0  token fields=0
    t=  500ms  window.turnstile=object     widget children=0  token fields=0
    t=10000ms  window.turnstile=object     widget children=0  token fields=0

The container was an empty `<div>`. `input[name="cf-turnstile-response"]` never existed.
So the token was always `""`, `/api/preview` answered **403**, and every visitor who
pressed "Ver una prueba gratis" was told *"No hemos podido verificar que no eres un
robot. Recarga la página."* — which was untrue, was not their fault, and did not improve
on reload, because the race is deterministic rather than intermittent.

No preview means no checkout. **Nobody could buy.**

The cause was four words in `upload-form.tsx`:

    if (!TURNSTILE_SITEKEY || !widget.current || !window.turnstile) return;

inside `useEffect(..., [])`. Next loads the Turnstile script `afterInteractive`, so it
has not run when React fires mount effects. The effect gave up once and never ran again.

**My first fix was also wrong**, and only measuring caught it. I used
`turnstile.ready()`, the first pattern in Cloudflare's own documentation. Their runtime
refuses it:

    TurnstileError: Remove async/defer from the Turnstile api.js script tag
    before using turnstile.ready().

Identical symptom, different cause. Reading the docs and shipping would have replaced one
silent outage with another.

**Verified on production after deploy:** widget children 0 → 1, token field 0 → 1, and
the widget reads *"Verifique que es un ser humano"*, correctly in Spanish.

---

## The design verdict

The critic scored from pixels it captured itself, twice.

    round 5   41/50   FAIL   (line 7, tap targets, 1/5 — blocker)
    round 6   49/50   PASS   no line below 4

It failed round 5 on four controls measuring **32px** on the live DOM — the "Descargar"
button on `/g/`, the recovery CTA, the `/recuperar/` submit, and the email field. Every
one on the money path. Same bug class as the 36px CTA that `tests/test_tap_targets.py`
exists to prevent; it came back through two doors that file did not know existed, and
that file now reads every `.tsx` and both call shapes.

It also caught a claim in my own comment that was false: the deferred gallery placeholder
said "the same 4:5 frame ... so nothing jumps" and was `aspect-[2/1]`. Measured 171px
against 279.875px — a **63.7% jump**, on a page I had just certified CLS 0, because
Lighthouse never scrolls far enough to fire the observer. Now **0.0%**, fixed by making
the placeholder *be* the figure with the real caption rendered invisible, so the height
is computed from the same string and cannot drift.

## What else shipped

| | before | after |
|---|---|---|
| hero "después", visible on a phone | 85px of 212 | **340px of 340** |
| landing transfer, first load | 465.9 KB | **324.1 KB** |
| dead canvas on `/g/` while generating | 383px | **48px** |
| Lighthouse mobile (perf / a11y / BP / SEO) | — | **98 / 100 / 100 / 100** |
| funnel events in the product | 1 (server-side `purchase`) | **9** |
| fake progress bars | 2 | **0** |

- **The fold is 691px, not 844px.** The consent banner is fixed to the bottom and up on
  every first visit. Every "above the fold" measurement before this run was against a
  page nobody was looking at.
- **The hero A/B was decided from screenshots**, and they contradicted the argument: the
  inset shape gives the result 4.01× the area, and on a phone it was *worse* than the
  even pair until the photograph moved above the price. A bigger picture starting at
  y=606 in a 691px slot shows more of the top of a head.
- **Two fake progress bars deleted**, `value={45}` on the gallery and `value={60}` on the
  upload form. Both literals, both on screens where money is in flight.
- **`docs/CONVERSION.md`**: 7 falsifiable hypotheses, 8 events, all 8 verified firing in
  a real browser — which caught two things no unit test would have.
- **Five named motion moments**, and a sixth nobody had named: shadcn's `transition-all`
  on every button, animating every property, outside the reduced-motion guard.
- **`scripts/go_live.py --dry-run`**: a preflight that checks everything and, by test,
  cannot apply infrastructure, deploy, set a secret, or push.

## What I got wrong, and how I knew

- The `turnstile.ready()` fix. Caught by measuring, not by reading.
- `aspect-[2/1]` for the placeholder, with a comment asserting the opposite. Caught by
  the critic.
- **Four times in one day**, a test read its own rationale or carried a regex whose `\b`
  had become a literal backspace byte — patterns that match nothing and pass against
  every offender. Seven real offenders in one file, four in another. Every affected test
  now strips comments first, and two carry a test asserting the pattern can fail.
- I wrote "not verified" about `fetchpriority` after reading the wrong row of the right
  source. Lighthouse pointed at it, I checked browser-compat-data properly, and it went
  in — performance 96 → 98, blocking time 140ms → 60ms.
- The Turnstile widget looked English on a Spanish page. Measuring said its default
  already follows the browser: a Spanish browser gets Spanish. **No change made.**

## needs Kevin

1. **#4 — run the test purchase.** I could not. The one action that creates a real order
   and spends real fal credit was refused by this session's guard, which is the right
   line. Everything around it is ready; the exact commands are on the issue. Start with:

       gcloud secrets versions access latest --secret=stripe-secret-key \
         --project=studio-face-fresh-start | cut -c1-8

2. **#10 — `infra/stripe.tf` is missing `refund.updated` and `refund.failed`** (GO-LIVE
   step 11b). Two lines, but applying them is sequenced inside the go-live procedure.

3. Also open and unchanged: **#6** (your own before/after pairs), **#7** (Resend region),
   **#9** (Docker not installed, so the gate cannot mirror the image build).

Run `.venv\Scripts\python.exe scripts\go_live.py --dry-run` for the current verdict. It
says **BLOCKED**, on exactly those two things.

## Not done

- `docs/design-references.md` — studying three reference pages was never started.
- Rebuilding `frontend/public/muestras/` from a real order, which depends on #4.
- Rubric line 2 stays at 4/5: "19,99 €" carries three visual treatments on one mobile
  viewport. Recorded rather than papered over.
