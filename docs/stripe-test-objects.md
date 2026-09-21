# Stripe test objects — recorded before the live switch

Date: 2026-09-20

Read-only record, made before Kevin's live Stripe key takes over. The task these
objects were created for (task 07, live-switch) will point the app and the
Terraform config at the new live key and at new live Product/Price/webhook
resources. Nothing below is destroyed by that switch — these test-mode objects
are deliberately left orphaned in Stripe test mode and in this file, not deleted,
so the pre-switch state can always be found again.

## Secret version: test key

Secret: `stripe-secret-key` (Google Secret Manager, project
`studio-face-fresh-start`). No secret value was printed, read or logged —
versions listed by metadata only (`gcloud secrets versions list`).

| version | state   | created (UTC)        | note |
|---------|---------|-----------------------|------|
| 5       | enabled | 2026-09-20T20:16:39  | newest — the LIVE key Kevin just added |
| 4       | enabled | 2026-09-17T09:43:49  | **previous version — the test key** |
| 3       | enabled | 2026-09-17T09:17:42  | older test-key version |
| 2       | enabled | 2026-09-17T09:07:37  | older test-key version |
| 1       | enabled | 2026-09-17T08:53:28  | older test-key version |

**Test key version number: 4** (the version immediately before version 5, the
newest/live one).

## Terraform-managed Stripe test objects

Read from `terraform state show` (read-only; no `apply`, `destroy` or
`state rm` run) against `infra/` state as of this date. These are the
test-mode Product, Prices and webhook endpoint that the live switch will
replace with new live-mode resources.

| Terraform resource               | Stripe id                        |
|-----------------------------------|-----------------------------------|
| `stripe_product.headshots`        | `prod_VH922Za1UbxOnd`             |
| `stripe_price.eur`                | `price_1UGal6A8vwX0ydGBbli2NJQx`  |
| `stripe_price.usd`                | `price_1UGal7A8vwX0ydGBw5uU38ji`  |
| `stripe_webhook_endpoint.api`     | `we_1UGakiA8vwX0ydGB2LMs6vVN`     |

No secret values (key material, webhook signing secret) appear in this file —
only Stripe object ids, a secret version number, and metadata timestamps.
