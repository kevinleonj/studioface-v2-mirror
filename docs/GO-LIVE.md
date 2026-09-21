# Go-live: test mode to live mode

Task 07 (live-switch, 20 Sep 2026) ran this. What follows is the procedure as it was
executed and as it stands for any future repeat of it (rollback, or a second switch of
this kind) — not a plan waiting on prerequisites, the way this file used to read.

Prerequisites closed before this ran: Stripe account activated for live payments,
issue #3 (legal details incl. the NIF for Bizum) closed, docs/TEST-PURCHASE.md green,
the dead March webhook removed from the live Stripe account by hand. Kevin put the
live secret key in both places it needs to be — the GitHub Actions secret
`STRIPE_API_KEY` and the newest version of the Secret Manager secret
`stripe-secret-key` — before this task started.

## The one fact that shapes everything below

Stripe test mode and live mode are **completely separate object spaces**. The API key
alone decides which one you are in; objects created in one are inaccessible from the
other. A test-mode price id cannot be used with a live key. `infra/stripe.tf` managed
one product, two prices and one webhook endpoint that existed only in test mode; live
mode had none of them.

That is why this was never a matter of just swapping `STRIPE_API_KEY`. Terraform state
holds object ids, not just config. Point the same state at a live key without changing
anything else and the next refresh asks live mode for objects that only ever existed
in test mode — Stripe returns "no such price" and every deploy's apply fails.

## Shape of the change: one state, made to forget four things

There is one Terraform state for this project (`gs://studio-face-fresh-start-tfstate`,
prefix `studioface`) and this procedure keeps it that way. An earlier version of this
document proposed a second state under `prefix=studioface-live`, built by hand with
`-target`, with the live price and webhook ids copied out into GitHub Actions
variables and secrets by hand afterwards. That plan is withdrawn. It duplicated the
GCP half of the graph in spirit if not in resources, needed a person to carry three
values across by hand on every future change, and left two independent states that
could each apply cleanly while disagreeing about which webhook secret is current —
exactly the kind of drift CLAUDE.md's "one Terraform state" line exists to prevent.

The graph already ties these three things together in the *same* state:

- `infra/stripe.tf` — `stripe_product.headshots`, `stripe_price.eur`,
  `stripe_price.usd`, `stripe_webhook_endpoint.api`.
- `infra/gcp.tf`'s `google_secret_manager_secret_version.stripe_webhook`, whose
  `secret_data` is `stripe_webhook_endpoint.api.secret` — Terraform's sole writer of
  `stripe-webhook-secret`, on every apply.
- `infra/gcp.tf`'s Cloud Run container env `STRIPE_PRICE_EUR`, whose value is
  `stripe_price.eur.id`.

So the switch is: make Terraform **forget** it is tracking the four Stripe resources,
without touching the real objects, and let the next ordinary `apply` — the one
deploy.yml already runs on every push to main — ask the (now live) key for those four
resources, get nothing back, and create them fresh. The same apply then writes
whatever `.secret` the new live `stripe_webhook_endpoint.api` carries as the newest
`stripe-webhook-secret` version, and hands the new live `stripe_price.eur.id` to Cloud
Run as `STRIPE_PRICE_EUR` — all three, one state, one apply, no manual copying.

`terraform state rm` is HashiCorp's documented way to do the forgetting:
<https://developer.hashicorp.com/terraform/language/state/remove> — "This command
removes one or more resources from the Terraform state, causing Terraform to lose
track of that resource ... it does not physically delete the associated remote
object." The orphaned test-mode ids it leaves behind are recorded, not lost:
docs/stripe-test-objects.md.

## Procedure

1. **`terraform state rm` on exactly four addresses**, nothing else:

       terraform -chdir=infra state rm \
         stripe_product.headshots stripe_price.eur stripe_price.usd \
         stripe_webhook_endpoint.api

   Read the output. It must say `Removed` four times, once per address above, and
   nothing about any other resource. Before running it, confirm the backend's own
   backup exists — the `studio-face-fresh-start-tfstate` bucket has object versioning
   on, so the state object generation immediately before the `rm` stays retrievable
   as a noncurrent version of `studioface/default.tfstate` even after the `rm` writes
   a new one; note the pre-`rm` generation number before running it.

2. **Push one commit** that only touches documentation (this file). That push is what
   triggers deploy.yml's normal `ci -> infra -> deploy` run — no separate step
   creates the live objects; the `infra` job's ordinary `terraform apply`, running
   with `STRIPE_API_KEY` already set to the live key, does it as part of the deploy
   this commit causes.

3. **Read that run's apply log.** It must show exactly four Stripe resources added
   (`stripe_product.headshots`, `stripe_price.eur`, `stripe_price.usd`,
   `stripe_webhook_endpoint.api`) and `google_secret_manager_secret_version.stripe_webhook`
   replaced (new secret version, because `stripe_webhook_endpoint.api.secret` changed
   under it). Any destroy of a resource that is not one of those four Stripe resources
   means something else drifted — stop, revert the commit, do not let the deploy
   finish being treated as good.

4. **Verify from outside**, all read-only / refusal paths, none of which can create an
   order or spend anything:
   - `/health` reports `stripe_mode: "live"` (it already does, independent of this
     task) and `.venv\Scripts\python.exe scripts\check.py stripe_live` exits 0.
   - An unsigned `POST` to the payment webhook address still answers 400 — Stripe
     signature verification rejects it before anything is created.
   - A made-up session id on the thank-you/status address still answers 404 — nothing
     is created, nothing is looked up successfully.

