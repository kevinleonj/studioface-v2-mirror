# Overnight goal for Claude Code (read fully before acting)

You are building StudioFace v2 unattended. Kevin is asleep. Nobody will answer questions.
Everything you need to decide is in CLAUDE.md, docs/DECISIONS.md, docs/DESIGN.md and this file.
When something is undecidable, pick the leanest option, write the reason in HANDOFF.md, continue.

## Hard boundaries (the classifier and hooks enforce these; do not fight them)
- Never run gcloud run deploy or terraform apply yourself, never write secrets. Push to main: CI applies infra/ and deploys. A red deploy triggers self-heal.yml.
- Never commit secrets. Never read .env or terraform.tfvars.
- No new dependency without a one-line reason in the commit message.
- `.venv\Scripts\python.exe scripts\ci.py` green before every commit. One commit per logical unit. `git add <named files>`.

## Phases. Each phase ends with a commit, a push to main, and a HANDOFF.md entry with evidence.

### Phase 0 — orientation (read-only)
cat -n CLAUDE.md, HANDOFF.md, app/*.py, tests/*.py, infra/*.tf, .github/workflows/*.yml.
Run `.venv\Scripts\python.exe scripts\ci.py`. Confirm 29 tests pass before you change anything.

### Phase 1 — backend runs for real
1. app/entry.py: complete FirestoreOrderStore.put/get (serialise the Order dataclass). Failing test first
   against the Firestore emulator (`gcloud emulators firestore start` is allowed; if unavailable, use a
   fake and say so).
2. preview_fn: upload validated bytes to BUCKET_SRC via the storage client, call fal nano-banana-2/edit at
   resolution 0.5K with build_prompt("corporativo", 0), return the fal URL. Use the researcher agent to
   confirm the fal Python client call shape first.
3. Gallery endpoint returns short-lived signed URLs (15 minutes) for gs:// keys, never public objects.
4. HEIC conversion with pillow-heif + EXIF transpose + 1536px long side, before any fal call. Test with
   a synthetic HEIC header only if a real fixture is unavailable; say which.
5. /internal/generate runs the four fal calls concurrently (asyncio.gather or a thread pool).
6. Push. Watch `gh run watch` for deploy.yml. If the Cloud Run revision is unhealthy, read
   `gcloud logging read` and fix. Do not stop on a red deploy.

### Phase 2 — frontend (Next.js static export, Tailwind, shadcn/ui) in ./frontend, served by the API image
Read docs/DESIGN.md first. Pages: / (landing with upload + Turnstile + preview + Checkout button),
/g/ (gallery; reads ?o=<order>&t=<token>, polls every 3 s), /recuperar (email -> resend link), /legal/* (aviso legal,
privacidad, términos, cookies). Spanish copy, prices with IVA included, one sentence stating images are
AI-generated. Consent Mode v2 Advanced with url_passthrough and ads_data_redaction, all four signals.
Definition of done per page: Playwright screenshots at 390x844 and 1440x900 in docs/screens/, Lighthouse
mobile performance >= 90 (npx lighthouse against the built static export), no console errors.

### Phase 3 — tracking backstop
GA4 Measurement Protocol purchase event from the pipeline's track_conversion, transaction_id = order id,
only on status delivered. Test with a fake HTTP client.

### Phase 4 — morning report
Write MORNING-REPORT.md: what was built, every piece of runtime evidence, the production URL,
what is NOT done, the three decisions you made alone and why, and the exact commands Kevin runs to
(1) make one €0.50 live test purchase, (2) run scripts/verify_ratelimit.py, (3) see the Cloud Run logs.
Final commit, push, stop.
