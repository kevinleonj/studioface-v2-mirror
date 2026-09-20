# Conversion — hypotheses, events, and the number that would prove each one wrong

Written 18 Sep 2026. This file exists because of one rule in `.claude/skills/studioface-ui`:
**never argue about conversion, instrument it.** Everything below was previously a design
opinion with nothing behind it — the product carried consent mode and a single
server-side `purchase`, so literally nothing between arriving and paying was measured.

An uninstrumented hypothesis is an argument with a number stapled to it. Each row names
the event, the ratio, and the reading that would falsify it. If a row cannot be
falsified it does not belong here.

## The events

Declared once in `frontend/src/lib/track.ts`. `tests/test_conversion_events.py` holds
both ends of the contract: no call site may fire a name that is not declared, and no
declared name may go unfired. The second is the expensive failure — a name nobody sends
shows in GA4 as a flat line, and a flat line reads as "this never happens" rather than
"this was never measured".

| event | fires when | where |
|---|---|---|
| `view_proof` | the hero before/after is ≥50% visible, once per visit | `comparador.tsx` |
| `cta_click` | the first-screen or sticky button is pressed; carries `location` (`fold` \| `sticky`) | `fold-cta.tsx` |
| `faq_identity_open` | "¿Me voy a parecer a mí?" is opened | `faq.tsx` |
| `upload_start` | at least one file is chosen | `upload-form.tsx` |
| `preview_started` | the free preview is requested | `upload-form.tsx` |
| `preview_ready` | the preview IMAGE fires its load event, so a face is really on screen | `upload-form.tsx` |
| `preview_failed` | a preview attempt put no face on the screen; carries `reason` (the server's `detail`, `image_blocked`, or `network`) | `upload-form.tsx` |
| `begin_checkout` | checkout is asked for, the last click before Stripe. Renamed from `checkout_click` 2026-09-20 — GA4's own name for the step, carrying `value` (19.99) and `currency` (EUR) | `upload-form.tsx` |
| `recuperar_view` | somebody lands on `/recuperar/` | `recuperar/page.tsx` |
| `order_delivered` | the gallery reports four delivered images | `g/page.tsx` |

Naming rules verified 18 Sep 2026 (`docs/verified.md`): names are case sensitive, must
start with a letter, allow only letters, numbers and underscores, cap at 40 characters,
and carry at most 25 parameters. None may reuse an automatically collected name, which
is why the step after preview is `begin_checkout` and not `click`.

`purchase` stays where it is — server-side, through the Measurement Protocol, from the
Stripe webhook. A client-side purchase event would be fired by the browser of someone
who has just been redirected back from Stripe, which is the one moment they are most
likely to close the tab.

## The hypotheses

| # | hypothesis | ratio to watch | falsified if |
|---|---|---|---|
| H1 | Proof before price. A real before/after inside the first viewport is what makes the page credible, so it must be seen before anything is asked. | `view_proof` / sessions | under 70% of sessions fire `view_proof`, which would mean the photograph is still below the visible slot for most visitors |
| H2 | "¿Me voy a parecer a mí?" is the objection that stops the sale, and the subheading plus the FAQ answer should settle it. | `faq_identity_open` / `view_proof` | over 25% open the identity question — the short answer is not landing and the reassurance belongs higher up |
| H9 | Most failed previews are the visitor's photograph, not our service, and the product can say which. Before I1 was fixed every failure - a content-policy refusal, a spent Turnstile token, an image the browser refused to load - arrived as one sentence and as no event at all. | `preview_failed` grouped by `reason` / `preview_started` | over 20% of attempts fail, or any single `reason` is over half of them |
| H3 | Reassurance next to the upload control (no account, no card, deleted in 7 days, pay only after the free preview) is what converts interest into a file being chosen. | `upload_start` / `view_proof` | under 8% of people who see the proof choose a file |
| H4 | Trader identity on every page, not only inside `/legal`, is the cheapest trust signal a stranger can read. | `upload_start` / `view_proof`, before and after | no movement of 1 percentage point or more after the identity block shipped |
| H5 | The free preview is the sale. Somebody who has seen their own face come back should convert far better than somebody deciding from a stranger's photograph. | `begin_checkout` / `preview_ready` | under 20%, which would mean the preview is showing people something they do not want |
| H6 | "Recuperar mis fotos" in the header and the footer of every page is how a lost buyer gets back in without writing to support. | `recuperar_view` / `order_delivered` | over 15% of delivered orders end up on the recovery page — the delivery email is not arriving or not being found |
| H8 | A visitor who meets a working product button inside the first screen tries the free preview far more often than one who has to scroll 1.3 screens to find a disabled one. Of 24 sites in the category, StudioFace was the only one with no primary call to action inside the first 844px (F3, 19 Sep). | `cta_click` with `location=fold` / `view_proof` | under 10% of people who see the proof press the button, which would mean the button is not the thing that was missing |
| H7 | The wait is designed rather than decorated: stating the time, showing the four frames and saying the email arrives anyway should keep people from abandoning a paid order. | `order_delivered` / `purchase` | under 90%, meaning one paid customer in ten never sees the gallery at all |

## What was measured to get here, not argued

Every number in this section came from a served copy of the real export, measured with
`getBoundingClientRect` at 390×844 and 1440×900, with the consent banner up — because it
is up on every first visit.

**The usable slot on a phone is 691px, not 844.** The consent banner takes 153px. That
single correction is what made H1 falsifiable rather than decorative:

| | "después" rendered | visible inside the 691px slot |
|---|---|---|
| before | 170 × 212 | 85px of 212 (40%) |
| after | 340 × 340 | 340px of 340 (100%) |

The `view_proof` threshold is 0.5 for this reason. At the old layout a visitor could have
"seen" the proof by the definition of a naive observer while looking at 85 pixels of
somebody's forehead.

**H7's screen was the worst one.** `/g/` while generating — the page a customer looks at
for two minutes straight after paying 19,99 € — held a heading, one sentence, a progress
bar frozen at 45%, and 383px of nothing. The bar was `value={45}`, a literal; a second
one, `value={60}`, sat on the upload form. Both are gone (`tests/test_the_wait.py`).

## Verified in a browser, not in a build

The build passing proves the module compiles, not that a visitor's actions reach `gtag`.
Measured 18 Sep 2026 on a served copy of the export at 390×844, with `dataLayer.push`
hooked so that every event is recorded at the moment it is pushed:

    load (390x844)                 -> view_proof
    scroll the pair into view      -> (nothing: already counted, fires once)
    scroll past it a second time   -> (nothing)
    open the identity question     -> faq_identity_open
    close it again                 -> (nothing)
    choose a file                  -> upload_start {"files":1}
    ask for the free preview       -> preview_started {"files":1}, preview_ready
    click buy                      -> begin_checkout {"value":19.99,"currency":"EUR","wardrobe":"por_defecto"}
    /recuperar/ load               -> recuperar_view
    /g/ four images delivered      -> order_delivered {"images":4}

All eight, each exactly once. Two things this caught that no test would have:

- **`view_proof` fires at load on a phone**, without any scrolling. That is the point of
  the hero rework and not a bug — the proof is now inside the 691px slot — but before the
  reorder it would have fired for a visitor looking at 85 pixels of a forehead. The 0.5
  threshold is what makes the event mean what its name says.
- **Reading the events after the fact could not see `begin_checkout` at all.** It fires
  immediately before `window.location.href = <stripe url>`, and the navigation destroys
  the page context. In production `gtag` sends with `sendBeacon`, which is designed to
  survive unload, and the event is fired before the `/api/checkout` round trip rather
  than after it, which buys a few hundred milliseconds. That is a mitigation, not a
  guarantee: if `begin_checkout` ever reads materially below `preview_ready` minus known
  drop-off, suspect the beacon before the funnel.

## Tying the sale to the visit and the ad click (20 Sep 2026)

Before this, the server-side `purchase` carried a `client_id` this server invented from
a hash of the order id, and a `transaction_id` that was the order id itself — so a sale
could be counted, but not joined to the visit that produced it, or to whichever ad click
paid for that visit.

**Read once, kept in memory only.** `gclid`, `gbraid` and `wbraid` — Google Ads splits
the click id across the three depending on the click's path (Search/Display,
app-to-web, web-to-app) — are read from the URL in `frontend/src/lib/track.ts` the
moment that module first runs, into a plain module variable. Nothing is written to
`localStorage`, `sessionStorage` or a cookie: "no storage before consent" here means
there is no storage of these at all, only a variable that lives as long as the tab does.

