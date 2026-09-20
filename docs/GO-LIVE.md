# Go-live: test mode to live mode

**Nothing in this document has been executed.** It is the plan, written while the
service is still in test mode, so that the switch is a procedure rather than an
improvisation. Every vendor fact in it is cited in docs/verified.md with today's date.

Do not start until issues #1 (fal balance), #2 (Resend domain) and #3 (legal details)
are closed and docs/TEST-PURCHASE.md has been run green. Selling with `[PENDIENTE]`
on the aviso legal is not a go-live.

## The one fact that shapes everything below

Stripe test mode and live mode are **completely separate object spaces**. The API key
alone decides which one you are in; objects created in one are inaccessible from the
other. A test-mode price id cannot be used with a live key. The product, the two
prices and the webhook endpoint that `infra/stripe.tf` manages today exist only in
test mode, and live mode has none of them.

That is why this is **not** a matter of swapping `STRIPE_API_KEY`. Terraform state
holds test-mode object ids. Point the same state at a live key and the next refresh
asks live mode for objects that do not exist there. Stripe documents the object
separation; nobody documents what that does to Terraform state, so this procedure
does not find out on production.

## Shape of the change: a second state, not a mutated one

Live mode gets its **own Terraform state prefix**, so the test-mode objects keep
existing and keep working, and live-mode objects are created from zero:
`-backend-config="prefix=studioface-live"` on `terraform init -reconfigure`, against
the same `studio-face-fresh-start-tfstate` bucket.

The GCP half of infra/ (Cloud Run, buckets, Firestore, secrets, Cloudflare) must NOT
be duplicated — there is one production service. So the live run is scoped to the
Stripe resources only, with `-target`, and the GCP half stays on the `studioface`
prefix. That is the ugly part of this design and it is deliberate: the alternative,
one state whose meaning depends on an environment variable, is worse.

If this repo ever grows a staging environment, replace the whole arrangement with two
workspaces and a `stripe_mode` variable. Not before; there is one environment today.

## Procedure

### 0. Prerequisites that are not code

- Stripe account activated for live payments: dashboard.stripe.com/account/onboarding
  (business, product and relationship information; KYC).
- For Bizum specifically, a business tax ID (`company.tax_id` / `vat_id`) or, for a
  Spanish sole trader, DNI/NIE as `individual.id_number`, plus `business_type`. The
  Bizum capability stays `pending` until Stripe verifies it. This is the same NIF that
  issue #3 needs for the legal pages.

### 1. The live key into Secret Manager

Cloud Run reads `latest` of `stripe-secret-key`, so adding a version is the switch.
Pipe the key into `gcloud secrets versions add stripe-secret-key --data-file=-`
against project `studio-face-fresh-start`. Never as a command-line argument: it would
land in shell history.

Do not disable the old test version yet — it is the rollback. The new version does
not take effect until the next Cloud Run revision starts, so this step alone changes
nothing that customers can see.

### 2. The live key as a CI secret

The Terraform Stripe provider reads `STRIPE_API_KEY`, and deploy.yml passes it from
the Actions secret of the same name. Replace it with `gh secret set STRIPE_API_KEY`.

**Keep the test key somewhere first.** Step 2 of the rollback needs it, and once this
is overwritten GitHub will not give it back.

### 3. Create the live objects

Locally, with the live key exported and the live state prefix initialised, plan the
four Stripe resources and nothing else:

    -target=stripe_product.headshots
    -target=stripe_price.eur
    -target=stripe_price.usd
    -target=stripe_webhook_endpoint.api

Read the plan before applying it. It must say **4 to add, 0 to change, 0 to destroy**.
Anything else — above all any destroy — means the state prefix is wrong and the next
step would delete the test-mode objects. Stop there.

### 4. Carry the outputs across

Three values move from the live state into the places the running service reads:

| output | destination |
|---|---|
| `stripe_price_eur` | `gh variable set NEXT_PUBLIC_STRIPE_PRICE_EUR`, and `infra/` for Cloud Run |
| `stripe_price_usd` | `gh variable set NEXT_PUBLIC_STRIPE_PRICE_USD` |
| `stripe_webhook_secret` | a new version of the `stripe-webhook-secret` secret |

The webhook signing secret is per endpoint and therefore per mode: the live endpoint
has its own `whsec_`. Until it is in place, `app/core.verify_stripe_signature` rejects
every live event with 400 and no order is ever created — the failure is total and
silent from the customer's side, because Stripe retries into a wall.

**Do this first, in its own commit.** An earlier version of this document said
`stripe-webhook-secret` has two writers, Terraform and bootstrap. That was wrong, and
the truth is worse. Terraform is its **sole** writer and always has been — bootstrap
writes only `USER_SECRETS` plus `app-token-secret` and `tasks-token`, pinned by
tests/test_secret_ownership.py. The problem is not who writes it but *which mode's
value they write, and how often*:

    google_secret_manager_secret_version.stripe_webhook
        secret_data = stripe_webhook_endpoint.api.secret

