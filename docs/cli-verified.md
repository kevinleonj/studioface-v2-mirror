# Verified CLI syntax (append-only: `<subcommand>` - `<url>` - `<YYYY-MM-DD>`)

The user-level guard_shell hook refuses an az/gcloud/wrangler subcommand that is not
listed here with a date inside the last 30 days. Verify against current vendor
documentation first, then append - never the other way round.

ASCII only in this file, deliberately. The hook reports its own message through a
cp1252 console; em dashes come back as replacement characters, so they are avoided
here rather than risking the ledger being unreadable to the thing that reads it.

gcloud secrets versions access - https://docs.cloud.google.com/sdk/gcloud/reference/secrets/versions/access - 2026-09-17
  Synopsis: gcloud secrets versions access ([VERSION] : [--secret]=SECRET)
  [[--location]=LOCATION] [[--out-file]=OUT-FILE-PATH] [[GCLOUD_WIDE_FLAG] ...]
  VERSION is the numeric id or the alias "latest". Writes the payload to stdout as
  UTF-8 unless --out-file is given. Used here only to verify a vendor's state; the
  value is never printed.

gcloud secrets versions list - https://docs.cloud.google.com/sdk/gcloud/reference/secrets/versions/list - 2026-09-17
  Lists version name, state and createTime. No payload.

gcloud run services describe - https://docs.cloud.google.com/sdk/gcloud/reference/run/services/describe - 2026-09-17
  Read-only. Used to read the deployed revision's environment.

gcloud beta run services logs tail - https://docs.cloud.google.com/sdk/gcloud/reference/beta/run/services/logs/tail - 2026-09-17
  Streams Cloud Run logs. Needs the beta component.

gcloud logging read - https://docs.cloud.google.com/sdk/gcloud/reference/logging/read - 2026-09-17
  Read-only log query with --limit and --format.

## Never run in this project

gcloud secrets versions add / disable / destroy, gcloud run deploy, terraform apply,
stripe login. Secrets belong to Terraform or to bootstrap; deploying belongs to CI.
