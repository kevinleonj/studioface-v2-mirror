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
- Structured data (task 52, 22 Sep 2026): StudioFace can never earn a Google merchant
  listing — it sells generated images delivered by email, not a tangible product, and
  Google's free-listings policy excludes exactly that
  (support.google.com/merchants/answer/12077589, "Services: labor, time, effort,
  expertise, or actions, which do not result in ownership of a tangible product"). The
  Product markup stays anyway because it earns the ordinary product snippet with the
  price, which Google's product-snippet page allows. Of Search Console's two warnings:
  hasMerchantReturnPolicy is answered honestly — a MerchantReturnPolicy node nested
  under Organization on /legal/terminos/ (Google's own recommended nesting), with
  applicableCountry ES, returnPolicyCategory MerchantReturnNotPermitted (no returnable
  window invented — none exists), and merchantReturnLink pointing at the real
  #devoluciones anchor on that page; every Product's offers references it by "@id".
  shippingDetails is deliberately NOT added — there is no shipping, and a zero-cost
  zero-day shipping block would be a false statement about a service.
