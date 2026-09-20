# The end-to-end test purchase

One purchase exercises everything no unit test can reach: Turnstile, the real fal
account and its balance, Cloud Tasks delivery, Firestore under a real transaction,
signBlob, Resend, and GA4. It has never been run. This is the procedure.

Kevin does the browser half — a CAPTCHA and a card form are his by the standing
rules. Claude does the verification half from the logs. Nothing here spends real
money if step 0 says test mode.

## Step 0 — which mode is production in? (do this first, it changes everything)

Test mode and live mode are separate object spaces; the API key alone decides which
one a request lands in (docs/verified.md, 2026-09-17). Card 4242 only works in test
mode. So before anything else:

    gcloud secrets versions access latest --secret=stripe-secret-key \
      --project=studio-face-fresh-start \
      | cut -c1-8

That prints only the prefix, never the key. `sk_test_` means test mode and the rest
of this document applies as written. `sk_live_` means live mode: card 4242 will be
declined, and the only honest test is a real 19,99 € purchase you then refund — or
the reverse of docs/GO-LIVE.md. Say which one on the issue and stop.

Cross-check, still without printing the key:

    gcloud secrets versions access latest --secret=stripe-secret-key \
      --project=studio-face-fresh-start \
      | xargs -I{} curl -s -u {}: https://api.stripe.com/v1/balance \
      | python -c "import json,sys; print('livemode:', json.load(sys.stdin)['livemode'])"

`livemode: False` is test mode.

## Step 1 — Claude starts tailing (say go on the issue and I run this)

    gcloud beta run services logs tail studioface-api \
      --region europe-west1 --project studio-face-fresh-start

## Step 2 — Kevin buys

1. Open https://studioface.app in a normal browser window.
2. Upload one to four photos of yourself. Solve the Turnstile.
3. Wait for the preview. That single 0.5K fal call is the first proof fal has
   balance; if it fails, stop and check issue #1.
4. Choose a style. Press the checkout button.
5. On Stripe: card `4242 4242 4242 4242`, any future expiry, any 3-digit CVC, any
   name and postcode. Use an address you can actually read mail at — the delivery
   link goes there.
6. Let the redirect complete. Do not close the tab. Paste the URL you land on into
   the issue: it must be `https://studioface.app/g/?o=cs_test_...&t=...` with BOTH
   parameters. Before commit 933efd9 it had no `t=` and this page said "enlace no
   válido"; that is the single most important thing this run proves.

## Step 3 — Kevin replays the webhook (proves the idempotency gate)

In the Stripe dashboard, Developers -> Webhooks -> the studioface endpoint -> the
`checkout.session.completed` event just delivered -> Resend. Or:

    stripe events resend <event_id> --webhook-endpoint=<endpoint_id>

Both work on a recent event (dashboard 15 days, CLI 30). Report the event id.

## Step 4 — what Claude verifies, and the exact evidence for each

| Claim | Where it shows up |
|---|---|
| One webhook accepted | `{"queued": "cs_test_..."}` and one `order stored order_id=... status=paid` |
| The replay was ignored | the second delivery answers `{"duplicate": true}`, 200, and there is NO second `order stored ... status=paid` |
| Four distinct prompts | four `image generation attempt` spans; confirmed against `build_prompt(style, 0..3)`, whose framing clause differs per variant |
| Four signed gallery URLs | `GET /api/orders/<id>/<token>` returns four `https://storage.googleapis.com/...X-Goog-Signature=...`, and this is the first live proof of signBlob |
| Resend outcome | `email sent subject=Tus fotos de StudioFace`, or the Resend exception if issue #2 is still open |
| GA4 | `Ga4Purchase` fires only on `delivered`; GA4_MEASUREMENT_ID is now G-NLP25TBTRJ on the revision, so this is also its first live firing |

Order status queries, run by Claude:

    gcloud logging read \
      'resource.type=cloud_run_revision AND resource.labels.service_name=studioface-api
       AND timestamp>="<start of the run>"' \
      --project studio-face-fresh-start --limit 200 --format 'value(textPayload)'

## Step 5 — after

Refund the test charge if it was live mode. Append the result to HANDOFF.md with the
pasted log lines, and close this document's issue.

## What this does NOT prove

The rate-limit counter behind Turnstile (one purchase is one request), concurrent
Firestore writes, and the 365-day bucket lifecycle. Those are covered elsewhere.
