# Settled decisions (do not re-open in code or prompts)
- Model: fal-ai/nano-banana-2/edit, 1K, JPEG, 4:5. Bake-off may change it later via one env var.
- No accounts. HMAC gallery links. Images kept 365 days, selfies 7 days (bucket lifecycle rules).
- Generation via Cloud Tasks -> /internal/generate. Never FastAPI BackgroundTasks on Cloud Run.
- Counters are Firestore transactions, never process memory.
- Payments: Stripe Checkout hosted, Bizum on. Prices are Terraform-managed (infra/stripe.tf).
- Email: Resend. Frontend: Next.js static export, built into the API image and served by FastAPI at "/" (one Cloud Run service, apex + api. mapped to it). No Firebase, no separate hosting product. API: Cloud Run europe-west1.
- Deploy: CI on push to main (deploy.yml). No human tag. No manual deploy command anywhere.
- Consent Mode v2 Advanced, url_passthrough + ads_data_redaction. PostHog cookieless optional.
- Price: 19,99 € (EUR price id from Terraform output), $9.99 for Ecuador variant.