**Read again at checkout.** GA4's own visitor and visit numbers — `client_id` and
`session_id` — are asked for with `gtag('get', 'G-NLP25TBTRJ', 'client_id' / 'session_id',
callback)` right before the `/api/checkout` call. Measured against production for this
task: both come back populated even with cookies refused, and unchanged after consent is
granted, because Advanced Consent Mode (`consent.tsx`, untouched by this task) sends
cookieless pings from first paint rather than waiting for a choice — so the two numbers
already exist before the visitor answers the banner.

**Stored on the order, all five.** `POST /api/checkout` carries `gclid`, `gbraid`,
`wbraid`, `ga_client_id` and `ga_session_id`; Stripe metadata carries them through the
redirect to the webhook, which is the only place `Order` gets built (`app/main.py:
_order_from_session`). `tests/test_checkout.py` pins the passthrough end to end.

**The purchase event now prefers the real visit.** `Ga4Purchase` (`app/adapters/ga4.py`)
uses `order.ga_client_id` as the MP `client_id` when the browser reported one, falling
back to the old derived id only when it did not — so the purchase lands on the SAME
GA4 visitor as `begin_checkout` did, instead of a synthetic one invented after the fact.
`order.ga_session_id`, when present, is sent as the `session_id` event param (MP-2:
that field is per-event, not top-level). Neither `gclid`, `gbraid` nor `wbraid` is sent
to GA4 by this task — they are stored for a possible future Google Ads offline-import
job (docs/verified.md, Gh) and are out of scope here.