and deploy.yml runs `terraform apply` on **every push to main**. So the secret always
holds whatever webhook endpoint the applied state owns. Today that is right, because
the test state is the only state. After go-live it is a trap that arms itself: put the
live `whsec_` in place, and the next ordinary deploy — any deploy, a README typo —
writes the TEST secret back as the newest version. Cloud Run reads `latest`,
`verify_stripe_signature` rejects every live event with 400, no order is created, and
Stripe retries into a wall. **Nothing logs an error**, because from the service's side
no webhook ever arrived. The first symptom is a customer who paid and got nothing.

So before step 4, remove `google_secret_manager_secret_version.stripe_webhook` and its
`depends_on` entry from infra/gcp.tf, in its own commit, and let the live state be the
only thing that ever writes that secret. `test_the_version_resource_tracks_the_endpoint
_in_the_applied_state` asserts this hazard still exists, so it will fail the day the
resource goes — which is the reminder to delete this paragraph with it.

### 5. Deploy

`STRIPE_PRICE_EUR` reaches Cloud Run through `infra/gcp.tf`, so the live price id has
to be in the Terraform that the GCP state applies. Update it, push, let GitOps deploy,
watch with `gh run watch`.

### 6. Bizum

Stripe's documented guidance is the Dashboard toggle plus dynamic payment methods, and
explicitly: *"Don't pass `payment_method_types` when creating Checkout Sessions."*
`app/entry.py:_checkout_factory` does not pass it, so **no code change is needed**.
Bizum is a toggle at dashboard.stripe.com/settings/payment_methods, set per mode.

Checked against our configuration:

- EUR only. Our only price is EUR. Fine.
- Minimum 0,50 EUR, maximum 5.000 EUR. Our price is 19,99 EUR. Fine.
- One-time payments only, no manual capture, not supported in subscription or setup
  mode. We take one payment in `mode: payment`. Fine.
- Refunds are **asynchronous**, up to about five minutes, with the final result on
  `refund.updated` / `refund.failed`.

That last one was a real gap. Half of it is now closed in code: `_stripe_refund`
returns Stripe's refund id and status, and the pipeline records them and writes
`failed_refund_pending` rather than `failed_refunded` unless the provider said
"succeeded", logging at ERROR when it said "failed". The gallery says "requested, your
bank is still processing it" instead of claiming the money is back.

**What is still open, and is a manual check until it is closed.** Nothing reconciles a
refund that settles *after* we stop looking. Asked to choose between an
`/internal/refund-status` endpoint and a documented manual check, I did neither yet and
took the documented check, for one reason: an endpoint has no caller. Cloud Tasks would
have to be taught to poll it, and the correct caller already exists — Stripe's own
`refund.updated` / `refund.failed` webhook, which the endpoint would duplicate. Adding
it now is an abstraction for zero callers, which the clutter rules forbid.

So, **before enabling Bizum**, do one of these, in this order of preference:

1. Add `refund.updated` and `refund.failed` to `enabled_events` on the
   `stripe_webhook_endpoint` and handle them in `_handle_event`, updating
   `refund_status` on the order. This is the real fix and it is small.
2. Until then: after any order reaches `failed_refund_pending`, check it by hand.
   Find them with

       gcloud logging read 'textPayload:"refund requested"' --limit 50

   and confirm each refund id in the Stripe dashboard. An ERROR line reading
   `refund FAILED order_id=... refund_id=...` means a customer paid and was not paid
   back; that one is not a log to triage later.

With card-only checkout this is close to theoretical — card refunds return
"succeeded" synchronously. It becomes real the moment Bizum is switched on, which is
why it sits in this section and not in a backlog.

Verify after the toggle by opening Checkout in a private window from a Spanish IP and
confirming Bizum appears.

### 7. Prove it

One real purchase at the live price, refunded from the Dashboard afterwards. The same
six claims as docs/TEST-PURCHASE.md, from the same log lines. Card 4242 does not work
here: live mode processes real cards only.


## Bizum: what it needs that we do not have (verified 18 Sep 2026)

Checked against Stripe's own Bizum page rather than assumed. The good news first: **there
is no blocker in the product.**

| requirement | us | status |
|---|---|---|
| business location | Spain | **ES is a supported location** |
| presentment currency | EUR | **EUR is the only one Bizum supports** |
| Checkout | one-time payment mode | **supported** — Bizum is *not* supported in Checkout subscription or setup mode, and we use neither |
| recurring payments | not used | Bizum does not support them anyway |
| charge size | 19,99 € | inside the 0.50 – 5,000.00 EUR band |
| prohibited categories | AI headshots | **not on the list** |
| `refund.updated` / `refund.failed` | subscribed and handled | done, 212e0bb |

**What is missing is account configuration, and only Kevin can do it.** Stripe, verbatim:

> **Individuals and sole proprietors**: Provide a valid personal identification number
> using the `individual.id_number` field. **Spain**: Provide your DNI or NIE if you are a
> foreign resident.

and

> You must also set the `business_type` on your account.

