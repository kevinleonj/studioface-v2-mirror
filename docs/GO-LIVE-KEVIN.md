# For Kevin, morning of 21 Sep — two things from last night, then the real purchase

Read this before you do anything. Two things happened overnight that you don't know
about yet. Neither is an emergency. Then there's the one real purchase to run today.

## Thing 1: an old, unused webhook may email you a scary-looking failure notice

Last night's automatic deploy accidentally created a full extra set of live Stripe
objects (a product, two prices, a webhook) a few minutes before the real ones got
created properly. Nobody spent money and nothing broke — but that first, throwaway
webhook is probably still sitting there in your Stripe account, switched on, pointing
at our site, except the password it was given to sign its messages with no longer
exists anywhere. So if it's still enabled, every time a real customer pays, Stripe will
try to tell that old webhook about it, fail, retry a few times, then send **you** an
email that looks like "your webhook endpoint is failing" or "delivery attempts
exhausted".

**This does not affect customers.** Our app already ignores messages from an endpoint
whose signature it doesn't recognise (it answers "400" and moves on), and separately,
the app already finishes the order the moment your customer's browser lands back on
the thank-you page — it doesn't wait for that webhook. So nobody's photos or refunds
are at risk. It's just a noisy, wrong email you'd otherwise wonder about.

I could not check from here, without your live key, whether that old webhook is still
switched on. Here's exactly where to look:

1. Go to <https://dashboard.stripe.com/webhooks> (make sure the toggle top-right says
   **Live**, not Test).
2. You should see two endpoints pointing at `https://api.studioface.app/api/stripe/webhook`.
   One of their ids ends in `...DV4oNARv` — **that one is real, leave it alone.**
3. The other one (a different id, does NOT end in `DV4oNARv`) is the leftover. Click
   into it, then either **Disable** it or, if Stripe offers it, **Delete** it. Either
   is safe — this endpoint has never successfully delivered anything since its secret
   was destroyed hours after it was created.

If you get a "webhook failing" email from Stripe before you've done this: ignore it,
it's this.

## Thing 2: the old test-mode Stripe objects are meant to stay exactly as they are

Before switching to real payments, we recorded the old test-mode product/prices/webhook
in `docs/stripe-test-objects.md`. Those are deliberately left alone, unused, in Stripe's
TEST side of your account (never the real, live side — no money can move through them).
Don't delete them. They let us re-run a free test purchase later without touching real
money, in case anything ever needs debugging.

## Now: one real purchase, with your own card, then refund it

This is the first real money StudioFace will ever take. €19.99 will actually leave
your card, then you'll get it back. Takes about five minutes.

### What you'll do

1. Open <https://studioface.app> in a normal browser window (not incognito is fine).
2. Upload one to four photos of yourself, solve the little "I'm not a robot" box.
3. Wait for the preview to come back — this is the app's first real use of the image
   generator today, so it may take fifteen to thirty seconds.
4. Pick a style, press the purchase button.

### What you should see on the payment page — check this before you type your card

The address bar must start with:

    https://checkout.stripe.com/c/pay/cs_live_

**The `cs_live_` part matters.** If it ever says `cs_test_` instead, stop — that would
mean something reverted production to test mode, and your card would just be declined
rather than charged (harmless, but tell me immediately if you see it).

5. Pay with your own real card. Real name, real address you can receive mail at — the
   receipt and photos both go to the email and address you enter here, not your Gmail.
6. Let the page redirect on its own. Don't close the tab or press back.

### What you should see right after paying

You land on a page whose address looks like:

    https://studioface.app/g/?o=cs_live_REDACTED&t=YYYYYYYYYYYYYYYY

It shows your own uploaded photo, dimmed, with a "generating..." message, then after
roughly 30–90 seconds it should replace itself with four finished photos you can view
and download. If it's still spinning after a few minutes, that's the one thing worth
telling me about right away.

You should also get an email shortly after, subject roughly "Tus fotos de StudioFace",
with your four photos attached/linked — that's the app's own delivery email, sent by
Resend, separate from anything Stripe sends you.

### How to refund it

1. Go to <https://dashboard.stripe.com/payments> (toggle says **Live**).
2. Find the payment — it'll be the newest one, €19.99, with the name/email you just
   entered.
3. Open it, click **Refund payment**, leave it as a full refund, confirm.
4. It says "Refunded" immediately in the dashboard. The money actually lands back on
   your card in 5–10 business days — that's your bank, not us.

### Which email confirms the refund

Stripe (not our app) sends its own automatic email to the billing email address you
typed at checkout, confirming the refund — separate from the app's photo-delivery
email above. If you don't see it within a few minutes, check
<https://dashboard.stripe.com/settings/emails> — that's where "email customers about
refunds" is switched on or off; if it's off, the dashboard's "Refunded" status is
still the real confirmation, an email is just a courtesy on top of it.

Bizum refunds (if you ever pay by Bizum instead of card) don't settle instantly —
that's what the `refund.updated` / `refund.failed` webhook events are for; today's
card purchase settles instantly and doesn't need that wait.

### The log lines I'll read afterwards, to confirm it all actually happened

I'll run this (read-only, no cost):

    gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="studioface-api"' --project studio-face-fresh-start --freshness 1h --format "value(timestamp,jsonPayload.message)"

And look for exactly these five lines, in this order, each appearing **once**:

1. `order stored order_id=cs_live_REDACTED status=paid outputs=0` — Stripe's
   payment notice (the webhook) arrived, and the app created the order record.
2. `enqueued order_id=cs_live_REDACTED queue=...` — generation was handed to
   Cloud Tasks.
3. `order stored order_id=cs_live_REDACTED status=generating outputs=0` — the
   generator picked the order up and started.
4. `order stored order_id=cs_live_REDACTED status=delivered outputs=4` — all four
   photos were generated and saved. This confirms generation ran to completion.
5. `ga4 purchase sent order_id=cs_live_REDACTED value=19.99 status=204` — the sale
   was recorded in analytics.

Only the first twelve characters of the order id are ever logged (that's on purpose,
so a log line alone can't be used to open your gallery link).

**The one thing I'm specifically checking for**: line 1 (`status=paid`, the order's
creation) must appear only **once**, and line 4 (`status=delivered`) must appear only
**once**. Stripe sends the
payment notice both as a webhook AND by redirecting your browser back, and the app is
built to fulfil from whichever one arrives first and ignore the second — seeing it fire
twice would mean you were charged once but the app tried to generate your photos twice,
which the design is supposed to prevent. After I check refunded and delivered-once, I'll
tell you either "clean" or exactly what I found instead.

Later refund confirmation, once it's had a few minutes to process:

    `refund settled order_id=cs_live_REDACTED refund_id=... status=succeeded order_status=refunded`