**The transaction id is no longer the gallery order id.** `order.id` is the Stripe
Checkout Session id, and it already sits in the `/g/?o=` link this app emails to the
customer — reusing it as GA4's `transaction_id` would tie an id the customer (and
anyone they forward that email to) can see to this service's ad-attribution accounting.
`Ga4Purchase` now sends Stripe's PaymentIntent id instead, falling back to a stable,
non-reversible derivation of the order id only for the `no_payment_required` case a
100%-off coupon produces, where Stripe never issues a PaymentIntent.

**No `consent` object is sent.** Researched for this task (docs/verified.md, MP-6
through MP-6d): Google documents omitting `consent` on a Measurement Protocol event as
the normal, default path — it falls back to "the consent settings from corresponding
online interactions for the client... instance" — and no page anywhere recommends
building one for a server-sent event. That fallback resolves correctly here precisely
because `client_id` now prefers the real browser id.

**Validated against Google's debug endpoint.** The exact payload `Ga4Purchase` builds
for an order carrying a PaymentIntent and both GA4 numbers was POSTed, unmodified, to
`/debug/mp/collect` and returned `{"validationMessages": []}` (docs/verified.md, MP-8).
One caveat found doing this (MP-7): the debug endpoint does not enforce a named event's
"Required" fields — a `purchase` with `transaction_id` deleted also validated clean — so
a green debug response proves the payload is well-formed, not that every field GA4's
own docs call required is present. `tests/test_ga4.py` is what actually pins that.

**`begin_checkout`.** Renamed from `checkout_click` in the same change, because it is
one of GA4's own documented event names (`docs/verified.md`, Gg) with a defined
`value`/`currency`/`items` shape, rather than a name this product invented.

## Deliberately not instrumented

- **Scroll depth.** It correlates with everything and explains nothing, and it would be
  the number people reach for instead of the seven above.
- **Anything about the visitor.** No demographics, no interests, no user id. The product
  has no account, asks for a garment rather than a gender, and collecting an identity
  attribute in order to sell a photograph is the thing `app/guards.py` refuses to do.
- **A client-side `purchase`.** See above.
- **`gclid`/`gbraid`/`wbraid` inside the GA4 purchase event itself.** Stored on the
  order for a possible future ads-import job, not sent to GA4 by this task.

## How to read any of this

Nothing here is reportable until the events have been live for long enough to have a
denominator. The first honest read is after 100 sessions that fired `view_proof`; before
that, every ratio in the table is noise with a decimal point.