Our trader NIF is **Z3714124-C**, which is a NIE, so this is the individual/sole-trader
path: `individual.id_number` = the NIE, plus `business_type`. Both live in
[tax settings](https://dashboard.stripe.com/settings/taxation).

Then, and this is the part that cannot be scheduled:

> The Bizum payments capability stays in a `pending` state until compliance with Bizum
> onboarding requirements is verified.

**So step 11 cannot be given a date.** Request the capability, supply the identification,
and wait for Stripe. Everything else in this document can proceed without it — Bizum is
additive to card, not a prerequisite for going live.

Two facts worth having before enabling it: the dispute window is **120 calendar days**
from the transaction, against a card's shorter one, and the refund period is **395 days**.
Both are longer than our seven-day source-photo retention, so a dispute can arrive after
the evidence has been deleted. That is an argument for keeping the delivery record, not
for keeping the photographs.

## Rollback

Reversible at every step, in this order. Nothing below deletes anything.

1. **Application, fastest path.** Add the kept test key back as a *new* version of
   `stripe-secret-key` — Cloud Run reads `latest`, so rolling back is another add, not
   a delete. Same for `stripe-webhook-secret` with the test endpoint's `whsec_`. Then
   re-run the latest deploy so a new revision picks both up.
2. **CI.** `gh secret set STRIPE_API_KEY` back to the test key, and the two
   `NEXT_PUBLIC_STRIPE_PRICE_*` variables back to the test price ids.
3. **Stripe objects.** Do not destroy them. Archive: `active = false` on the live
   `stripe_price` stops new purchases, `disabled = true` on the live
   `stripe_webhook_endpoint` stops deliveries. Both are arguments on the provider's
   resources, so this is an edit to infra/ applied against the live prefix.
4. **Bizum.** Toggle off in the Dashboard. New sessions only; sessions already open
   can still complete.
5. **In-flight money.** Anything paid live before the rollback is real money. Refund
   those orders from the Dashboard by hand. New ones are stopped by the kill switch
   (`config/killswitch` -> `{"on": true}` in Firestore, or the budget push to
   `POST /internal/budget`); `/api/checkout` answers 503 while it is on, and so does
   `/api/preview`.

## The ordered command list

Every step, in order, with its rollback. Nothing here has been executed.

| # | Step | Command / action | Rollback |
|---|---|---|---|
| 0 | Activate the Stripe account for live payments | dashboard.stripe.com/account/onboarding | n/a |
| 0b | Bizum capability: business tax ID (limeralda, NIF Z3714124-C) or DNI/NIE, plus `business_type` | Stripe dashboard | n/a |
| 1 | Live key into Secret Manager | pipe the key into `gcloud secrets versions add stripe-secret-key --data-file=- --project studio-face-fresh-start` | add the kept test key back as a newer version |
| 2 | Live key as the CI secret | `gh secret set STRIPE_API_KEY` | `gh secret set STRIPE_API_KEY` with the test key |
| 3 | Remove the test state's claim on the webhook secret | delete `google_secret_manager_secret_version.stripe_webhook` and its `depends_on` from infra/gcp.tf, commit, push | revert the commit |
| 4 | Init the live state | `terraform -chdir=infra init -reconfigure -backend-config="bucket=studio-face-fresh-start-tfstate" -backend-config="prefix=studioface-live"` | `init -reconfigure` back to `prefix=studioface` |
| 5 | Plan the four Stripe resources ONLY | `terraform -chdir=infra plan -target=stripe_product.headshots -target=stripe_price.eur -target=stripe_price.usd -target=stripe_webhook_endpoint.api` | n/a, read-only |
| 6 | **Read the plan.** It must say `4 to add, 0 to change, 0 to destroy` | if it says anything else, STOP — the prefix is wrong and the next step deletes the test-mode objects | n/a |
| 7 | Apply those four | same `-target` list with `apply` | `active = false` on the price, `disabled = true` on the endpoint — never destroy |
| 8 | Live webhook secret into Secret Manager | `terraform -chdir=infra output -raw stripe_webhook_secret` piped into `gcloud secrets versions add stripe-webhook-secret --data-file=-` | add the test `whsec_` back as a newer version |
| 9 | Live price ids into the CI variables | `gh variable set NEXT_PUBLIC_STRIPE_PRICE_EUR` and `..._USD` | set the test price ids back |
| 10 | Live price id into infra so Cloud Run gets it | edit `infra/`, commit, push, `gh run watch` | revert and push |
| 11 | Bizum on | dashboard.stripe.com/settings/payment_methods, per mode | toggle off; open sessions still complete |
| 11b | **Before 11**: add `refund.updated` and `refund.failed` to `enabled_events` | infra/stripe.tf, apply against the live prefix | remove them |
| 12 | One real purchase at the live price, then refund it | browser + card | refund from the dashboard |

In-flight money is the one thing no step above undoes. Anything paid live before a
rollback is real: refund those orders by hand, and stop new ones with the kill switch
(`config/killswitch` -> `{"on": true}` in Firestore), which closes `/api/checkout` and
`/api/preview` with 503.

## What this procedure deliberately does not do

- It does not delete or disable the test-mode objects. Test mode stays usable, which
  is what keeps docs/TEST-PURCHASE.md repeatable after go-live.
- It does not automate itself. A go-live that runs unattended is a go-live nobody read
  the plan for.