## Bizum

Unchanged by the state design above; still a Dashboard toggle, not code, and still
gated on Stripe verifying the account's Bizum capability. See
docs/verified.md / the Stripe research already done for the specifics
(`individual.id_number` = NIE `Z3714124-C`, `business_type`, EUR-only, 0.50–5,000 EUR
band, one-time payment mode only, asynchronous refunds via `refund.updated` /
`refund.failed`, which `infra/stripe.tf`'s `enabled_events` already includes and
`app/main.py` already handles). Toggle it at
dashboard.stripe.com/settings/payment_methods once Stripe marks the capability
active, and verify in a private window from a Spanish IP afterwards.

## Rollback (documented, not run as part of this task)

Reversible, and none of it destroys anything:

1. **`terraform state rm` the same four addresses again** — forget the live objects
   the same way the switch forgot the test ones. They stay real in Stripe live mode,
   just untracked, the same way the test objects in docs/stripe-test-objects.md stay
   real in test mode.
2. **Put a test key back in both places**: a *new* version of the Secret Manager
   secret `stripe-secret-key` (never delete or disable the versions in between —
   they are the record of what ran when) and `gh secret set STRIPE_API_KEY` back to a
   kept test key.
3. **Push.** The next ordinary apply asks the now-test key for the four Stripe
   resources, gets nothing (state forgot them in step 1), and creates a fresh
   test-mode product, two prices and webhook endpoint — the same mechanism as the
   forward switch, run in reverse. `google_secret_manager_secret_version.stripe_webhook`
   picks up the new test endpoint's secret, and Cloud Run's `STRIPE_PRICE_EUR`
   becomes the new test price id, in the same deploy.
4. **In-flight money.** Anything paid live before a rollback is real money and this
   procedure does not touch it. Refund those orders from the Dashboard by hand, and
   stop new ones immediately with the kill switch (`config/killswitch` ->
   `{"on": true}` in Firestore, or the budget push to `POST /internal/budget`) —
   `/api/checkout` and `/api/preview` both answer 503 while it is on.
5. If Bizum was switched on and money is still settling, archive rather than destroy:
   `active = false` on the live `stripe_price`, `disabled = true` on the live
   `stripe_webhook_endpoint`, applied through the same state before removing tracking
   of them — stops new purchases and new deliveries without deleting the record of
   what already happened.

## The ordered command list

Every step, in order, with its rollback. `scripts/go_live.py --dry-run` reads this
table (not its own copy of it) to print the preflight, which is why the shape stays
`| # | Step | Command / action | Rollback |` even though the design above is prose.

| # | Step | Command / action | Rollback |
|---|---|---|---|
| 0 | Activate the Stripe account for live payments; close issue #3 (legal, incl. the NIF); run docs/TEST-PURCHASE.md green | dashboard.stripe.com/account/onboarding | n/a |
| 0b | Bizum capability: business tax ID (NIF Z3714124-C) or DNI/NIE, plus `business_type` | Stripe dashboard | n/a |
| 1 | Live key into Secret Manager | pipe the key into `gcloud secrets versions add stripe-secret-key --data-file=- --project studio-face-fresh-start` | add the kept test key back as a newer version |
| 2 | Live key as the CI secret | `gh secret set STRIPE_API_KEY` | `gh secret set STRIPE_API_KEY` with the test key |
| 3 | Forget the four tracked Stripe resources in the one state | `terraform -chdir=infra state rm stripe_product.headshots stripe_price.eur stripe_price.usd stripe_webhook_endpoint.api` | run the same `state rm` again once a test key is back in place |
| 4 | Read the `state rm` output | must say `Removed` four times and name only those four addresses | n/a, read-only |
| 5 | Push the commit that documents the switch | `git push origin main` | `git revert` that commit, push |
| 6 | Read the triggered deploy's `infra` job apply log | must show exactly 4 Stripe resources added and `google_secret_manager_secret_version.stripe_webhook` replaced; any destroy elsewhere is a stop | if anything else appears: stop, revert the commit, report |
| 7 | Verify `/health` and the mode check | `.venv\Scripts\python.exe scripts\check.py stripe_live` | n/a, read-only |
| 8 | Verify the webhook address still refuses | unsigned `POST` to the payment webhook address, expect 400 | n/a, read-only |
| 9 | Verify a made-up session still 404s | `curl` a bogus session id at the thank-you/status address | n/a, read-only |
| 11 | Bizum on | dashboard.stripe.com/settings/payment_methods | toggle off; sessions already open still complete |
| 11b | Before 11: `refund.updated` / `refund.failed` declared and handled | already true — `infra/stripe.tf` `enabled_events`, `app/main.py` | n/a |
| 12 | One real purchase at the live price, then refund it | browser + card | refund from the dashboard |

In-flight money is the one thing no step above undoes. Anything paid live before a
rollback is real: refund those orders by hand, and stop new ones with the kill switch
(`config/killswitch` -> `{"on": true}` in Firestore), which closes `/api/checkout` and
`/api/preview` with 503.

## What this procedure deliberately does not do

- It does not delete or disable the test-mode objects. They stay real, orphaned in
  Stripe test mode, and recorded in docs/stripe-test-objects.md — which keeps
  docs/TEST-PURCHASE.md repeatable after go-live.
- It does not touch any resource that is not one of the four Stripe resources named
  above. A destroy anywhere else during the triggering apply is a stop condition, not
  something this procedure absorbs.
- It does not automate itself past the one push in step 2. A go-live that runs
  unattended past that point is a go-live nobody read the apply log for.
