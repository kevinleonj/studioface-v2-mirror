# Run me first — Windows PowerShell, C:\Users\KEVIN\dev\studioface-v2

Pack version: PACK-VERSION.txt (bootstrap prints it on line 3). Integrity: MANIFEST.sha256 lists every file's hash;
verify after unzip with the command in step 0. Nothing from the failed run exists in any cloud: it stopped at
"billing accounts list", before any create.

## Step 0 — keep your answers, replace the folder, verify the pack
Your Terraform state (55 resources) lives in gs://studio-face-fresh-start-tfstate, not in the folder. Secrets
live in Windows Credential Manager. Only the six plain answers live in the folder: copy them out first.

    Copy-Item C:\Users\KEVIN\dev\studioface-v2\.bootstrap-answers.json C:\Users\KEVIN\dev\answers-backup.json

    Set-Location C:\Users\KEVIN\dev
    Remove-Item -Recurse -Force C:\Users\KEVIN\dev\studioface-v2
    Test-Path C:\Users\KEVIN\Downloads\studioface-v2-overnight.zip
    Expand-Archive -Force C:\Users\KEVIN\Downloads\studioface-v2-overnight.zip C:\Users\KEVIN\dev
    Set-Location C:\Users\KEVIN\dev\studioface-v2
    Copy-Item C:\Users\KEVIN\dev\answers-backup.json C:\Users\KEVIN\dev\studioface-v2\.bootstrap-answers.json
    Get-Content PACK-VERSION.txt
    python scripts\verify_pack.py

Expected: version `2026-09-17-e` and `MANIFEST OK: <n> files`.

## Step 1 — dry run

    python bootstrap.py --dry-run

Expected line 2: `interpreter: ...\.venv\Scripts\python.exe`, then `Tools OK.`, then the plan, no traceback.

## Step 2 — what it asks, in order (each remembered; Enter keeps the shown value)

| # | Prompt | Answer |
|---|---|---|
| 1 | GCP project id to CREATE | studio-face-fresh-start |
| 2 | Google account | a numbered list of the accounts gcloud already knows; pick **OWNER_EMAIL_REDACTED** by number; 0 = log in another. Nothing is typed. |
| 3 | Domain | Enter (studioface.app) |
| 4 | GitHub owner | kevinleonj |
| 5 | Cloudflare account id | 0755f56b4e85398ba3c258abfa2a4c61 |
| 6 | Cloudflare zone id | 0855ea83395b6f45d4e93d9bb45b34f4 |
| 7 | GA4 Measurement ID | G-NLP25TBTRJ (public; this is what you pasted into the wrong prompt before) |
| 8 | Cloudflare API token (hidden) | stored in Windows Credential Manager after the first entry |
| 9 | fal.ai API key (hidden) | same |
| 10 | Resend API key (hidden, starts with re_) | same |
| 11 | Stripe SECRET key (hidden, sk_test_) | same |
| 12 | GA4 Measurement Protocol API SECRET (hidden) | the value under "Measurement Protocol API secrets" in the GA4 stream page, or Enter to skip; a G- value is rejected |

Secrets are verified against the vendor (Cloudflare, Stripe, Resend) BEFORE anything is created; a rejected one
is forgotten and you are asked again on rerun. `--reset-inputs` forgets everything.

Logins, each only if missing on this box, all as the account from prompt 2:
gcloud (browser), gh (device code), stripe (pairing code), firebase-tools (browser).
There is NO "application-default" login any more: Terraform gets a one-hour gcloud token.

## Step 3 — real run

    python bootstrap.py

Ends by starting the build (scripts\overnight.py). Leave the PC on and plugged in.

## What happened on the terraform run (55 of 60 created; 5 errors, all root-caused)
| Error | Cause | Fix in pack -e |
|---|---|---|
| Cloudflare 81053 "record with that host already exists" | api.studioface.app already exists from v1 | bootstrap finds it via the API and `terraform import`s it; Terraform then updates it in place |
| google_firebase_project 403 | a firebase.tf that was NOT part of the reviewed pack (sandbox tampering, now removed) | deleted; Firebase is added by firebase-tools in step 6 as designed |
| WorkloadIdentityPool 403 "denied (or it may not exist)" | iam.googleapis.com was not in the enabled-API list; pool had no depends_on | API added; pool depends on service enablement |
| Cloud Run "code 7" | secrets had containers but no versions when the service was created, and IAM had just been granted | two-phase apply: phase A creates secrets/Stripe/Turnstile, bootstrap adds the versions, phase B creates Cloud Run |
| Billing budget 403 "requires a quota project" | gcloud user tokens belong to a Google-owned project | provider: user_project_override = true, billing_project = <project> (provider reference) |

## What happened on the earlier run (so it does not repeat)
- gcloud's active account on this box was kevin@limeralda.com. Its Google Workspace has Google Cloud
  disabled by the Workspace admin ("Account Restricted"), so `billing accounts list` was refused.
- The script did not ask which account to use; it accepted "some account is active". Fixed: prompt 2.
- The application-default login went to a DIFFERENT account (gmail) than the gcloud account (limeralda),
  which would have made Terraform and gcloud disagree. Fixed: no ADC; one token from the chosen account.
- G-NLP25TBTRJ was typed into the api_secret prompt. Fixed: separate prompts with format checks.
- Every rerun re-asked everything. Fixed: answers file + OS credential store.

## GA4 API secret
analytics.google.com → Admin → Data streams → studioface.app → "Measurement Protocol API secrets" → Create →
copy the Secret value (prompt 12). The Measurement ID G-NLP25TBTRJ is prompt 7.

## Later, once, by hand
Firebase Hosting custom domain (TXT into Cloudflare); Stripe → Payment methods → Bizum; Cloudflare api record →
Proxied after the Cloud Run certificate exists.

## Checking on the build
    .venv\Scripts\python.exe scripts\morning.py
