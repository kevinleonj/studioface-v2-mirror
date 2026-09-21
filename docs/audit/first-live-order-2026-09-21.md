# First real order — read-only log check, 21 Sep 2026

Task: find a real (`cs_live_`) order in the last 24 hours of Cloud Run logs, confirm it
was fulfilled exactly once (charged once, photos generated once), and record whether a
refund had settled at the time of this check. Read-only throughout: log reads only, no
order was written to, no purchase or refund was made by this task.

## Command run (read-only, no cost)

    gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="studioface-api"' \
      --project studio-face-fresh-start --freshness 1d \
      --format "value(timestamp,jsonPayload.message)" --order asc

Full run: 105,599 lines, covering roughly 2026-09-20T11:26Z to 2026-09-21T11:26Z. A
second, narrower read-only check re-ran the same query filtered to this one order id,
with `--freshness 6h`, to look specifically for a later refund line (covering
2026-09-21T07:30Z to ~2026-09-21T13:28Z, i.e. past the end of the first query's window).

## A real order exists

One `cs_live_` order was found: `cs_live_a1VF` (the app logs only the first twelve
characters of an order id on purpose, so that a log line alone cannot open the
customer's gallery link; this report follows the same rule and never prints the rest).
No other `cs_live_` paid order appears anywhere in the 24-hour window — the only other
`cs_live_` mentions are two earlier probe requests with made-up ids
(`cs_live_REDACTED`, `cs_live_fake`) that Stripe correctly answered 404
and the app correctly refused with `gracias: refused ... payment_status=None`; neither
of those created an order.

## The five lines, each checked for how many times it appears for this order

1. `order stored order_id=cs_live_a1VF status=paid outputs=0` — **appears once**, at
   09:02:30. This is the payment notice (the webhook) creating the order record.
2. `enqueued order_id=cs_live_a1VF queue=generate` — **appears once**, at 09:02:31.
   Generation was handed to Cloud Tasks.
3. `order stored order_id=cs_live_a1VF status=generating outputs=0` — **appears once**,
   at 09:02:31. The generator picked the order up and started.
4. `order stored order_id=cs_live_a1VF status=delivered outputs=4` — **appears once**,
   at 09:02:48. All four photos were generated and saved.
5. `ga4 purchase sent order_id=cs_live_a1VF value=19.99 status=204` — **appears once**,
   at 09:02:48. The sale was recorded in analytics.

(Between lines 3 and 4 there is also one `order stored order_id=cs_live_a1VF
status=generating outputs=4` line at 09:02:48 — a normal intermediate write as the four
images finish, not one of the five lines being checked, and it is not a duplicate of
any of the five.)

**The one thing this check exists to catch, plainly stated: did Kevin get charged once
but the app try to generate his photos twice?** No. The "order stored ... status=paid"
line appears exactly once and the "order stored ... status=delivered outputs=4" line
appears exactly once. The shop is designed to finish the order from whichever of two
signals — Stripe's payment notice, or the customer's browser returning — arrives first,
and ignore the second. That is exactly what happened here: nothing fired twice, so
Kevin was charged once and his photos were generated once.

## Refund line — not found in this check

    refund settled order_id=cs_live_a1VF refund_id=... status=succeeded order_status=refunded

This line was searched for twice: once in the full 24-hour dump, and once in a
narrower, order-specific query with a 6-hour freshness window that reaches from before
the purchase (07:30Z) up to roughly 13:28Z today — about four and a half hours after
the order was delivered (09:02Z). **It was not found in either.** This does not mean
anything went wrong with the purchase; it means that, as of this check, either Kevin
has not yet done the manual refund step in the Stripe dashboard, or he has and the
confirming webhook has not reached the app yet. This task is read-only and was told not
to wait for events, so it did not wait for the refund to appear — Kevin should confirm
the refund directly in the Stripe dashboard (https://dashboard.stripe.com/payments,
toggle set to Live) rather than relying on this log check for that part.

## RESULT

RESULT: clean — the one real order found (`cs_live_a1VF`) was charged exactly once and
its four photos were generated and delivered exactly once, with none of the five
required log lines appearing more than once; this is the fulfilment behaviour the
system is designed to guarantee, and it held. The refund line was not present in the
logs at the time of this check (checked up to ~4.5 hours after delivery) — that is a
separate, still-open step for Kevin to confirm in the Stripe dashboard, not a defect in
how the order itself was processed.
