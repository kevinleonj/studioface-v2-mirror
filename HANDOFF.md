# HANDOFF

## 2026-09-16 — sandbox build (Claude in claude.ai)
- Backend core, guards, HTTP layer: 29 tests green, ruff clean (complexity <= 8).
- Terraform for GCP + Stripe + GitHub + Cloudflare: `terraform validate` green against providers google 7.46.1, stripe 3.4.1, github 6.13.0, cloudflare 5.25.0.
- UNTESTED: app/entry.py (needs GCP), app/adapters/firestore_counter.py, app/adapters/turnstile.py, Dockerfile, workflows.
- Follow-ups: see GOAL.md phases 1-4.

## 2026-09-16 — final audit before handover (claude.ai)
Fixed: pyproject had no build-system (CI/Docker `pip install -e` unproven) -> setuptools backend + packages, proven in a clean venv; Makefile now touches .claude/state/ci_mirror_ok (user-level guard_bash blocks push without it); bootstrap trusts the repo root in ~/.claude.json (documented key) and checks `claude auth status`; overnight.sh adds --permission-prompts none; Cloudflare api record DNS-only until the Cloud Run certificate exists; Lighthouse is an alarm (continue-on-error) with lighthouserc.json; deploy.yml YAML fixed.
Still untested here: Dockerfile build (no Docker in sandbox), app/entry.py, adapters, workflows end to end, gh/stripe/firebase-tools flags.

## 2026-09-16 — cross-platform run (Mac Terminal or Windows Git Bash)
scripts/ci.py replaces `python scripts/ci.py` everywhere (Windows has no make); hooks use shell form (`bash "<script>"`) because Windows exec form needs a real .exe; python resolved as python3-or-python (Store stub on the HP box); preflight prints winget ids on Windows, brew on macOS; keep-awake: caffeinate on macOS, powercfg note on Windows.

## 2026-09-16 — single-language rebuild (Python everywhere)
All bash removed. bootstrap.py (with --dry-run, exercised), scripts/ci.py, overnight.py, morning.py, verify_ratelimit.py, set_secret.py; hooks are Python in exec form (`python <script>`), each exercised with real JSON: block=exit 2, allow=0, lint reformats and exits 0, stop gate exits 2 on red CI / dirty tree and 0 when green and clean. CI gate green on this code.

## 2026-09-17 — venv as the single interpreter
bootstrap.py creates .venv and re-execs inside it; hooks, TaskCompleted and permissions pinned to .venv\Scripts\python.exe; CI gate runs inside .venv. Verified: re-exec + CI green from the venv in the sandbox. On Kevin's box the earlier verification installed into global site-packages (pip warned about openai/pydantic-settings conflicts): harmless, optional `python -m pip uninstall -y studioface`.

## 2026-09-17 — real run crashed at 2/8 on Windows (WinError 2), root-caused and pinned
Cause: subprocess.run(["gcloud", ...]) — CreateProcess does not search PATHEXT, gcloud is gcloud.cmd. Fix: scripts/_exec.py resolve() (shutil.which) for every argv[0] in bootstrap and all scripts; os.execv removed (does not replace the process on Windows). Regression tests: tests/test_bootstrap.py (4). Also: PACK-VERSION.txt printed at start; Kevin's folder still contained files from an older zip (Expand-Archive overlays) → RUN-ME-FIRST step 0 deletes the folder first.

## 2026-09-17 — "stuck" after ADC login: root cause + redesign of bootstrap inputs
Cause: `npx -y firebase-tools login:list` captured (silent) while npx downloaded firebase-tools. Removed firebase-tools from bootstrap; Firebase project + Hosting site now Terraform (google-beta, validated). Reordered: logins before questions; answers persisted (bootstrap.config.json); secrets in OS credential store via keyring (Windows Credential Manager backend, Context7-verified); input validation (GA4 secret rejects a G- id; Kevin pasted the Measurement ID last run); ADC quota project set; long steps stream. 36 tests green.

## 2026-09-17 — run stopped at 3/8 "Account Restricted"; bootstrap.py rewritten from scratch (pack -c)
Root causes: (1) gcloud active account was the restricted Workspace account, script never asked which; (2) ADC login went to a different account than gcloud; (3) Measurement ID typed into the api_secret prompt; (4) every rerun re-asked all inputs. Fixes: explicit gcp_account prompt + `gcloud config set account`; Terraform auth via GOOGLE_OAUTH_ACCESS_TOKEN (provider + gcs backend, both verified); separate GA4 id/secret prompts with regexes; answers file + keyring; vendor validation of Cloudflare/Stripe/Resend keys before any create. Integrity: the sandbox copies of bootstrap.py and tests/test_bootstrap.py were modified by a process that was not this session; both were deleted and rewritten, and MANIFEST.sha256 + scripts/verify_pack.py now ship with the pack. 38 tests green; terraform validate green.

## 2026-09-17 — first real terraform apply: 55/60, five errors root-caused (pack -e)
Cloudflare 81053 -> import existing api record; firebase.tf (not authored in this session; sandbox tampering) removed with google-beta; iam.googleapis.com added + pool depends_on; Cloud Run code 7 -> two-phase apply with secret versions between; billingbudgets 403 -> user_project_override/billing_project. Stripe webhook secret and Turnstile secret are now Secret Manager versions written by Terraform (values already in state). 42 tests, terraform validate green.

## 2026-09-17 (overnight, Claude Code) — phase 1: the backend runs for real
Baseline was 50 tests, not the 29 GOAL.md phase 0 predicted (the pack grew since that line was
written). Now 132, all green, ruff clean.

Built: app/images.py (HEIC decode, EXIF transpose applied physically, 1536 px long side, JPEG out);
app/config.py (one schema, every missing variable named at once, secrets repr=False);
FirestoreOrderStore.put/get; concurrent generation (app/core.threaded_batch);
app/adapters/fal.py; app/adapters/gcs.py (V4 signed URLs + source uploads); app/preview.py.

Four defects found by writing the test first, each of which would have hit production:
1. FirestoreOrderStore could not be constructed at all. OrderStore.__init__ assigns
   `self.killswitch = False`, which lands on the subclass property setter and ran before
   `self.db` existed -> AttributeError on the first request of every cold start.
2. That same assignment WRITES {"on": false}. Every new Cloud Run instance would have switched
   off a kill switch the budget alert had just switched on — the one control that bounds the bill.
3. The pipeline sent one identical prompt four times (core.PROMPTS), so a customer's four
   "different" headshots were four runs of the same prompt. guards.build_prompt(style, variant)
   already existed, tested, with no caller. core.PROMPTS deleted.
4. The paid path handed fal gs:// URIs for a private bucket. fal fetches over HTTPS and could
   never have read the reference photos, so every paid order would have failed and refunded.

Decisions made alone (nobody to ask, per GOAL.md):
- Firestore emulator NOT used: it needs a Java 8+ JRE and the cloud-firestore-emulator component;
  this box has neither and the global rules say it is not a development machine, so installing a
  JRE overnight was out of scope. tests/fake_firestore.py deep-copies on read and write to mimic
  the wire (which is what catches aliasing). Transaction atomicity is therefore still unproven —
  FirestoreCounter remains the one untested adapter.
- Concurrency is a thread pool, not asyncio. fal_client.subscribe is blocking and
  /internal/generate is a sync FastAPI route, so it already runs in a worker thread; going async
  would have forced the ImageModel port and every test using it to become async for no gain.
  fal_client.subscribe_async is verified to exist if that ever changes.
- Retries stay wave-based inside the SAME order-level budget, so the existing assertions
  (attempts == 6 after two transient failures) hold unchanged against the concurrent code.

Evidence: 132 tests green; `.venv\Scripts\python.exe scripts\ci.py` green; and a live uvicorn on
127.0.0.1:8099 driven with curl — preview from a real 2400x1800 HEIC returned 200, no-turnstile 403,
text-file-as-jpeg 422, webhook queued, replay duplicate, bad signature 400, generate without the
Cloud Tasks token 403, generate delivered, gallery returned four signed storage URLs, wrong gallery
token 404, fourth preview from one client 429.

Open, needs a live check before the gallery is trusted: whether the Cloud Run runtime service
account needs roles/iam.serviceAccountTokenCreator bound ON ITSELF to call signBlob for itself.
Recorded in docs/verified.md; the researcher could not settle it from documentation.

## 2026-09-17 (overnight, Claude Code) — phases 2, 3, 4
Frontend (Next.js 16 static export, Tailwind 4, shadcn/ui) in frontend/: landing, /g/, /recuperar/,
four legal pages, Spanish es-ES, Consent Mode v2 Advanced (four signals, url_passthrough,
ads_data_redaction). GA4 Measurement Protocol purchase backstop in app/adapters/ga4.py.
Two endpoints that did not exist and without which those pages were decoration: POST /api/checkout
and POST /api/recuperar.

Evidence: 169 tests green; ci.py green; terraform validate green; Lighthouse mobile 96 (landing)
and 95 (gallery) against the built export served by the real app, LCP element is the H1; 14
Playwright screenshots at 390x844 and 1440x900 in docs/screens/; zero console errors on every page;
live curl runs for preview/webhook/generate/gallery/recuperar recorded in MORNING-REPORT.md.

One measured fix worth repeating: Lighthouse mobile was 80, with 2.1 s attributed to text
compression. Neither Cloud Run nor StaticFiles compresses anything, so the export's JS and CSS went
over the wire raw in production too. GZipMiddleware took it to 96.

Decisions made alone (full reasoning in MORNING-REPORT.md section 4): fake Firestore rather than
install a JRE for the emulator; thread pool rather than asyncio for the four fal calls; the browser
never names an object in the bucket - /api/preview returns a signed batch handle and the server
rebuilds the gs:// keys itself.

NOT DONE, and it is the first thing to fix: `git push` was denied by the permission system (no
approval surface in an unattended session), so all 11 commits are LOCAL. Nothing is deployed, there
is no new production URL, and no deploy run was watched. GOAL.md phase 1 step 6 is unfinished.
STRIPE_PRICE_EUR and GA4_MEASUREMENT_ID were added to infra/ and need an apply; until then
/api/checkout answers 503 checkout_not_configured by design and no money can be taken.
FirestoreCounter remains the one untested adapter (needs the emulator), and the signBlob
self-binding question in MORNING-REPORT.md section 5 is still open.

## 2026-09-17 (after the push) — deploy green, /healthz root-caused, 6.2/6.4/6.5 run
Deploy run 105229369056 green end to end; revision 00005 serves 100% of traffic.

The smoke failure was not ours. Google Front End answers the literal path /healthz itself on
every *.run.app host, before the request reaches the container. Measured on 00004 before
changing anything: /healthz -> 404, 1568 bytes, Google's own error page, no
x-cloud-trace-context; /healthzz and /nonexistent-page -> 404, 12165 bytes, our Next.js 404
(so the container answered); /openapi.json -> 200 and listed /healthz. Traffic was already
100% on 00004 and there is no traffic block in infra/gcp.tf, so it was never a rollout
problem. Locally, with the real export mounted, /healthz returned 200 — which is why every
test passed while production could not reach it. Renamed to /health (not aliased; nothing
else referenced it) and pinned: a test parses the smoke curls out of deploy.yml and asserts
the app serves each path and that none is one Google reserves. 176 tests green.

FirestoreCounter is no longer untested. /api/recuperar uses the same counter with no
Turnstile in front; from one IP production returned 200 x5 then 429 x2, exactly
RECOVER_PER_HOUR=5, so the Firestore transaction works across Cloud Run instances.
Atomicity under genuinely concurrent writes is still unproven (one client, sequential).

The signBlob question is answered: sa-studioface-api holds roles/iam.serviceAccountTokenCreator
at PROJECT level, which covers every service account in the project including itself, so no
self-binding is needed. Its own resource-level policy is empty, which is what made the
overnight check look alarming. Still unproven end to end — signing only happens for a
delivered order and none exists yet.

verify_ratelimit.py against api.studioface.app: 403 x5, the documented PASS. That proves the
Turnstile gate, not the counter behind it; a real token means solving a CAPTCHA, which the
standing rules forbid.

GA4 is deployed but INERT: GA4_MEASUREMENT_ID is on the revision with no value and no secret
reference, and ga4_measurement_id is unset in the variables file, so Ga4Purchase returns early
on every delivered order and no conversion is ever sent. The payload shape itself is good —
the exact adapter payload returned "validationMessages": [] from /debug/mp/collect, with a
negative control (event name "purchase!!") returning NAME_INVALID to prove the endpoint checks.

Open: set ga4_measurement_id and re-apply; make the 0,50 EUR live purchase (it also settles
signBlob end to end); rate-limit counter behind Turnstile; concurrent-write atomicity;
[PENDIENTE] legal details.

## 2026-09-17 (operator session, Claude Code) — items 1, 2, 3, 6 of Kevin's list

### The escalation channel was closed (4157f26)
Before anything else: `gh issue create` answered "the 'kevinleonj/studioface-v2'
repository has disabled issues". `github_repository` defaults `has_issues` to false
and infra/github.tf never set it, so every rule that escalates by opening an issue —
CLAUDE.md's, and the prompt inside self-heal.yml — has been dead since the repo was
created, failing silently. `has_issues = true`, pinned at both ends by
tests/test_escalation_channel.py. Deploy run 35240871044 green; `gh api
repos/kevinleonj/studioface-v2 --jq .has_issues` -> `true`.

### Item 2 — the post-payment path was broken for every customer (933efd9)
Found by auditing the path the test purchase would take, before running it. Two
defects, neither reachable by any existing test because nothing exercised the link
Stripe actually redirects to.

1. `success_url` was `{public_url}/g/?o={CHECKOUT_SESSION_ID}` — order id only. The
   gallery refuses to poll without `?t=` as well (g/page.tsx line 60), so paying
   landed the customer on "Este enlace no es válido o ha caducado." The working link
   existed only in the delivery email. Stripe substitutes only {CHECKOUT_SESSION_ID}
   and the token is an HMAC over APP_TOKEN_SECRET, so the redirect now lands on
   `GET /api/gracias`, which mints the token and 302s to the gallery. Confined to
   `cs_` ids so it is an oracle for the order namespace and no wider.
2. Even with a good token the gallery latched onto "notfound": the status endpoint
   404s on an unknown order, and Stripe redirects before the webhook lands. A good
   token on an unknown order is now `{"status": "pending"}`. Also swapped a `!=`
   token comparison for `hmac.compare_digest`.

`_checkout_factory` had no test at all. It has one now.

### Item 1 — the test purchase is a written procedure, not yet run (a3ff5a7)
docs/TEST-PURCHASE.md. Kevin owns the browser half; step 0 is a mode check, because
card 4242 only works in test mode, test and live are separate object spaces, and
nobody had checked which key production holds. I could not check it myself: the
Stripe CLI on this box answers "The API key provided has expired" and the rules
forbid `stripe login`. Issue #4 asks for it.

### Item 3 — the counter is proven, and so is the ceiling it enforces (878c079)
tests/test_counter_atomicity.py: 24 threads on a barrier at one document, exactly
`limit` get through, against the real emulator in a new CI job. Skips where
FIRESTORE_EMULATOR_HOST is unset. What it does not prove is in the module docstring:
Google documents the emulator as "simple locking", not production's concurrency
control.

tests/test_fal_bill_ceiling.py: no number of clients gets more than daily_global=300
previews out of fal per UTC day; a client refused by its own ceiling does not spend
global budget; the 301st innocent caller is refused with `daily_cap`. Writing it
caught a bug in my own flood helper — `10.{s}.{i}.7` varies the /24, not the host, so
"one subnet, 200 addresses" was really 200 subnets and the subnet ceiling had never
been exercised.

tests/test_ci_contract.py because a test that skips everywhere passes forever while
proving nothing. It also pins timeout-minutes on every job (three of four had none)
and a concurrency group on every workflow. `infra` now needs `[ci, emulator]`.

202 passed, 5 skipped locally; ci.py green.

### Item 6 — read and dry-run only; the write is blocked (issue #5)
All eight secrets had every version ENABLED; Cloud Run reads `latest` for all of
them, so 18 older versions are live credentials nothing uses. `gcloud secrets
versions disable` is refused here by the auto-mode classifier ("Secret-Store
Writes"), which is the same line CLAUDE.md draws. Issue #5 has the exact loop.

The dry run caught a trap worth keeping: `--filter="state=ENABLED AND name!=$latest"`
returns the latest version too, with a warning that `name!=` "currently does not
match". Driving the disable loop off that filter would have disabled the live
app-token-secret and fal-key. The command in the issue excludes the latest in the
shell, never in the gcloud filter.

### Open, and who owns it
- #1 fal balance (Kevin) — without it every order silently refunds
- #2 Resend domain verification (Kevin) — without it a paid order delivers no email
- #3 NIF, registered name, address for /legal (Kevin) — three files, exact lines
- #4 run the 4242 purchase, and say which Stripe mode production is in (Kevin)
- #5 disable 18 superseded secret versions (Kevin, one command)
- docs/GO-LIVE.md — item 5, in progress
- No dependency cache on any CI job.
- Pushing several commits quickly supersedes intermediate deploy runs: the `deploy`
  concurrency group keeps only one pending run, so 35241145498 was cancelled. The
  tip still deploys; per-commit deploys do not.

## 2026-09-17 (operator session) — items 4 and 5, and what CI taught us

### Item 4 — legal details (issue #3)
Three files, exact lines, in the issue: aviso-legal 14-15, privacidad 14-15, terminos
38. Nothing invented. `<Pending>` paints a visible `[PENDIENTE: ...]` on the live page,
which is the right failure mode and is still there.

### Item 5 — docs/GO-LIVE.md (92e332c). NOT executed.
Shaped by one verified fact: test and live are separate object spaces and the key
alone picks one, so this is not a key swap. Terraform state holds test-mode object
ids; pointed at a live key it asks live mode for objects that do not exist. The
procedure therefore uses a second state prefix (`studioface-live`) scoped with
`-target` to the four Stripe resources, and leaves the GCP half alone. Rollback is
five ordered steps, none of which deletes anything.

Two defects in today's code found while writing it, documented there, not fixed:
- `stripe-webhook-secret` has TWO writers. `google_secret_manager_secret_version
  .stripe_webhook` writes the TEST endpoint's secret on every apply of the test state.
  After go-live the next ordinary deploy would put the test secret back over the live
  one and every live order would die at signature verification, silently, with Stripe
  retrying into a wall. It must lose that writer before step 4.
- Bizum refunds are ASYNCHRONOUS and can fail minutes later via `refund.failed`.
  `_stripe_refund` treats `Refund.create` as done, which is true for a card. But
  `Pipeline.run` refunds automatically whenever generation fails, so this sits on an
  automatic path: a failed Bizum refund would be silent. `refund.failed` has to be on
  the webhook endpoint before Bizum is switched on.

Bizum itself needs no code. Stripe's documented guidance is a Dashboard toggle plus
dynamic payment methods and says explicitly not to pass `payment_method_types`, which
`_checkout_factory` already does not.

### The emulator job took three attempts. Both failures were mine, and both were worth it.
1. 35241448581: `ERROR: (gcloud.emulators.firestore.start) The java executable on your
   PATH is not a Java 21+ JRE`. The job exported JAVA_HOME_21_X64 — which is what the
   documentation talks about — and gcloud reads the `java` on PATH, not JAVA_HOME.
   Worse, tests/test_ci_contract.py asserted "JAVA_HOME_21" appears in the job, so the
   test agreed with the mistake instead of catching it. It now asserts the PATH export.
2. 35242208491: the emulator ran, and two cases failed with `ValueError: Failed to
   commit transaction in 5 attempts` — 24 threads exhausting the client's retries
   under the emulator's simple locking. The assertion was wrong, not the counter.
   "Exactly `limit` threads win" is a claim about scheduling fairness; what bounds the
   bill is that the document never grants more than `limit`. Rewritten as that, with
   exactness preserved by draining the document sequentially afterwards and asserting
   the total grants come to exactly `limit`.
3. 35242711314 green end to end: ci, emulator, infra, deploy all success.
   `6 passed in 22.45s` on the emulator job.

Carried forward from failure 2, and this one is about production, not CI: the same
retry exhaustion is possible on `g:{day}`, the global daily key that EVERY preview
writes. Firestore sustains roughly one write per second per document. At the 300/day
ceiling that is not close, but a burst can raise and /api/preview then answers 500. It
fails closed — no fal call — so the bill stays bounded, which is the right direction.
Written into the module docstring.

### self-heal fired three times against commits main had already passed (1243b8d)
35242095249, 35242376134 and 35242584866 all triggered while this session was pushing
fixes. Each checks out `main`, which already had the fix, and could have pushed over
the top of this work. I cancelled all three by hand, which is not a control. There is
now a guard: if the failed run's head_sha is not the tip of main, the heal stops. A
newer tip either carries the fix or fails on its own and triggers its own heal.

### Runtime evidence against production (a3ff5a7 deployed)
    GET https://api.studioface.app/api/gracias?session_id=cs_test_probe123
      -> 302, location https://studioface.app/g/?o=cs_test_probe123&t=e646d1c4...
    GET .../api/gracias?session_id=not-a-session   -> 404
    GET .../api/gracias                            -> 404
    GET .../api/orders/cs_test_probe123/e646d1c4...  -> 200 {"status":"pending","images":[]}
    GET .../api/orders/cs_test_probe123/deadbeef...  -> 404
Both post-payment defects are fixed on the live service.

## 2026-09-17 (operator session, part 2) — the gate, A, B, C, and the design finding

**Invariant (item C):** self-heal must never heal a commit that is not the current tip
of main — `head_sha != git rev-parse HEAD` stops the run — and its concurrency group is
`{ group: self-heal, cancel-in-progress: false }` (self-heal.yml:12), confirmed, so a
heal already running is never killed by a newer failure.

**The Stop hook was unsatisfiable (1fe110b).** check_done.py reads
.claude/state/last_test_run; scripts/ci.py only ever wrote ci_mirror_ok, a different
file for a different gate. last_test_run is stamped by guard_shell.py:124 for commands
that *look like* a test run, and `python scripts/ci.py` does not. Measured: 17:49:41
against a green run at 19:39:07. The gate now writes both.

**Item A — I was wrong, and the truth is worse (6bc3b76).** bootstrap never wrote
stripe-webhook-secret or turnstile-secret; Terraform has always been sole owner, so
there was nothing to take away. The hazard is that the secret's value follows whichever
webhook endpoint the *applied state* owns, and CI applies the test state on every push.
After go-live, any deploy — a README typo — writes the TEST secret back as `latest`,
every live event fails signature verification, and nothing logs an error because from
our side no webhook arrived. Pinned by tests/test_secret_ownership.py, one of which
fails the day the resource is removed, which is the reminder to delete the warning.

**Item B — and a double refund found while writing the test (b4a9099).** The pipeline
wrote "failed_refunded" on the strength of the request alone. It now records Stripe's
refund id and status and only claims refunded when the provider said "succeeded".
While testing it: the replay guard was `("delivered", "failed_refunded")`, so adding a
new terminal status without adding it to that tuple would make a retried Cloud Task
refund a SECOND time. Both are in DONE_STATUSES now, held by two tests that run the
pipeline twice. Reconciliation is a documented manual check, not a new endpoint,
because the correct caller is Stripe's refund.updated webhook and an endpoint would
have zero callers — reasoning in GO-LIVE.md.

**Item D — the design finding, before any change.** Against the real built frontend:

    P0  tasteful-default-2026 (cream+serif+sage)  _next/static/chunks/*.css
        var(--font-inter) inter ... fraunces ... var(--font-geist-mono)
    DESIGN AUDIT: 1 P0, 0 P1, 0 P2   FAIL

The page trips no crude tell — no purple, no gradient text, no cardocalypse, no emoji,
no averaged copy. It fails on exactly one thing: Inter + Fraunces + cream, the 2026
"tasteful default". The diagnosis in the brief was right and the script isolates it.

The audit is NOT yet wired into scripts/ci.py or deploy.yml, deliberately. Our page
fails it today, so wiring it now makes the gate red and blocks every commit including
the ones that fix the design. It lands with the redesign that makes it pass.

## 2026-09-17 (operator session, part 3) — the design loop, items D–H

**The floor (D).** scripts/design_audit.py placed, lint-fixed (E501 x5, one Yoda, and
audit_text split at complexity 9 > 8), and its test repaired: as delivered it looked
for the script as a sibling of itself and for fixture DIRECTORIES f_slop/f_ref, so it
could not pass in either location. Each fixture is now staged alone into a tmp dir,
because auditing the one fixtures directory judges slop.html and refined.html together.
A byte-identical duplicate at scripts/test_design_audit.py (outside testpaths, so never
collected, but linted) was deleted. Added a fourth case: an empty directory is an
error, not a pass — a step that passes silently on an unbuilt export would make a
broken build look like a clean design.

**The verdict on our page, before any change:** 1 P0, 0 P1, 0 P2. The page tripped NO
crude tell. It failed on exactly one: `tasteful-default-2026 (cream+serif+sage)` —
Inter + Fraunces + cream #FAFAF7 + blue #1D4ED8.

**The decision (E).** docs/DESIGN.md rewritten to lead with what it refuses. Three
directions built as standalone HTML, all three passing the floor 0/0/0 — necessary and
nowhere near sufficient, which is the whole reason the judge exists.

**The judge (F).** .claude/agents/design-critic.md, sonnet, captures its own
screenshots, refuses to score a line without citing what it sees, treats any line at 0
or 1 as a blocker, and must name the one thing it would keep. NOTE: a new agent file is
not invokable in the session that creates it — the registry loads at startup — so round
1 ran as an inline sonnet agent pointed at the same file.

**Round 1 (G).** A 34/50 FAIL, B 40/50, C 37/50. A was disqualified by a bug, not
taste: at 1440x900 its H1, price and CTA are all below the fold, because the frame's
negative-margin bleed makes it ~775px tall at that width and `align-items:end` drags
the text column down with it. I verified the arithmetic before accepting it. The floor
and every unit test pass on that page — only a screenshot finds it.

B shipped, with all three of the critic's fixes rather than just its verdict:
repeat(3,1fr) -> 2fr/1fr/1fr (cardocalypse geometry is a tell with or without cards);
body copy moved off Chivo Mono to Public Sans with mono kept for labels and frame
numbers; sample frames moved below the trust content so they stop competing with the
CTA for the same thumb. Kept from A: the focus ring that draws. Kept from C: the
asymmetric facts grid and the reduced-motion guard.

The critique's sharpest note was aimed at me: all three variants reused the same
"Studio" + accent-coloured "Face" wordmark, so one of the "three different decisions"
was never re-decided, only re-hexed. The mark is now labelled, not branded.

    before:  DESIGN AUDIT: 1 P0, 0 P1, 0 P2   FAIL
    after:   DESIGN AUDIT: 0 P0, 0 P1, 0 P2   PASS

**Only then wired.** scripts/ci.py runs the audit AFTER the tests and skips it when
there is no export; deploy.yml has a `design` job that builds the frontend first and
`infra` needs it. Wiring it earlier would have made the gate red and blocked the very
commits that fix the design. Deploy 35258843367 green on all five jobs.

**Live check:** Newsreader, Public Sans, Chivo Mono and "Hoja 01" present on
studioface.app; Fraunces, #FAFAF7 and #1D4ED8 gone. The one "Inter" left in the HTML is
inside `afterInteractive`, a Next.js Script prop, not a font.

**Item H.** /recuperar/ is in the footer — it existed with nothing linking to it, so a
buyer who closed the tab and lost the email had no way back into a paid product. The
refund FAQ asked "¿Y si no me convencen?" and answered with our delivery condition; it
now matches min_deliverable=4 and points at the free preview. Issue #6 opened for the
before/after pairs, sequenced so the 4242 run produces them.

## 2026-09-17 (operator session, part 4) — the loop ran three rounds and stopped

**Round 1 (mocks):** A 34/50 FAIL, B 40/50, C 37/50. B shipped.
**Round 2 (real pages): 32/50 FAIL.** All three round-1 fixes had landed and worked;
the score fell because the critic looked at pages I had not. I redesigned ONE of seven
routes. Tokens are CSS variables and inherited fine; `--font-fraunces` had been
deleted, and /recuperar/, /g/ and four /legal/* pages still asked for it, so their H1s
fell back to body weight. An undefined CSS variable is not an error, it is a silent
fallback — invisible to 227 tests and to the floor, obvious in one screenshot.
**Round 3: 39/50.** All four fixes verified live with getComputedStyle, not by reading
code. Only line 5 below 3.

Fixed across rounds 2 and 3, and three of the four were states:
- the "drawing" focus ring was on footer links only; the checkout button — the one
  control the whole funnel runs through — kept the generic shadcn ring
- hovering the upload target did nothing; no rule existed
- choosing a file exposed the raw 20px OS control and never named the files back
- an invalid email produced the browser's English validation bubble on a Spanish product
- **the CTA measured 36px tall**, under the 44px tap floor, from shadcn's `lg: h-9`.
  Found by getBoundingClientRect at round 3. It survived every test, the audit and two
  rounds of screenshots because 36px looks fine; it is only wrong under a thumb.
  tests/test_tap_targets.py now holds the floor and checks both CTAs actually ask for
  that size, since fixing the variant achieves nothing if they use the default.

**Stopped at three rounds, as instructed, and the target is arithmetically out of
reach rather than merely unmet.** Line 5 (value visible above the fold) is capped at 2
by the rubric while we show no real photographs, so "40/50 with no line below 3" fails
on line 5 alone however good everything else gets. Issue #6 unblocks it. Issue #3 is
worth about +1 each on lines 6 and 10, which would put the total near 41.

Two process notes worth keeping: a new agent file is NOT invokable in the session that
creates it (the registry loads at startup), and the critic's `http.server` left
frontend/out locked, so a rebuild failed EBUSY and the gate then audited a STALE export
and reported green. Kill the server, rebuild, re-run — and tell the agent to clean up.

## 2026-09-17 (overnight run) — hazards, and what the tooling taught us

**A new agent file is NOT invokable in the session that creates it.** The agent
registry loads at session start, so `.claude/agents/design-critic.md` could be written
and used only from the following session; round 1 of the critique had to run as an
inline sonnet agent pointed at the same file. Write the agent file one session before
you need it, or plan to run it inline the first time.

**The stale-export false green is closed at both ends** (3319813). The gate compares
the oldest file in frontend/out against the newest in frontend/src, before the audit,
and the critic is told to serve a temp copy so no server can hold the lock. The first
version of the rule was wrong and production said so at once: Next copies
frontend/public verbatim and PRESERVES mtimes, so file.svg reported the export 28824s
stale on a build that had just succeeded. Public copies are excluded, with a held-out
test proving that is not a hole a stale route can hide in.

**The footer-link hazard was already fixed** (c962f44). The brief reported four legal
links and no recovery link on the live page; measured, it is there, live and in all ten
built pages. The link shipped in 1ec5e9b; a fetch from before that, or an edge cache,
explains the report. Test added anyway, because "it is in the shared footer" is a claim
about a component and what ships is ten static HTML files.

**Vendor facts had to be settled against live APIs, not documentation.** Context7 has no
gpt-image-2 page, fal's own docs URL 404s, and repeated fetches of the marketing page
returned CONTRADICTORY application ids. The authoritative source turned out to be
`GET https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=<id>` with the fal key,
which is generated from the deployed app. Worth knowing for every future fal change.

**Two cautions recorded in docs/verified.md.** `POST https://queue.fal.run/<id>` with
body `{}` returns 200 and QUEUES the job — it does not validate up front, so probing an
endpoint that way is not free by construction. And fal publishes no price for
gpt-image-2 anywhere I could reach, so spend is measured from
`https://rest.alpha.fal.ai/billing/user_balance` rather than estimated.

**docs/cli-verified.md now exists** because the user-level guard_shell hook refuses any
gcloud subcommand not listed there with a date inside 30 days. It is ASCII-only on
purpose: the hook reports through a cp1252 console and turned em dashes into
replacement characters, so the ledger avoids them entirely.

## 2026-09-18 (overnight run) — assets, wardrobe, prompts, legal, email

**Item 2, demo assets. Spend $0.9744 of a $3.00 ceiling, measured not estimated.**
Three before/after pairs in frontend/public/muestras. The "after" images are real
production output via POST /internal/generate; the payment is not real and the code
says so — demo- order ids, amount_cents 0. First live proof of signBlob end to end,
which HANDOFF has carried as unproven since the overnight build.

gpt-image-2 renders "three photographs of the same person" as ONE collage rather than
three images. Identity coherence across the panels is excellent, which is what the
single call was for, but a collage is not a "before" — so --recrop rebuilds the pairs
from the artifacts already in GCS for $0.00 rather than paying twice for a framing
mistake.

**The wardrobe was menswear for everyone** (0e84958). Every style hard-coded a man's
shirt. The repair is NOT a gender question: the customer picks a garment, six options
named after clothes, and a test fails if any option is ever labelled after a kind of
person. Reasoning and citations in guards.py — GDPR Art. 9 does not name gender
identity, Ley 4/2023 makes self-declaration authoritative, and Aragon.ai sells "choice
of attire" without asking. wardrobe=None reproduces the old prompt exactly.

**The prompt told the model what to leave out** (cb98133). Google's own guidance says
to phrase exclusions positively, and nano-banana-2 has no negative-conditioning input,
so "no hands" was just the word "hands" in the prompt. Rewritten as scene facts. The
test caught two more ("no harsh shadows", "no tie") and caught me introducing a
contradiction — my first affirmative draft asserted a plain backdrop, which fought the
linkedin style's office setting.

Recorded as NOT sourced, so nobody re-derives it: named lighting patterns (Rembrandt,
butterfly, loop, split, clamshell) appear nowhere in Google's docs, and no reachable
photography source confirms corporate-headshot lens/height/backdrop conventions. Our
"85mm at f/2.8" is unverified folklore that reads plausibly. Left in place, labelled.

**Item 4, legal** (394e90a). limeralda, NIF Z3714124-C, Maria de Molina 31, Madrid, in
all three files. The Pending component is deleted, not merely unused. Before/after
screenshots of /legal/terminos/ at 390x844 in docs/design-review/. Issue #3 closed.

**Item 5, email — DONE and verified as delivered, not merely accepted.**
The delivery mail was the bare gallery URL as the entire plain-text body: phishing to
a person, bulk to a filter, arriving when the customer is deciding whether paying was
wise. app/emails.py now sends html + text for both messages.

    POST https://api.studioface.app/api/recuperar  ->  {"sent": true}
    GET  https://api.resend.com/emails/01a0b177-4a3f-738c-ae47-fb540912bf8c
      to        kevinleonjouvin@gmail.com
      from      StudioFace <fotos@studioface.app>
      subject   Tus fotos de StudioFace ya están listas
      last_event delivered
      html 2039 chars, text 538 chars, button present, trader identity present

The Resend list carries its own before/after: 21:43 and 21:44 are the old bare-URL
sends with the old subject; 22:22-22:23 are the new ones. All delivered.

**Resend region is us-east-1, not eu-west-1** (issue #7). Verified, not assumed. The
domain IS verified so item 5 was unblocked; the privacy page already discloses
processing outside the EEA, so it is disclosed rather than contradicted.

**Follow-up worth doing:** the send_email port passes either a link or the literal
"REFUND" and the adapter sniffs the sentinel. That is a poor contract. It is pinned by
a test (a link containing the word REFUND is still a delivery) rather than fixed,
because fixing it touches Pipeline and every test that fakes the port.

### The paid walk, 20 September — run, and what running it cost to learn

The paying half had been written on 19 September and deliberately never run. It was run
today. It failed three times for three unrelated reasons, and only one of them cost
anything, because the expensive ones were found before spending.

**Before any fal call.** `checkout.stripe.com` no longer renders a card form. With
several payment methods enabled it renders a COLLAPSED accordion — Tarjeta, Klarna,
Bancontact, EPS — and no card field exists in the DOM until Tarjeta is chosen
(`docs/audit/stripe-hosted-page-probe.png`). The walk waited on a card placeholder that
was never coming. Two more: the placeholders are localised (the page came up **German**
under the walk's default browser context, Spanish under `es-ES`), and
`get_by_placeholder(re.compile("MM ?/ ?[YA]"))` cannot compile at all — the `/` ends the
attribute value and Playwright raises `InvalidSelectorError`. That line would have thrown
on every run since the day it was written.

Found with a test-mode Checkout session and a headless browser, no fal call. A4.4a said
these selectors were unversioned and would break without notice; they did, and they now
live in `tests/e2e/stripe_checkout_page.py` behind `tests/e2e/test_stripe_hosted_page.py`,
which fills the form and stops at the pay button without pressing it. It costs nothing and
runs in twelve seconds.

**Paid run 1 — two causes, one image.** The browser was redirected to
`https://studioface.app/g/?o=cs_test_...` holding an order that existed only on
127.0.0.1, and polled production for the full ten minutes. `GALLERY_BASE` was a module
constant, so no composition root could say otherwise. `make_app` takes `gallery_base` now;
the default is unchanged, so production behaves exactly as before.

Underneath that, fal had refused all four generations anyway:

    Invalid URL scheme 'gs:' in image URL. Only http://, https://, and data: URLs
    are supported.

The pipeline was built with `sign=lambda uri: uri`, so the delivery path handed fal
`gs://local/previews/<batch>/0.jpg`. The preview path had learned this in September; the
delivery path never had, because nobody had run it. `LocalStorage.sign_for_fal` now
returns the address fal itself gave back, and `tests/test_funnel_storage.py` is the
second-long version of the ten-minute failure.

Run 1 therefore spent **one** fal image, not five: the four generations were refused
before any picture was made.

**Paid run 2 — five images, and one honest assertion failure.** Everything worked. The
browser landed on the LOCAL gallery, four real images were generated and delivered, and
`test_descargar_downloads_and_the_tab_stays_put` PASSED. The gallery assertion still
failed:

    AssertionError: P4: an image decoded nothing: [0, 0, 0, 0]

Measured against that same delivered order afterwards, at no cost:

    at the instant the 4 elements exist [[0, False], [0, False], [0, False], [0, False]]
    after 1s                            [[928, True], [928, True], [928, True], [928, True]]
    violations: []

Four elements existing is not four pictures. The walk waited on the COUNT and then read
`naturalWidth`, which times the browser's decoder rather than the gallery. It now waits
for `complete && naturalWidth > 0`, and the sibling race in the preview half is closed
too. Re-run against the live delivered order:

    fixed predicate satisfied after 0.23s; widths=[928, 928, 928, 928]
    ASSERTION THAT FAILED THE PAID WALK NOW HOLDS

**needs Kevin: a third paid run, ~5 fal images.** The brief allowed two and both are
spent. Every cause is fixed and each fix is proven, but the artefact
`docs/audit/paid-walk-2026-09-20.txt` still holds run 2's red output and its check is
therefore red. The exact commands:

    .venv\Scripts\python.exe scripts\run_funnel.py --serve-only
    $env:RUN_FUNNEL='1'; $env:RUN_FUNNEL_PAID='1'
    .venv\Scripts\python.exe -m pytest tests/e2e/test_funnel.py -v -s -k "paying or descargar" 2>&1 | Tee-Object -FilePath docs\audit\paid-walk-2026-09-20.txt

**fal images spent on this task: 6** — one in run 1 (its four generations were refused),
five in run 2 (one preview, four delivered). Gate: 685 passed, 15 skipped, green.

## Still open
- Issues #1-#5, all Kevin's: fal balance, Resend domain, legal details, run the 4242
  purchase and say which Stripe mode production is in, disable 18 secret versions.
- The ten "Lessons, 17 Sep 2026" rules were not in the message I was given, so
  CLAUDE.md has not been touched. Paste them and it is one commit.
- No dependency cache on any CI job.
- The two GO-LIVE defects above, neither of which bites until go-live.

## 2026-09-18 (self-heal) — deploy 35313074204, and the hook that still was not attached

**The red run, and who fixed it.** The `ci` job failed on
`tests/test_pre_push_hook.py::test_git_is_actually_pointed_at_the_versioned_hooks`,
which asserted `git config --get core.hooksPath == .githooks`. That is per-clone LOCAL
config in `.git/config`; no file in the repository can set it and `actions/checkout@v4`
makes a fresh clone that never had it, so the assertion could not pass on any runner,
ever. `infra` (`needs: [ci, emulator, design]`) never started and `deploy` never
started. The test landed in 0599d33, the same commit whose deploy went red.

Reproduced on the tip rather than read from the log, because `gh run view
35313074204 --log-failed` was NOT available here — this token gets `HTTP 403: Resource
not accessible by integration` on every `/actions/` route, `gh run list` included:

    $ git rev-parse HEAD   ->  0599d33
    $ python scripts/ci.py
    E  AssertionError: core.hooksPath is not .githooks   /   assert '' == '.githooks'
    1 failed, 310 passed, 16 skipped        CI MIRROR GATE: red at: pytest

While this session was diagnosing, a concurrent session pushed **ed0945d** with the
same diagnosis and essentially the same fix (skipif on `CI=true`, plus the
`core.hooksPath` line in `bootstrap.py` `git_push`). Per the standing invariant — a
healer must never heal a commit that is no longer the tip of main — this session's own
duplicate heal commit was NOT pushed. It is parked on the local branch `heal-findings`
(871da16) and can be deleted. Main's tip verified green here, all five jobs mirrored,
`DESIGN AUDIT: 0 P0, 0 P1, 0 P2 PASS`, and the formerly red case now reports
`7 passed, 1 skipped` under `CI=true`. Production never changed, which is what a red
`ci` job should mean: `GET https://api.studioface.app/health -> 200
{"ok":true,"killswitch":false}`, `GET / -> 200`.

**What ed0945d did not fix, and this commit does. The gate was still attached to
nothing.** Both halves were verified by measurement, not by reading code.

1. `.githooks/pre-push` was mode `100644` in the index. git tests a hook with
   `access(X_OK)` and SILENTLY skips one it cannot execute — no error, no gate, exit 0.
   git said so itself, on this session's push attempt:

       hint: The '.githooks/pre-push' hook was ignored because it's not set as executable.

   So `core.hooksPath` could be set, the two tests about the hook's contents could pass,
   and every POSIX clone would still push unguarded. Fixed with
   `git update-index --chmod=+x .githooks/pre-push`, pinned by a test that asserts the
   INDEX mode, because the index is what a clone receives. Kevin's Windows box is the
   one place this never bit: Git for Windows cannot represent the bit and ran the hook
   anyway, which is why the measured hook costs in that file are real.

2. `test_a_fresh_clone_gets_the_hook_without_anybody_remembering` greps bootstrap.py
   for the string `core.hooksPath` — and the comment explaining the line contains that
   string. Measured: delete the `sh(["git", "config", "core.hooksPath", ".githooks"])`
   call, keep the comment, and the held-out test still reports `1 passed`. It cannot
   tell an attached gate from a described one. `tests/test_bootstrap.py` now also
   exercises `git_push` with `sh` faked and asserts the argv, which no comment can
   satisfy. Both tests are kept: one guards the file, one guards the behaviour.

### Follow-up found while fixing this — FIXED 18 Sep
`scripts/ci.py` used to build the whole plan before the first step ran and drop the
design audit when `frontend/out` was absent, so a clean clone built the frontend and
then never audited it while still printing `design  mirrored`. The plan is no longer
filtered up front: whether the audit can run is decided WHEN it runs, and the skip is
printed either way. Verified by the gate's own coverage table on every run since.

## 2026-09-18 — UI run: hero, wait states, conversion, motion, budgets, and one outage

Ten commits, each gated and deployed green. The design critic went **41/50 FAIL → 49/50
PASS**, no line below 4. But the most important thing in this run is not a design item.

### The outage: nobody could buy, and had not been able to for some time

Found while trying to automate the 4242 test purchase. **The Turnstile widget never
rendered in production.** Measured against studioface.app, six time points:

    t=    0ms  window.turnstile=undefined  widget children=0  token fields=0
    t=10000ms  window.turnstile=object     widget children=0  token fields=0

`useEffect(..., [])` opened with `if (... || !window.turnstile) return;`. Next loads the
script `afterInteractive`, so it has not run when React fires mount effects. The effect
bailed once and never ran again → token `""` → `/api/preview` 403 → every visitor told
"No hemos podido verificar que no eres un robot". Deterministic, so reloading never
helped. No preview means no checkout.

My **first fix was also wrong** and only measuring caught it: `turnstile.ready()` is the
first pattern in Cloudflare's docs and their runtime refuses it against an async tag —
"Remove async/defer from the Turnstile api.js script tag before using turnstile.ready()".
Same symptom, different cause. Now a bounded poll. Verified on production after deploy:
widget children 0 → 1, token field 0 → 1, and the widget reads "Verifique que es un ser
humano" in Spanish.

### What shipped

| item | evidence |
|---|---|
| Hero A/B decided from screenshots | inset gives the "después" 4.01× the area; on mobile the photograph follows the H1 and 340px of 340 is visible inside the 691px slot, against 85px of 212 before |
| /g/ and /recuperar/ wait states | two fake progress bars deleted (`value={45}`, `value={60}`); dead canvas 383px → 48px |
| docs/CONVERSION.md | 8 events, 7 falsifiable hypotheses, all 8 verified firing in a browser |
| Motion | five named moments; measured `transform 0.08s` under no-preference and `none` under reduce with `:active` still true |
| Budgets | landing 465.9 KB → **324.1 KB**; Lighthouse mobile 98/100/100/100 |
| Tap targets | four 32px controls on the money path, now 44px |
| `scripts/go_live.py --dry-run` | preflight that checks everything and can change nothing |

### The fold is 691px, not 844px

The consent banner is fixed to the bottom and up on every first visit. Every "above the
fold" measurement before this run was against a page nobody was looking at.

### A bug class that bit four times in one day

A test that reads its own rationale, or a regex whose `\b` reaches the file as a literal
backspace byte. `test_header` grepped the comment saying why the header is not sticky;
`test_the_wait` caught `<Progress value={60}>` inside the note recording its deletion;
`test_motion` and `test_tap_targets` both shipped patterns that could not match anything
and passed against seven and four real offenders respectively. Every affected test now
strips comments before reading, and two files carry a test asserting the pattern matches
what it claims to.

### Follow-ups, not fixed

- **#4 the test purchase is still yours.** The one action that creates a real order and
  spends real fal credit was refused by this session's guard, which is the right line.
  Everything around it is ready and the exact commands are on the issue.
- **#10 `infra/stripe.tf` is missing `refund.updated` and `refund.failed`** (GO-LIVE step
  11b). Two lines, but applying them is sequenced inside the go-live procedure.
- `docs/design-references.md` (study three reference pages) was never written.
- Rebuilding `frontend/public/muestras/` from a real order depends on #4.
- Line 2 of the rubric stays at 4/5: "19,99 €" carries three visual treatments on one
  mobile viewport — 28px serif hero, 14px muted header, 14px muted FAQ answer.
- The stale follow-up about `scripts/ci.py:252` dropping the design audit on a clean
  clone is **fixed** — the plan is no longer filtered before the build step runs.

## 2026-09-18 (self-heal) — deploy 35346406139, and the second job nobody fixed

**Cause.** 931874f added `playwright==1.55.0` to `[dev]` and
`tests/test_verify_production.py`, which drives a real Chromium. The PACKAGE and the
BROWSER BINARY are two separate installs: `pip install -e ".[dev]"` gives the module, and
the ~100 MB binary only arrives with `playwright install`. The file's guard was
`pytest.importorskip("playwright.sync_api")`, which sees the module and cannot see the
binary — so the browser cases did not skip, they failed. `ci` went red, `infra`
(`needs: [ci, emulator, design]`) never started, `deploy` never started. Production was
never touched, which is what a red `ci` job should mean.

**Evidence.** `gh run view 35346406139 --log-failed` was NOT available: this token still
gets `HTTP 403: Resource not accessible by integration` on every `/actions/` route, as
recorded on 17 Sep. Reproduced on the tip instead, by rebuilding the CI environment
exactly — module present, binary absent:

    $ PLAYWRIGHT_BROWSERS_PATH=/nonexistent pytest tests/test_verify_production.py
    playwright._impl._errors.Error: BrowserType.launch: Executable doesn't exist at
    .../chromium_headless_shell-1187/chrome-linux/headless_shell
    2 failed, 4 passed

**A concurrent session fixed it first, and that is not the interesting part.** While this
session was diagnosing, **0ea9dd9** landed with the same diagnosis: browser install in
`deploy.yml`, a `playwright install` exemption in `workflow_lint.py`, and a module-scoped
fixture that SKIPS on a laptop and FAILS when `CI=true`. That fixture is a better answer
than the one this session had written — a skip that cannot hide on the one machine that
matters — and it is measured to work:

    $ env -u CI PLAYWRIGHT_BROWSERS_PATH=/nonexistent pytest tests/test_verify_production.py
    6 skipped

Per the standing invariant — never heal a commit that is no longer the tip of main — this
session's duplicate heal was NOT pushed. It is parked on the local branch
`heal-duplicate-347b925` and can be deleted.

**What 0ea9dd9 missed, and this commit fixes. TWO jobs run the whole suite, and only one
was fixed.** `deploy.yml:ci` got the browser; `ci.yml:ci` did not. GitHub sets `CI=true`
on every runner, and the new fixture fails rather than skips there, so the job that gates
**every pull request** was red on every run while main stayed green. Measured on 0ea9dd9,
in that job's exact environment:

    $ CI=true PLAYWRIGHT_BROWSERS_PATH=/nonexistent pytest tests/test_verify_production.py
    6 errors                                   <- every pull request

**The install went into the GATE, not into a second workflow job, and that is the better
fix rather than a workaround.** The defect was duplication: a setup step copied per job
is a step that gets forgotten in one, which is exactly what happened. `scripts/ci.py`
now installs the browser before it runs pytest, so every job that runs the gate is
covered by construction — and Kevin's box runs these cases instead of skipping them
forever. Proven on a genuinely browserless box, in `ci.yml`'s environment:

    $ CI=true PLAYWRIGHT_BROWSERS_PATH=/tmp/freshbox pytest tests/test_verify_production.py
    6 errors
    $ PLAYWRIGHT_BROWSERS_PATH=/tmp/freshbox python -m playwright install chromium
    Chromium Headless Shell 140.0.7339.16 downloaded
    $ CI=true PLAYWRIGHT_BROWSERS_PATH=/tmp/freshbox pytest tests/test_verify_production.py
    6 passed

No `--with-deps`: that half is apt-get as root and this also runs on Windows. The run
above is the evidence that the plain install is enough on the ubuntu-latest image — the
OS libraries are already there. Cost when the browser is present: 0.4s.

**A constraint worth recording, because it will recur.** The first version of this fix
edited `.github/workflows/ci.yml` and could not be pushed:

    ! [remote rejected] main -> main (refusing to allow a GitHub App to create or
      update workflow `.github/workflows/ci.yml` without `workflows` permission)

This token can read no `/actions/` route and cannot write workflow files at all. Any
future fix that lives in a workflow file needs Kevin; a fix that lives in the gate does
not. That is a second, independent reason to prefer the gate.

**Two guards in `tests/test_ci_contract.py`, both held out and measured.**
- The gate's plan is IMPORTED and the order asserted, not grepped: move the install
  after pytest and the test fails. Reading the source as text would have passed on a
  step that is described in a comment and never run.
- The matcher for "jobs that run the suite" reads `- run:` steps, NOT substrings,
  because self-heal.yml:55 mentions `python scripts/ci.py` inside its PROMPT. A
  substring search would have demanded a browser install in the healer's prose. That is
  the bug class that bit four times on 17 Sep, and it now has its own test.

    before:  6 errors      (ci.yml's environment, on 0ea9dd9)
    after:   418 passed, 7 skipped    DESIGN AUDIT: 0 P0, 0 P1, 0 P2
             WORKFLOW LINT: ok        CI MIRROR GATE: green in 17s

**Open, unchanged by this commit:** `deploy.yml`'s explicit `--with-deps` step is now
redundant with the gate's own install, but removing it needs the `workflows` permission,
and it is harmless (idempotent). There is still no dependency cache on any CI job;
caching `~/.cache/ms-playwright` is the obvious first one.

## 2026-09-18 — the third outage, the post-mortem, and what still cannot be seen

### Post-mortem: three outages in two days

**What they were.** (1) `success_url` carried no `t=` token, so every paying customer
landed on "Este enlace no es válido o ha caducado." (2) The Turnstile widget never
mounted — a `useEffect(..., [])` bailed on `!window.turnstile` before the
`afterInteractive` script had run, and never ran again — so `/api/preview` answered 403
to everybody. (3) `NEXT_PUBLIC_API_URL` pointed the browser at `api.studioface.app`, a
different hostname on a service with no `CORSMiddleware`; `/api/checkout` preflighted
into a 405 and `/api/preview` had its response withheld for want of an
`Access-Control-Allow-Origin`. Each one, alone, made the product unsellable. Their shared
cause is not three coding mistakes. It is that **every test in this repository ran either
inside the process — pytest against the FastAPI app object — or inside the build —
Playwright against a static export on localhost.** Neither vantage point can see a
`success_url` Stripe builds, a script tag Next injects at a particular moment, or a
browser refusing to hand a response to a page. All three defects lived in the space
between correct parts.

**Why nothing saw them.** At the moment outage 3 was live, this repository had 407
passing tests, five green CI jobs, a design critique of 49/50 from an agent that had
measured the live DOM with `getBoundingClientRect`, a Lighthouse mobile score of 98, and
a deploy smoke step that curled `/health` and `/` and got 200 from both. Every one of
those instruments was telling the truth about the thing it measures, and none of them
measures whether a stranger can buy a photograph. The smoke step is the sharpest example:
it asked the two questions a dead funnel answers perfectly. The design critic is the
subtlest: it scored the page a human sees, which was genuinely good, on a page whose
first button returned 403. A test suite can be simultaneously green, honest, and blind,
and the blindness is structural rather than careless — nobody had ever written down that
"the parts are correct" and "the product works" are different claims needing different
evidence.

**What is true now.** `scripts/verify_production.py` takes a public URL and nothing from
this repository's internals, and answers seven links from outside: health, the landing
document, the gallery's rejection of a forged token, what a CORS preflight actually does,
whether the Turnstile widget mounts and produces a token field, whether any `/api` call
leaves the origin, and the free preview. It runs as the last step of every deploy against
the public hostname, so **a deploy that leaves the funnel dead is now a red deploy**, and
on a 15-minute schedule as a canary that opens one reused issue titled `PRODUCTION DOWN:
<link>`. Two of the three outages are reproduced as fixtures in
`tests/fixtures/production/` and the checker is pointed at them on every test run, so the
claim "it would have caught them" is a test rather than a promise. The fourth outage will
be visible within fifteen minutes, named by the link that broke, instead of whenever
somebody opens the site.

### The rest of the verification gap, enumerated

Everything below is currently verified ONLY by something that never crosses the network.
The point of the list is that it exists, not that it gets closed today.

| behaviour | verified today by | covered by the new check? | what would cover it |
|---|---|---|---|
| Stripe webhook signature against a real Stripe delivery | `tests/test_money_path.py` constructs the signature locally with the same library Stripe uses | **no** | a Stripe CLI `trigger` against the deployed endpoint, asserting 200 and exactly one order written |
| Cloud Tasks actually dispatching | fake queue in `tests/fake_runner.py`; the real dispatch has never been observed | **no** | the test purchase; or a synthetic task enqueued to a no-op internal route, asserting one attempt |
| Signed URL retrieval from a browser | `tests/test_signed_urls.py` checks the URL is built and expires in 15 min | **no** | the canary fetching one delivered image over the network and asserting 200 then 403 after expiry |
| Resend actually delivering | `tests/test_emails.py` asserts the bodies; the transport is never exercised | **no** | Resend's API returns a message id — assert it, and the DMARC report says whether it aligned |
| GA4 actually receiving | the eight events were verified firing into `dataLayer` in a real browser | **partly** | `/debug/mp/collect` returns validationMessages; the property itself needs a real read |
| the fal call under real latency | `tests/test_generation.py` fakes the client; the 300s Cloud Run timeout has never been met | **no** | the test purchase, with the wall-clock recorded |
| the delivery email arriving in an inbox | nothing | **no** | send to a seeded address and assert receipt; the DMARC report covers alignment, not arrival |
| Firestore transaction under contention | `tests/test_counter_atomicity.py` against the real emulator in CI | **yes, adequately** | — |

The honest summary: **the money path from webhook to delivered image has never once been
observed end to end.** Everything before it (page, widget, preview request) is now checked
from outside every 15 minutes; everything after the checkout button is still inference.

### DMARC

**The policy is already `p=quarantine`.** Read with DNS-over-HTTPS from two independent
resolvers, identical from both (`docs/verified.md`, 18 Sep):

    _dmarc.studioface.app  "v=DMARC1; p=quarantine; rua=mailto:kevinleonjouvin@gmail.com"
    studioface.app         "v=spf1 include:_spf.mx.cloudflare.net include:amazonses.com ~all"
    resend._domainkey      RSA public key present   (the only signing selector)

The brief asked whether to move "toward quarantine". It is there. The open question is
`p=reject`, and there are three tags absent that matter more than the policy value:
`pct` (defaults to 100), `adkim`/`aspf` (default to relaxed), and `ruf` (no forensic
reports at all).

**Are Resend's IPs aligning? I cannot say, and I will not guess.** There are 24 of these
reports in the inbox going back to March. I read the 17 Sep message, but the aggregate
data is a zip attachment and the Gmail tooling here exposes its metadata and not its
bytes. I tried to reconstruct it from the raw MIME by hand; the result was a structurally
damaged archive — `local header offset -3`, deflate stream corrupt — which is exactly the
transcription-from-memory failure this whole day has been about. So the question stays
open with a one-line answer available:

    .venv\Scripts\python.exe scripts\dmarc_report.py <the .zip you saved from Gmail>

`scripts/dmarc_report.py` is written and tested against both a passing and a failing
report built from the RFC 7489 schema. It prints IP, count, SPF, DKIM and the policy
applied per source, and one verdict line.

**The recommendation, conditional on what that prints.** If every source is
`amazonses.com` space with `spf=pass dkim=pass`, over a week of reports and not one day:
move to `p=reject`, and tighten `~all` to `-all` in the same change, because a softfail
SPF under a reject policy is a contradiction nobody benefits from. If any legitimate
source is failing — most likely Cloudflare Email Routing forwarding, which breaks SPF by
design — fix that first; `reject` would bounce real mail. Do not move on one clean day:
one report covers 24 hours and this domain sends few enough messages that a quiet day
proves nothing.

**Move `rua` off Kevin's personal inbox.** These arrive daily, forever, from every
receiver, and the brief is right that this is the 42-CI-emails failure again: a channel
that fires on success buries the mail that matters. Proposed, not applied — the record is
DNS and I do not change DNS in an unattended run:

    v=DMARC1; p=quarantine; rua=mailto:dmarc@studioface.app; adkim=s; aspf=s; pct=100

with `dmarc@studioface.app` routed by Cloudflare Email Routing to a folder, or to a
parser. Note `adkim=s; aspf=s` moves alignment from relaxed to strict and should be
adopted only after the reports show strict alignment is already happening — it is listed
here so the whole record is on the table, not as a same-day change.

### Not done, and one stray

- The money path end to end is still issue #4 and still needs a human for the one step
  Turnstile exists to block. Everything around it is ready.
- `docs/design-references.md` has still not been written.
- I created a file at `C:\Users\KEYIN\dev\studioface-v2\tests\fixtures\dmarc\failing.xml`
  by mistyping the path. It contains the word "placeholder" and nothing else. The shell
  guard correctly refuses deletes outside the project, so it needs removing by hand.

### The consent banner: 153px of 691, and what the rules actually require

Verified against the AEPD's *Guía sobre el uso de las cookies* (MAYO 2024) and the press
note on its alignment with the EDPB guidelines, cited in `docs/verified.md`. The
requirement is:

> accepting and rejecting must be offered **at the same time, at the same level and with
> the same visibility**, in a prominent place and format, and it must not be more
> complicated to reject than to accept. Withdrawal must be as easy as giving consent.

**What that does and does not say.** It is a requirement of *parity and prominence*.
Nothing in it sets a minimum banner size, mandates a paragraph of explanatory prose in the
first layer, or forbids a compact presentation. Our banner already satisfies it: "Rechazar"
and "Aceptar" sit side by side, same layer, same size, both `size="lg"` at 44px, and the
reject button is first in the DOM. **We are compliant and merely larger than we need to
be.**

**The cost, measured.** 153px of an 844px viewport, which is 18% of the first screen and
the difference between our 691px usable slot and Basecamp's 761 or Linear's 844
(`docs/design-references.md`). It is the single largest lever on the first impression and
the only one that costs nothing in content.

**Where the 153px goes.** Three lines of body copy — *"Usamos cookies de medición y
publicidad. Puedes aceptarlas o rechazarlas. Política de cookies"* — wrapping at 390px,
stacked above the two buttons, with `var(--s3)` padding around all of it.

**The proposal, not applied.** Put the sentence and the buttons on one row at 390px by
shortening the copy to what the first layer has to carry — who is setting cookies, for
what, and a link to the detail — and letting the buttons sit beside it rather than under
it:

    Cookies de medición y publicidad.  [Política]     [Rechazar] [Aceptar]

Estimated at roughly 90–100px rather than 153, returning ~55px to the first screen. The
buttons stay 44px, stay side by side, stay same-size, and "Rechazar" stays first — every
property the AEPD requires is untouched, because none of them is about height.

**The trade-off, stated plainly.** Shorter copy in the first layer means the *purpose* is
compressed from a sentence to a phrase. The guidance requires the purposes to be
identified in the first layer, and "medición y publicidad" does identify them — but it is
terser, and terser is closer to the line. This is the reason it is a proposal and not a
commit: the 55px is a real gain, and being close to a line on a legal disclosure is
exactly the kind of decision that should be made deliberately by Kevin rather than
silently by me at the end of a long session. `tests/test_tap_targets.py` and the
`prefers-reduced-motion` guard already cover the buttons; a layout test would need to
assert the reject/accept parity explicitly before this ships.

**What I would not do:** make it dismissible by scrolling, shrink the buttons, move
"Rechazar" to a second layer, or grey it relative to "Aceptar". Each of those buys space
by breaking the one thing the rule is actually about.

## 2026-09-18 — security pass: five things, each measured before and after

| | before | after |
|---|---|---|
| security headers | **none at all** | HSTS, nosniff, Referrer-Policy, CSP — verified live |
| deployer IAM | `roles/owner` | eleven roles, owner removed, full apply proven without it |
| branch protection on main | none | force push, deletion and non-linear history blocked |
| self-heal token | 5 scopes | 3 — the 2 removed were never used |
| runtime dependencies | unpinned, resolved per build | 50 packages, 1011 sha256 hashes, `--require-hashes` |

**Headers.** `curl -I https://studioface.app/` returned content-type, accept-ranges,
last-modified, etag, cache-control, a trace id, content-length, date and server. That was
the whole list. The CSP allows exactly what was measured or documented — Turnstile from
Cloudflare's own reference, googletagmanager and a regional google-analytics host from a
live measurement of three routes, self-hosted fonts (next/font inlines them, so no
gstatic), and storage.googleapis.com for the gallery's signed URLs. **Stripe is
deliberately absent**: Checkout is a redirect, so the browser leaves this origin before
any Stripe code runs, and a test fails if a Stripe host appears. Verified in a real
browser against the real app: widget mounts, token issued, fonts load, **0 CSP
violations, 0 page errors**. `'unsafe-inline'` on script-src is the known weak point and
is written down rather than hidden — Next emits inline scripts and a static export has no
per-request nonce.

**IAM.** The deployer held `roles/owner`, from a credential a GitHub Actions workflow can
reach: read every secret's value, delete Firestore, delete the buckets holding customers'
photographs, remove Kevin. Replaced with eleven roles derived from the resource types in
`infra/*.tf`, each name confirmed against the live catalogue. Done in **two applies on
purpose** — Terraform uses these permissions to change these permissions, so the
replacements were granted additively first and owner removed only once they had been in
force for a whole apply. Both applies succeeded; owner is gone and the pipeline still
works, which is the proof that the list is right.

**Branch protection.** Required status checks were enabled, **measured, and removed**. A
push with `ci, design, emulator` required succeeded anyway (`3 of 3 required status checks
are expected`) because `enforce_admins` is false. They would block exactly one actor:
self-heal, which pushes as a GitHub App and runs *only when the checks are red*. Requiring
green checks to push the fix for a red check is circular. Having both needs a ruleset with
the healer as a bypass actor — a follow-up, not an improvisation.

### Follow-ups this created

- **Ruleset with a bypass actor**, so required status checks can exist without disabling
  the healer. Classic branch protection cannot express it.
- **Base images are still pinned by tag**, not digest (`python:3.12-slim`,
  `node:22-slim`). Digest pinning is stronger and is a real maintenance commitment: every
  base-image security update becomes a manual bump, and a stale pinned digest is its own
  vulnerability. Deliberately not half-done.
- **self-heal's prompt tells it to run `gcloud`** and the workflow has no
  `google-github-actions/auth` step, so that instruction cannot work. Removing
  `id-token: write` did not cause this; it revealed it.
- **Regenerating the lock** after any dependency change:
  `uv pip compile pyproject.toml --generate-hashes --python-version 3.12 --python-platform linux -o requirements.lock`.
  A test fails if a dependency in pyproject is missing from the lock.

---

# 19 September 2026 — UI / SEO / ads brief: go-live M1, then B0 and U1

## F8 state, re-measured against production before anything was touched

| | | |
|---|---|---|
| F8a | `POST /internal/budget` unauthenticated | **CLOSED** — 403 `pubsub_token`. The probe reported 500; it was actually **200**, i.e. worse than reported. Fixed earlier today as go-live U1. |
| F8b | `/api/gracias?session_id=cs_test_fake` | **CLOSED** — 404, no `Location`. Was a 302 minting a valid gallery token. Go-live U2. |
| F8c | `/docs` and `/openapi.json` | **OPEN, 200.** Go-live U4. Section 4 says not to start it here, so it is untouched. |
| F8d | CSP missing Google's hosts | **CLOSED today** — section 4's named exception, done first. |

## go-live M1 — the CSP blocked GA4's image pings and every Ads host

Ten hosts Google's own guide requires were absent. This was not only a future problem:
GA4 pings `www.googletagmanager.com` and `*.g.doubleclick.net` and `img-src` allowed
neither, so those were already being dropped. An Ads conversion tag would have been
blocked silently — zero conversions, reading as "the landing page does not convert".

Two things the guide does not say out loud, both in `docs/verified.md`:

- It specifies `script-src-elem`; we send only `script-src`, which CSP Level 3 falls back
  to. Correct today, silently undone the day anyone adds a `script-src-elem`. A test holds
  that shut.
- `https://*.google.<TLD>` is prose. Written literally it is a source that can never match
  and produces no parse error. We name `*.google.com` and `*.google.es`.

Evidence: 20 failed → 27 passed; outside-in check named all 17 missing hosts against
production, and is green at revision `studioface-api-00080-5jt` (image `704c5bb`, = head
of main at the time).

## B0 — the harness, and what it found

`scripts/ui_snapshot.py`, `scripts/ui_diff.py`, `scripts/analytics_probe.py`,
`scripts/dead_code.py`, `scripts/check_ad_copy.py`, plus the baselines under
`docs/ui/2026-09-19/`. Raw frames are gitignored; contact sheets and `geometry.json` are
committed.

The baseline reproduces F1 and F2 exactly and reproduces the finding behind them: the
primary call to action sits at y=1283 against a usable first viewport of 691px, so there
is no product action on the first screen at any of the three viewports.

Four things the harness found that were not in the brief:

1. **One browser context was shared across pages**, so the consent choice carried from the
   home page into the six pages after it and they were photographed already-answered while
   the file called them `first-visit`. One context per page now.
2. **There is no client-side validation in the uploader.** `accept=` is a picker hint,
   `onChange` stores whatever was chosen, every message comes from `/api/preview`. B0.2's
   "client-side validation error" state does not exist to capture.
3. **"5 de 4 elegidas"** — choosing five files renders that, and `files.slice(0, MAX_FILES)`
   silently drops the fifth. For U9.
4. **`pkill` does not exist on this machine.** A "restart" of the local server silently
   failed to bind, the old process kept the port, and every submitted state was
   photographed against an exhausted rate-limit counter. Ports are freed by PID now. Same
   class as M6: a stale thing answering while the evidence claims it is fresh.

**Dead-code baseline is mostly false positives.** 14 of 17 "unused" public assets are the
`muestras` before/after images, referenced by template literal (`more-muestras.tsx:89`),
which a literal-string scan cannot see. Four of the five "unused" svgs are referenced by
`scripts/demo_server.py:33`, outside the tree the scanner walks. Only `public/file.svg` and
`src/lib/utils.ts` are genuinely dead. See `docs/ui/2026-09-19/dead-code-before-notes.md`;
D1 must teach the asset rule about interpolations before deleting anything.

## U1 — the mobile header, and its collision with section 2

145 → 56 at 360 and 390; unchanged 69 on desktop. Everything above the fold moves up 89px.

**U1 and section 2 conflict and cannot both be honoured.** The header is one component on
every page, so shrinking it moves the five locked pages. The alternative — a different
header on legal pages — is worse for the reader and is the special-casing the clutter
rules forbid. So I verified the property the lock protects rather than the proxy:
comparing `before[145:691]` with `current[56:602]`, the same 546px of content above the
fixed banner, every locked page is **IDENTICAL**. Not one character changed; each is 89px
higher, so more is visible, never less.

`ui_diff.py` gained `--allow-header-shift`, **off by default**, which crops each capture at
its own header height, forgives nothing else, and prints every frame it forgave. It took
locked-page failures from 20 to 2.

The 2 that remain are `/g/` at 390x844 only, and are understood: that page is shorter than
the viewport, so the sticky footer sits lower on a shorter document. Footer pixels are
identical (sampled the underline rows: `(20,25,38)`, `(235,227,216)`, `(242,206,141)` at
matching offsets). Deliberately **not** forgiven by the flag.

## U2's latency gate, measured before writing any U2 code

From Cloud Run request logs, 30-day window:

- free preview, `POST /api/preview` 200: **only two exist** — 10.04s and 12.30s, median
  **11.17s**. The other 46 are 41 × 405 (the canary's preflight) and 5 × 403 (Turnstile).
- full generation, `/internal/generate/<order>` 200: 14.56s, 19.78s, 28.98s, median
  **19.78s**.

Both are an order of magnitude under U2's 120-second threshold and the slowest run seen is
28.98s. **"en dos minutos" stays.**

## needs Kevin

- **needs Kevin: five fresh previews.** The brief wants 20 preview latencies, or 5 fresh
  ones. Only 2 exist and generating more needs a human to pass a Turnstile challenge in
  production and spends fal credits. The U2 decision does not turn on it — the margin is
  4x — but the sample size is 2, not 20.
- **needs Kevin: `/docs` and `/openapi.json` are 200 in production** (F8c, go-live U4).
  Deliberately not started here, per section 4.

## Follow-ups this created

- **`/api/preview` has no latency log line**, which is why the measurement above had to
  come from Cloud Run's request log rather than ours. craft.md requires one.
- **The secrets file path under `/internal/` is being probed from the internet** — 5
  attempts in 30 days, all 404. Noted, not acted on.
- **The `--full` screenshots are unreliable for `position: fixed` elements**; the banner
  renders at a different offset than in the viewport capture. `ui_diff` handles it by
  masking the union of both post-crop positions, but anything else reading those files
  should know.
- **`--destructive` is still used for error text** in `upload-form.tsx`, the leftover token
  the UI skill calls an unfinished decision.

## U2 to U5, all verified against the deployed hostname

| unit | what moved | measured before -> after |
|---|---|---|
| U2 | the H1 | 38px/3 lines -> 30px/2 lines at 390; desktop unchanged at 68px; the F2 gap 129 -> 24 |
| U3 | the hero | inset thumbnail -> comparison slider, with crops aligned to 0.05% on face width and 0.03% on the eye line |
| U4 | the consent banner | 173 -> 106 at 360, 153 -> 106 at 390, 77 -> 63 at 1440; buttons 102.9/94.3 -> equal, same fill |
| U5 | the first-screen CTA | did not exist -> top 549 at 390x844, clearing the banner by 137px |

Cumulative, at 390x844 with the banner up: the usable slot is 691px and it now holds the
header with the price, the H1, the comparison slider, the AI disclosure, a working
product button and its reassurance line. Before, it held 606px of prose and the top of
somebody's hair.

### Two conflicts inside the brief, both resolved by measuring rather than choosing

**U1 against section 2.** The header is one component on every page, so shrinking it
moves the five locked pages. Resolved by checking the property the lock protects: with
the same 546px of content compared above the fixed banner, every locked page is
pixel-identical and simply 89px higher. `ui_diff.py --allow-header-shift` makes that
allowance explicit and prints what it forgave; it is off by default.

**U3's 42svh against U5's clearance at 360x640.** U3 requires the AI disclosure caption
directly under the frame; F11's prototype measured the 360 case without one. With it, a
269px frame puts the button under the banner. 42svh stays as U3's rule — at 390x844 the
frame is width-limited and the cap never binds — and a `@media (max-height: 700px)` block
tightens it to 34svh, which only short viewports see.

### The U2 H1 drops a phrase the UI skill asks for

The skill says the H1 contains "foto de perfil profesional" for Quality Score. U2 names
the replacement string exactly and it does not. The phrase survives in the page title
unit S2 specifies, which is what the ad account reads. Flagged, not dropped quietly.

### Section 7's analytics guard, run on production after U1-U5

(a), (b) and (c) unchanged: consent default with all four signals denied and
`wait_for_update: 500` at index 0 against a first `config` at index 4; 2 of 2
`/g/collect` requests carrying `gcs=G100`; all four granted after "Aceptar". Events went
from `[view_proof, upload_start]` to `[view_proof, cta_click, upload_start]` — exactly the
one difference the section allows. No STOP condition.

The probe had to be fixed first, and it is worth recording why: U5's button is an
`<a>`, and the probe looked for `main button`, so it found the uploader's submit and
reported `disabled: 'Ver una prueba gratis'` against a page that had a working button on
it. A guard that measures the wrong element reports "no change" most convincingly.

### The U5 deploy went red once, and it was not the change

`npm ci` inside the docker build failed with `npm error network`. self-heal fired and
also failed — the known follow-up already in this file: its prompt runs `gcloud` and the
workflow has no `google-github-actions/auth` step. Re-running the failed job succeeded on
the same commit, `c326546`. Nothing was changed to fix it, because nothing was broken.

---

# 19 September 2026 — funnel incident, Block 1 (F1, F2, F3, F8)

All four deployed and verified from outside at revision `studioface-api-00096-nmc`.
The outside-in monitor is 18 checks, all green, one BLOCKED by design.

| defect | root cause, file:line | fix | evidence |
|---|---|---|---|
| **I2** paying customer got `{"detail":"Not Found"}` | `app/entry.py:108` `dict(Session.retrieve(...))` raises `TypeError` on stripe-python 15 (`StripeObject` stopped inheriting from `dict`); `except stripe.error.InvalidRequestError` does not catch it; the bare `except` in `/api/gracias` turned it into 404 | `.to_dict()`, `stripe.InvalidRequestError`; gracias fulfils as well as redirects, claimed per session; an exception is now a 502 Spanish page with the recover link | the session from the incident returns 302 → `/g/`, the gallery answers 200 `delivered` with 4 images, a made-up id still 404s |
| **I1** preview never displayed | `app/preview.py:40` returned fal's own CDN address; `img-src` has never contained a fal host (`git log -S "fal.media"` empty) | the preview goes into the private bucket and comes back signed on `storage.googleapis.com` | `img-src allows our images` green; `test_csp_matches_served_urls.py` 1 failed → 5 passed |
| **O1** retry needed a page reload | the shipped bundle had exactly one Turnstile call, `render`; tokens are single-use | keep the widget id, `reset` after every attempt and from the retry button, submit disabled until a fresh token arrives | `turnstile can be reset` green: `turnstile.{render,reset}`. Against this morning's bundle the test reported `['render']` |
| **O2** fal's 422 became our 500 | the `preview_fn` call sat outside any try/except | `ModelRefused` in the adapter, 422 with a named detail, five new Spanish sentences | 8 tests; the audit table is in `tests/test_preview_errors.py` |
| **O11** "5 de 4 elegidas" | `onChange` stored everything, `slice(0, MAX_FILES)` dropped the fifth silently | count what is kept, filter non-images by type, say what was ignored | in the same commit |
| **O3** Descargar did not download | `download` is ignored on a cross-origin link, and the signed address had no `Content-Disposition` | two signed addresses per image; the download one carries `attachment; filename="studioface-<n>.jpg"` | `gallery offers a download` green; 7 failed → 8 passed |
| **O9** `/docs` public | no configuration for it | `Settings.enable_docs` from `ENABLE_DOCS`, default False, `make_app` fails closed | `schema is not published`: all three 404 |

## Two defects I introduced today, both found by my own checks

1. **The container would not start.** C1 wired `store_result=storage.put`, where `storage`
   is the imported module, not the bucket adapter. 609 tests were green because none of
   them ran `entry.py`'s composition root. `tests/test_entry_builds.py` now does, and
   reproduces the production traceback in 15 seconds.
2. **A verification request regenerated a delivered order.** My first C2 claimed
   idempotency on the session key; the webhook had claimed the event key, so the session
   key was free and the success URL rebuilt an order that was already `delivered`. Four
   fal images and a second delivery email to Kevin. The order document is the fulfilment
   record now and is checked before the claim key. Proven: three revisits, zero new
   generations.

## F6 — the audit says the prompts do NOT differ

O6 assumed preview and delivery ask for different clothes. They do not:

    STYLES['corporativo']['wardrobe'] = 'a dark navy blazer over a plain white shirt'
    PREVIEW  build_prompt('corporativo', 0)          wardrobe=None
    DELIVERY build_prompt('corporativo', i, None)    identical except framing

The only difference between the four variants is the framing phrase ("subject centred"
vs "subject slightly left of centre"). Both ask for the navy blazer over a white shirt.

So the divergence Kevin saw — a light blue shirt in the delivered photos — is the MODEL
not following the prompt, not a prompt mismatch. F6's rule ("if they differ, make the
preview use the delivery's wardrobe") does not fire, and no prompt was changed.
**This is a product decision for Kevin, not a defect to fix in code.**

## Follow-ups

- **F4, F5, F7 not started**: the gallery's false "revelando" flash, the silent 11-second
  preview wait, and structured logging. F7 matters most — application `logger.info` still
  never reaches Cloud Run, which is why I2 was "unknown from outside".
- **The local browser walk is not written.** The harness is (`tests/e2e/funnel_app.py`,
  `scripts/run_funnel.py`), the walk is not. Nothing has yet proven fail-then-retry or a
  real download event in a browser.
- **Blocks 2 and 3 not started.**
- **fal images spent this session: 4**, all from the duplicate generation above.

---

# 19 September 2026 — funnel incident, Block 1 complete except the walk

All eight F units are merged and deployed. F6 was reopened by the external reviewer and
the first answer was wrong; the corrected one is below.

## F6 — the first audit was wrong, and here is what the request bodies say

"The model did not follow the prompt" is rejected, correctly. I captured the ACTUAL
arguments for order `cs_test_a1eehOBw`, variant 0 on both sides, by running the real
code paths with a `subscribe()` that records instead of calling fal:

| field | preview | final |
|---|---|---|
| endpoint | `fal-ai/nano-banana-2/edit` | same |
| image_urls | one, the same signed source | same |
| aspect_ratio | `4:5` | same |
| output_format | `jpeg` | same |
| seed | absent | absent |
| num_images | absent | absent |
| **resolution** | `0.5K` | `1K` — deliberate, not clothing |
| **prompt** | `...a dark navy blazer over a plain white shirt...` | `...a smart-casual light blue shirt with an open collar...` |

The model obeyed both times. The order carries `wardrobe='camisa-azul'`.

**The defect is structural.** `Preview.__call__` calls `build_prompt(style, 0)` with no
wardrobe and has no choice: the wardrobe selector is rendered inside `{handle ? (...)}`,
so it does not exist until the preview has already returned. Upload, preview, THEN
choose clothes, then pay. Every customer who picks anything but the default is shown one
garment and sold another, by construction.

F6's rule — the preview must use the wardrobe the DEFAULT delivery uses — already holds:
the style default resolves to exactly `blazer-camisa`. So no prompt was touched, and the
customer's choice still wins for the four finals. What was fixed is the promise:
`/api/preview` returns which wardrobe it used and the page says so when the choice
differs. The key is derived by matching prompt text, not written down.

## The rest of Block 1

| unit | what it was |
|---|---|
| F1 | one Turnstile call in the bundle, `render`; no reset, so every retry replayed a spent token |
| F2 | fal's 422 left as a 500; `normalise` raised inside `preview_fn` so a corrupt file was a 500 too |
| F3 | `download` is ignored cross-origin and the signed address had no `Content-Disposition` |
| F4 | `loading` and `working` shared a branch, so everyone read "Estamos revelando" for two seconds |
| F5 | eleven seconds of one grey line; now a reserved 4:5 frame, an elapsed counter and two focus moves |
| F7 | nothing configured logging, so every `logger.info` went nowhere — the reason I2 was "cause unknown" |
| F8 | `/docs`, `/redoc`, `/openapi.json` published the whole money path |

F7's proof, from production after one probe request:

    INFO  app.main  gracias: refused session_id=cs_test_f7prob payment_status=None

`severity` is promoted out of the JSON by Cloud Run, which is how you know the object is
being parsed rather than stored as a string. That probe also caught a `session_id[:14]`
left behind in `/api/gracias` where the rule is twelve; a test now scans for any literal
slice of an id.

F5's number is measured, not offered: every successful `/api/preview` in the 30-day
window is 9.43, 10.04, 11.20, 11.26, 12.30 seconds — median 11.20, slowest 12.30. The
copy says "unos 15 segundos", rounding up past the slowest rather than quoting the
median.

## Outfit audit, 20 September — the request bodies, captured this time

O12 arrived as "blazer in the preview, light blue shirt in all four photos, and the
prompt text is identical". The prompt text is not identical. `docs/audit/outfit-2026-09-20.md`
has both request bodies side by side.

Logs could not answer it and were never going to: `jsonPayload.logger="app.adapters.fal"`
returns nothing in the 30-day window, and `app/adapters/fal.py` logs `application`,
`resolution`, `sources` and `latency_ms` and never the prompt, the aspect ratio, the seed
or the wardrobe. Reading the order document from production was refused by the sandbox,
so the customer's actual garment is still a "needs Kevin" line in the audit.

So it was reproduced: `tests/test_outfit_audit.py` walks the real funnel through the real
`app.entry.build()` — preview, checkout, webhook, `/internal/generate` — on the fixture
face, with only sockets faked, and captures every arguments dict handed to
`fal_client.subscribe`. Model id, the single reference photo and its order, `4:5`, `jpeg`,
no seed, one image per call: identical. Different: `resolution` 0.5K -> 1K, deliberate,
and one clause — `Preview.__call__` builds with `wardrobe=None` while the pipeline builds
with `wardrobe=order.wardrobe`, the garment the customer picks after the preview exists.

No behaviour was changed. That is F6's settled decision — the four finals honour the
customer's choice and the page says so when it differs from the preview — and the
disclosure is live in the deployed bundle:

    $ curl -s https://studioface.app/_next/static/chunks/2k1u3dv5i6bse.js | grep -o 'Tu prueba se ha hecho con.\{0,90\}'
    Tu prueba se ha hecho con ",d(E),". Las cuatro fotos finales usaran ",d(f),"."

What the audit added is the instrument: 8 tests, 681 passed, gate green.

## Still open

- **The local browser walk is not written.** This is the last Block 1 item. It is what
  decides, empirically, whether the Turnstile `callback` re-fires after `reset()` or
  whether the `getResponse` poll is what delivers the token — Cloudflare documents
  neither, and F1 was built to work either way precisely because of that.
- **Blocks 2 and 3 have not started.**
- **fal images spent this session: 4**, all from the duplicate generation caused by my
  own earlier verification request, which is fixed and re-proven.
- **The fal log line still cannot answer an outfit dispute.** It carries no `wardrobe=`
  and no prompt fingerprint, which is why 20 September's audit had to be reproduced
  locally instead of read. One key on the delivery call and on `checkout session created`
  would close it. Related: `preview_token` binds `batch` and `n` only, so `/api/checkout`
  accepts any `style` after a preview that is always `corporativo`.

## 2026-09-20 (Claude Code) — the paying half of the walk is green

`docs/audit/paid-walk-2026-09-20.txt` held a FAILED run: the gallery assertion read
`naturalWidth` at the instant the fourth `<img>` appeared and got `[0, 0, 0, 0]`. The fix
was already in the tree (67f8b7a: wait on four elements that are `complete` AND decoded,
then assert the widths); nothing had re-run it, so the recorded evidence still said red.

Re-ran it end to end against `scripts/run_funnel.py --serve-only` — real app, Cloudflare
dummy keys, Stripe test mode, card 4242, real fal. Both paid tests pass:

    tests/e2e/test_funnel.py::test_paying_lands_on_the_gallery_with_four_real_images PASSED
    tests/e2e/test_funnel.py::test_descargar_downloads_and_the_tab_stays_put PASSED
    ================= 2 passed, 6 deselected in 92.01s (0:01:32) ==================

Before spending anything, `tests/e2e/test_stripe_hosted_page.py` ran green (1 passed in
12.61s). That is the point of the tripwire: it costs no fal image, so a red paid walk
afterwards is a funnel defect and not Stripe UI drift.

**fal images spent: 5** — one preview plus four delivered, in a single paid run. The
budget was two runs; the second was not needed. `.funnel-storage` afterwards held
`previews/<batch>/preview.jpg` and `cs_test_.../0..3.jpg`.

One operational note worth keeping: while the funnel server is up, the built export
carries Cloudflare's dummy site key and `tests/test_turnstile_widget.py` correctly turns
the gate red. `run_funnel.py` rebuilds the real export on shutdown; killing the server
from outside skips that `finally`, so the rebuild has to be run by hand before the gate
means anything. Gate green after the rebuild: 685 passed, 15 skipped, 41s.

# 20 September 2026 — the task queue: two of seven, then the host reaped the loop

`scripts/queue_runner.py` runs `work/queue/*.md` one at a time, each in a fresh
`claude -p` process, and a task moves to `work/done/` only when its own `check:`
command exits 0. `scripts/check.py` holds the five outside-in production checks.
Both were proved against production before the first task ran: `robots`, `sitemap`,
`head` and `attribution` each exited 1 with the problems the brief predicted, and
`gallery_hidden` exited 0. Nothing was edited to make the checker agree.

## What the loop did

    13:46:57 RUN  01-outfit-audit.md attempt 1
    13:55:07 DONE 01-outfit-audit.md
    13:55:07 RUN  02-paid-walk.md attempt 1
    14:24:39 RUN  02-paid-walk.md attempt 2
    14:29:26 DONE 02-paid-walk.md
    14:29:28 RUN  03-sale-to-visit.md attempt 1
    <killed>

The loop did not finish and it did not fail. The host stopped the background
process because the machine was critically low on memory, roughly 40 minutes into
task 03. Per the host's own instruction the loop was not restarted.

Worth keeping: task 02 went red on attempt 1 and the runner re-ran it. The fix
commit is `67f8b7a fix(b): the walk waits for decoded pictures, not for four
elements` — the checker rejected the agent's first answer, which is the whole
reason the exit code decides instead of the model.

## State of the tree

Ten commits on local `main`, **none pushed, so nothing is deployed**. `origin/main`
is still `79b1ea3`. Tasks 03 to 07 are untouched in `work/queue/`; 05, 06 and 07
each need a deploy before their check can pass, so they cannot be finished without
a push.

Task 03 was killed after its research phase and before any code. Its nine verified
Measurement Protocol lines are committed to `docs/verified.md` (`5c05d15`) so the
reading is not repeated: the `consent` object and its two fields, `client_id` at
top level versus `session_id` inside `events[].params`, the `/debug/mp/collect`
path contradiction, and the two things Google still does not document.

## Follow-ups

- The queue agents committed to `main` directly rather than one branch per task.
  Nothing was pushed, so nothing reached production, but the brief asked for a
  branch per task and the runner does not enforce it.
- `scripts/queue_runner.py` has no memory ceiling and no resume marker. A reaped
  run loses the in-flight task's work; only the `work/done/` moves survive.

**Refreshing the public mirror:** rerun `scripts/make_public_mirror.py` into a NEW empty
folder, delete `.github/` from it, `git init`, add the mirror as `origin`, `git fetch
origin`, `git reset --soft origin/main`, `git add -A`, commit, and push to
`kevinleonj/studioface-v2-mirror` only — never to this repository, which stays private.

Replacing the mirror with a single commit each time would be tidier, but
`.claude/hooks/block_irreversible.py` refuses every forced push, so the mirror instead
carries one sanitised snapshot commit per refresh. Nothing leaks either way: every commit
on the mirror is output of the redactor, and no commit from this repository is ever
copied. Do not weaken that hook to make the tidier version work.

## 2026-09-20 (Claude Code) — task 03: the sale is tied to the visit and the ad click

`work/queue/03-sale-to-visit.md` was killed after its research phase on the earlier
queue run; its nine Measurement Protocol facts were already in `docs/verified.md`
(commit `5c05d15`). This session did the code.

**What changed.**
- `frontend/src/lib/track.ts`: `gclid`/`gbraid`/`wbraid` read once, at module load,
  into a plain in-memory variable (`clickIds`) — no `localStorage`, no cookie, so
  "no storage before consent" holds because there is no storage of these at all.
  `ga4Identifiers()` asks the already-running tag for GA4's visitor and visit numbers
  with `gtag('get', 'G-NLP25TBTRJ', 'client_id' / 'session_id', callback)`, bounded to
  1s since Google does not document the callback as always firing. `checkoutClick`
  renamed to `beginCheckout` ("begin_checkout").
- `frontend/src/components/upload-form.tsx`: fires `begin_checkout` with
  `value: 19.99, currency: "EUR"`; awaits `ga4Identifiers()` and sends all five ids
  (`gclid`, `gbraid`, `wbraid`, `ga_client_id`, `ga_session_id`) to `/api/checkout`.
- `app/core.py`: `Order` gained `gbraid`, `wbraid`, `ga_client_id`, `ga_session_id`,
  `payment_intent`.
- `app/main.py`: `/api/checkout` reads and forwards the four new fields;
  `_order_from_session` reads them (plus `payment_intent`) back off the Stripe
  session into the `Order` the webhook creates.
- `app/entry.py`: `_checkout_factory` accepts and stores all four in Stripe metadata.
- `app/adapters/ga4.py`: `Ga4Purchase` now prefers `order.ga_client_id` as the MP
  `client_id` (falls back to the old derived id when the browser reported none),
  sends `order.ga_session_id` as the `session_id` event param when present, and
  computes `transaction_id` from Stripe's PaymentIntent — never `order.id`, which is
  the same id already sitting in the customer's `/g/` gallery link and delivery email.
  No `consent` object is sent (researched this session, see below).
- `docs/CONVERSION.md`: renamed the row, added a "Tying the sale to the visit and the
  ad click" section with the full reasoning above.
- `docs/verified.md`: MP-6 through MP-6d (researcher: Google does not recommend or
  require a `consent` object on a server-sent MP event — omitting it is the documented
  default path), MP-7 (the debug endpoint does NOT enforce a named event's own
  "Required" fields — found by deleting `transaction_id` from a control payload and
  still getting a clean response) and MP-8 (the exact payload `Ga4Purchase` builds,
  validated clean).

**Evidence.**
- New/changed tests: `tests/test_ga4.py` (transaction id is never the gallery order
  id, falls back when Stripe reports no PaymentIntent, client_id prefers the browser's,
  session_id sent only when present) and `tests/test_checkout.py` (all four new fields
  pass through to `create_checkout`). `.venv\Scripts\python.exe -m pytest -q`:
  692 passed, 15 skipped (e2e needs `RUN_FUNNEL=1` + a live server, none started).
- `.venv\Scripts\python.exe scripts\ci.py`: green (ruff check, ruff format, pytest,
  workflow lint, frontend build, design audit all mirrored; docker build skipped,
  Docker is not on this machine).
- Bundle check (`frontend/out/_next/static/chunks/*.js` after `npm run build`):
  contains `begin_checkout`, `gbraid`, `wbraid`, `client_id`, `session_id`; contains
  no `"checkout_click"` — the exact set `scripts/check.py attribution` looks for.
- GA4 debug endpoint (`https://www.google-analytics.com/debug/mp/collect`, placeholder
  `api_secret`, per docs/verified.md MP-3): the real payload `Ga4Purchase` builds for
  an order carrying a PaymentIntent and both GA4 numbers returned
  `{"validationMessages": []}`. A negative control (deleted `transaction_id`) also
  came back clean, which is MP-7 — the debug endpoint checks structure, not a named
  event's required fields, so it does not replace `tests/test_ga4.py`.

**Not done, deliberately.** `work/queue/03-sale-to-visit.md` was not moved to
`work/done/` in this session's commit, to avoid a second push-triggered Cloud Run
deploy for a bookkeeping-only change (deploy.yml has no `paths-ignore`, so every push
to main runs the whole pipeline). Move it once this entry's evidence is accepted:
`git mv work/queue/03-sale-to-visit.md work/done/` and a `chore:` commit, matching the
pattern of `033f5b2` / `2364ec2`.

**Follow-ups.**
- `gclid`/`gbraid`/`wbraid` are stored on the order but not sent anywhere yet — a
  future Google Ads offline-conversion import (Data Manager API, docs/verified.md Gh)
  is the documented destination for them, not this task.
- MP-2b documents a 24-hour (session attribution) / same-business-day (User-ID)
  window for joining a server event to a browser session by `session_id`. Nothing
  enforces that window today: an order that sits in `generating` for longer than that
  (LEASE_SECONDS is 600s, so unlikely, but not impossible under repeated Cloud Tasks
  retries) would still send whatever `ga_session_id` it captured at checkout, now
  outside Google's documented join window. Not fixed here; flagging for whoever next
  reads GA4's server-session numbers and finds them inconsistent.

## 2026-09-20 (Claude Code) — task 05: robots.txt and sitemap.xml

`scripts/check.py robots` and `scripts/check.py sitemap` measured production red
before this task: no `/robots.txt`, no `/sitemap.xml`.

**What changed.**
- `frontend/src/app/robots.ts` (new): Next.js file-convention route, `export const
  dynamic = 'force-static'` (required on Next.js 16.3.5 — confirmed by trying the
  build without it first, which failed the static export). Allows `/`, disallows
  `/g/`, `/api/`, `/internal/`, `/recuperar/`, and states `Sitemap:
  https://studioface.app/sitemap.xml`.
- `frontend/src/app/sitemap.ts` (new): same `force-static` requirement. Lists the
  home page and the four legal pages (`/legal/aviso-legal/`, `/legal/privacidad/`,
  `/legal/terminos/`, `/legal/cookies/`).
- `app/main.py`: no change needed. The `StaticFiles` mount was already registered
  last ("so /api, /internal and /health win"), so any file the export produces at
  its root — including these two — is already served with no shadowing to fix.
- `tests/test_seo.py` (new): asserts against the real `frontend/out` export (skipped
  if it does not exist, same convention as `tests/test_footer_links.py`) that both
  files exist with the right content, and separately builds the FastAPI app with
  `static_dir=frontend/out` and proves `GET /robots.txt` and `GET /sitemap.xml`
  both return 200 through `TestClient`.
- `tests/test_source_scanners.py`: added `test_seo.py` to the exemption list for the
  raw-source-scan rule, same reason already recorded there for `test_footer_links.py`
  — it reads a built artefact, not product source carrying our own comments.

**Evidence.**
- Before: `.venv\Scripts\python.exe -m pytest tests/test_seo.py -v` — 6 failed (no
  `frontend/out/robots.txt`, no `frontend/out/sitemap.xml`, and the FastAPI app
  answered 404 for both).
- After: `.venv\Scripts\python.exe -m pytest tests/test_seo.py -v` — 6 passed.
- `.venv\Scripts\python.exe scripts\ci.py`: `CI MIRROR GATE: green in 42s` (703
  passed, 15 skipped).
- `.venv\Scripts\python.exe scripts\check.py robots`: GREEN, exit 0.
- `.venv\Scripts\python.exe scripts\check.py sitemap`: GREEN, exit 0.
- Deployed via GitOps (`git push origin main`, commit `47a2a8a`): GitHub Actions run
  `35517711576` (`emulator`, `ci`, `design`, `infra`, `deploy` all green, including
  "verify production from outside" and "lighthouse"). Cloud Run revision
  `studioface-api-00110-4wg`, serving 100% of traffic.

**Not done, deliberately.** `work/queue/05-robots-sitemap.md` was left in place —
moving it to `work/done/` was not part of this task's brief and the two renames
already staged for tasks 03/04 were left untouched per instruction, so this task
added no third rename to that same commit-in-waiting.

**Follow-ups.** None. Both `scripts/check.py robots` and `scripts/check.py sitemap`
are green against production; nothing deferred.

## 2026-09-20 (Claude Code) — task 06: the home page's <head>

`scripts/check.py head` measured production red before this task: no canonical link,
no `og:image`, no JSON-LD carrying the price.

**What changed.**
- `frontend/src/lib/config.ts`: added `SITE_URL = "https://studioface.app"`, the one
  place `metadataBase` and the JSON-LD's absolute URLs now come from, next to the
  existing `PRICE_EUR` this task reads for the JSON-LD offer price (no second
  hard-coded "19.99").
- `frontend/src/app/layout.tsx`: `metadata.metadataBase = new URL(SITE_URL)`, so every
  page's relative `og:image` and canonical resolve to an absolute
  `https://studioface.app/...` address — required by the Open Graph protocol.
- `frontend/src/app/page.tsx`: `export const metadata` with the exact title
  `Foto de perfil profesional con IA para LinkedIn y CV | StudioFace`, a 119-character
  description naming the price and the free preview, `alternates.canonical: "/"`,
  Open Graph (type website, es_ES, the share image at 1200x630) and a Twitter
  `summary_large_image` card. Two `application/ld+json` `<script>` tags — Product
  (offer price `PRICE_EUR.toFixed(2)`, EUR, InStock) and Organization — placed AFTER
  the visible sections rather than before them: putting them first serialised the
  price into the raw HTML ahead of the real hero photograph and broke
  `tests/test_hero.py`'s proof-before-price check, which reads the DOM as text and had
  no way to know a `<script type="application/ld+json">` block is invisible to a
  visitor. No `aggregateRating`, no `FAQPage` — neither is backed by a real review
  count or a machine-readable FAQ, and an unbacked one is what Google's rich-result
  spam policies act on. By the brief.
- `scripts/make_share_image.py` (new): Pillow (already a dependency —
  `scripts/align_muestras.py` uses it too, so no new one is added). Center-crops the
  two files `scripts/align_muestras.py` already cuts
  (`frontend/public/muestras/mujer-40-{antes,despues}-hero.jpg`) to 600x630 each,
  pastes them side by side into a 1200x630 canvas, and steps JPEG quality down until
  the file is under 200 KB. Generates nothing and calls no model, same rule as the
  script it reads from. Output committed at `frontend/public/share.jpg` (101,729
  bytes) rather than built at deploy time: this is a static export with
  `images.unoptimized`, so there is no image server to regenerate it from, and
  `og:image` needs one fixed URL a crawler fetches once.
- `app/main.py`: `CachedStatic` gained a third tier. `ONE_DAY = "public,
  max-age=86400"` for `/muestras/*` and `/share.jpg` — no hash in either filename, so
  not `IMMUTABLE` like `_next/static/**`, but a crawler fetches `og:image` once and a
  search engine re-crawls the page on its own schedule, so a full day of caching is
  free bandwidth. Previously both fell through to `REVALIDATE` (`no-cache`).

**Evidence.**
- Before: `.venv\Scripts\python.exe -m pytest tests/test_page_head.py
  tests/test_share_image.py -v` — collection error (no `scripts/make_share_image.py`)
  then, once the module existed but before the metadata/JSON-LD landed, 8 of 9
  `test_page_head.py` cases failed (title, description, canonical, og:image, twitter,
  Product, Organization, the check.py regex) against the already-built export.
- After: both files green — `12 passed` (`test_share_image.py` + the pre-existing
  cache-policy suite, now asserting `ONE_DAY` instead of `REVALIDATE` for `/muestras/*`
  and a new case for `/share.jpg`) and `9 passed` (`test_page_head.py`).
- Full suite: `.venv\Scripts\python.exe -m pytest -q` — `718 passed, 15 skipped`.
- `.venv\Scripts\python.exe scripts\ci.py` — `CI MIRROR GATE: green in 53s`, `DESIGN
  AUDIT: 0 P0, 0 P1, 0 P2 PASS`, `WORKFLOW LINT: ok`.
- Local mobile Lighthouse (performance only, `scripts/demo_server.py` serving the real
  app + this export, `npx lighthouse --form-factor=mobile --throttling-method=simulate
  --chrome-flags="--headless=new"`): three runs, 84 / 95 / 88 — noisy on this machine
  under `simulate` throttling (CLS held at 1.0/0 every run; LCP and TBT swung with
  background load, not with anything this task changed — `og:image` is a `<meta>`
  reference, not a resource the browser fetches on page load). No fixed regression to
  chase; recorded honestly rather than cherry-picked.
- `scripts/check.py head`, run locally against the exact regex it uses:
  `canonical link True`, `share image True`, `product data with the price True`.
  Production verification is the pending step below.

**Not done, deliberately.** `work/queue/06-page-head.md` was left in place, same
reasoning as task 05: moving it was not part of the brief, and the three renames
already staged for tasks 03/04/05 were left untouched per instruction.

**Follow-ups.**
- `scripts/check.py head` still needs to be run against production after this deploys
  — recorded below once the run finishes.
- Local Lighthouse variance (84-95) is worth a second look with the machine otherwise
  idle, though nothing in this task's diff should move LCP or TBT.

## 2026-09-20 (Claude Code) — task 07: logs

`app/entry.py`'s `build()` already called `configure_logging()` (fixed in `5d781f6` /
`2d9f21a`, before this task existed). This task adds the test that proves the wiring at
the composition root rather than only at the unit, and the production evidence that the
deployed container actually speaks JSON to stdout.

**What changed.**
- `tests/test_logging_configured.py` (new): builds the app through `app.entry.build()`
  with only its network boundaries faked (reuses the `built` fixture from
  `tests/test_entry_builds.py` — CLAUDE.md lesson 8, "production wiring counts" —
  instead of declaring the same Firestore/Storage/Stripe/Resend doubles a second time).
  Asserts the root logger carries the JSON-formatted handler `app/logs.py` installs
  (not just "any handler": pytest's own log-capture plugin attaches one to the root
  logger for every test regardless of the application, so that check alone would have
  passed even with `configure_logging()` never called — caught by temporarily disabling
  the call and watching the test fail, see below) and that its level is INFO or lower.
- `docs/audit/logs-2026-09-20.md` (new): one GET to `https://studioface.app/health`
  (read-only, no state change, no email) and the matching production log lines, found
  by `x-cloud-trace-context` and by timestamp.

**Evidence.**
- Red demonstration (`app/entry.py`'s `configure_logging()` call temporarily replaced
  with `pass`, then reverted — `git diff --stat app/entry.py` shows zero diff
  afterwards): `.venv\Scripts\python.exe -m pytest tests/test_logging_configured.py -v`
  — `2 failed` (`AssertionError: no JSON-formatted handler on the root logger after
  build()` and `AssertionError: root logger level 30 drops INFO lines`).
- After reverting: `.venv\Scripts\python.exe -m pytest tests/test_logging_configured.py -q`
  — `2 passed in 1.24s`.
- `.venv\Scripts\python.exe scripts\ci.py`: `CI MIRROR GATE: green in 45s` (720 passed,
  15 skipped).
- Production: `curl -s -i https://studioface.app/health` returned `200`,
  `x-cloud-trace-context: e0e5ddaeb0b036730769302ab70a7092`. The application's own
  stdout line for that same request (`gcloud logging read` on
  `run.googleapis.com/stdout`, `studioface-api`, `europe-west1`,
  `studio-face-fresh-start`): `jsonPayload.logger = "uvicorn.access"`,
  `jsonPayload.message = "169.254.169.126:47512 - \"GET /health HTTP/1.1\" 200"`,
  `severity = "INFO"`, timestamp 55ms after the request — revision
  `studioface-api-00111-9kx`. Cloud Run's separate platform request log for the same
  request (matched by `trace`) corroborates but is not itself evidence of application
  logging; both are pasted in full in `docs/audit/logs-2026-09-20.md`.
- `gcloud.cmd` from Git Bash failed on this command with `'C:\Program' is not
  recognized` (a known quoting problem invoking a `.cmd` with a space in its install
  path from MSYS bash) — ran the same `gcloud logging read` / `gcloud config
  get-value` commands from PowerShell instead, which worked cleanly. Noting this so
  the next agent does not waste time on the same bash failure.

**Not verified.** `/health`'s own route handler does not call `logger.info` (see
`app/main.py`) — the application-level line captured is uvicorn's access log, passed
through rather than suppressed by `configure_logging()`. That a *route's own*
`logger.info` reaches Cloud Run in production (as opposed to uvicorn's access log) was
not separately re-proven against production in this task; `tests/test_logging.py`
proves it at the unit level and was already green before this task.

## 2026-09-20 (Claude Code) — the day's close: shipped, mirrored, queue empty

All five remaining queue tasks ran as one subagent each, one branch each, and every one
moved to `work/done/` only after I ran its own check command myself and saw exit 0. The
five outside-in production checks are now all green, where four of five were red this
morning:

    robots          GREEN   (was 404 and three missing lines)
    sitemap         GREEN   (was 404)
    head            GREEN   (was no canonical, no og:image, no price data)
    attribution     GREEN   (was five missing keys and checkout_click still firing)
    gallery_hidden  GREEN   (was already green)

`scripts/verify_production.py`: all 18 links answered, 1 blocked by the Turnstile
challenge by design. Final deployed revision `studioface-api-00113-f7k`.

The public mirror is https://github.com/kevinleonj/studioface-v2-mirror — history-free,
no workflows, secrets and order identifiers redacted. This repository stays private.

Answered read-only from Firestore: order `cs_test_a1eehOBw…` carries
`wardrobe = 'camisa-azul'`, `style = 'corporativo'`. It is NOT empty, so the outfit
audit's explanation stands: the preview builds with `wardrobe=None` and asks for a navy
blazer, the four finals build with the stored value and ask for a light blue shirt.

## 2026-09-20 (Claude Code) — task 06: stripe mode visible

`/health` now names which Stripe mode is live, derived only from the configured key's
prefix, so the next task (07, the live switch) has a machine-checkable signal instead
of a guess about which key is loaded.

**What changed.**
- `app/config.py` (new function `stripe_mode(key)`): pure, no I/O. `sk_test_`/`rk_test_`
  prefixes answer `"test"`; `sk_live_`/`rk_live_` answer `"live"`; anything else
  (including empty) answers `"unknown"`. Never inspects anything past the prefix.
  Vendor fact already in `docs/verified.md` (2026-09-17 and 2026-09-18 entries, from
  https://docs.stripe.com/keys), so no new researcher pass was needed.
- `app/main.py`: `Deps` and `make_app` both gained a `stripe_mode: str = "unknown"`
  field/parameter. `GET /health` now answers
  `{"ok": ..., "killswitch": ..., "stripe_mode": ...}`.
- `app/entry.py`: `build()` derives `mode = stripe_mode(s.stripe_secret_key)` right
  after `Settings.from_env()`, logs it once (`logger.info("stripe_mode=%s", mode)`),
  and passes `stripe_mode=mode` into `make_app(...)`. Nothing else about the key is
  ever logged or returned.

**Evidence.**
- Before: `.venv\Scripts\python.exe -m pytest tests\test_stripe_mode.py` — collection
  error, `ImportError: cannot import name 'stripe_mode' from 'app.config'`.
  `tests\test_health.py` (updated to expect the new field) — `7 failed, 3 passed`,
  `TypeError: make_app() got an unexpected keyword argument 'stripe_mode'`.
  `tests\test_entry_builds.py`'s two new cases — both failed (no `stripe_mode` on the
  built `Deps`, no `"stripe_mode="` line from `app.entry`'s own logger).
- After: `tests\test_stripe_mode.py` — `6 passed` (includes the twin: a live prefix
  reports `live`, not a hard-coded `test`). `tests\test_health.py` — `10 passed`.
  `tests\test_entry_builds.py` — `6 passed`, including
  `test_health_reports_the_stripe_mode_from_the_configured_key` (reads `Deps` off a
  route closure — calling `GET /health` there would trip the fixture's Firestore
  double, which deliberately raises on any read) and
  `test_the_startup_log_states_the_stripe_mode_once` (a handler on `app.entry`'s own
  logger, unaffected by `configure_logging()` replacing the root logger's handlers).
- `.venv\Scripts\python.exe scripts\ci.py` — `CI MIRROR GATE: green in 40s`,
  730 passed, 15 skipped, `DESIGN AUDIT: 0 P0, 0 P1, 0 P2`.
- Deployed: GitHub Actions run 35536762619, all jobs green (`ci`, `emulator`, `design`,
  `infra`, `deploy`, including `verify production from outside`). Revision
  `studioface-api-00117-5jg`.
- Production: `curl https://studioface.app/health` ->
  `{"ok":true,"killswitch":false,"stripe_mode":"live"}` — matches this task's own
  prediction ("expected right after this deploy: live, because the newest secret
  version is already the live key while the price is still a test price, so checkout
  is broken until task 07 finishes"). `.venv\Scripts\python.exe scripts\check.py
  stripe_mode_reported` -> `GREEN`, exit 0. Startup log line confirmed in Cloud Run
  (`gcloud logging read`, `studioface-api-00117-5jg`): three `stripe_mode=live` lines,
  one per cold-started instance — "once at startup" holds per instance, as intended.

**Not done, deliberately.** Checkout itself is not fixed here — `stripe_live` (the
stricter check that wants exactly `live`) is a separate, later gate; today it also
reports GREEN, but only because the live key is already the newest secret version,
not because of anything this task changed. That mismatch (live key, test-mode price)
is task 07's problem, not this one's, and the task brief says "go straight on."

**Follow-ups.**
- Task 07 (`work/queue/07-live-switch.md`) is next: the price is still a test price
  under a live key, so checkout is broken in production right now. Nothing in this
  task masks that; `/health` reporting `live` honestly is what makes it visible.

## 2026-09-20 (Claude Code) — task 07b: the walk works again after the live switch

The live switch (task 07) made `stripe-secret-key`'s newest Secret Manager version the
live key. `scripts/run_funnel.py` read that secret at `"latest"`, so after the switch it
handed the walk a live key and its own guard correctly refused to run at all — the walk
was dead until pointed at the recorded test version.

**What changed (`scripts/run_funnel.py`).**
- New `STRIPE_TEST_KEY_VERSION = "4"`, the version `docs/stripe-test-objects.md` records
  as the test key immediately before the live one. `read_secret` now takes a `version`
  argument; `FROM_SECRET_MANAGER` maps each secret to `(env var, version)`, and only
  `stripe-secret-key` is pinned — `fal-key` stays at `"latest"` because fal has no
  live/test split.
- `stripe-webhook-secret` is no longer read from Secret Manager at all. Stripe can never
  reach `127.0.0.1`, so the walk has always signed and verified its own webhook; reading
  the now-rotated production signing secret served no purpose. `STRIPE_WEBHOOK_SECRET`
  is now minted per run with `secrets.token_hex(32)`, the same pattern
  `tests/e2e/funnel_app.py` already uses for the local Cloud Tasks token.
- The guard that refuses a live key (`sk_test_`/`rk_test_` prefix check) is unchanged and
  still runs after the pinned read, so a wrong or rotated version number is still caught.

**Test first.** `tests/test_walk_uses_test_key.py`, four cases: the pin is recorded in
the doc (empty), the pinned version is actually requested instead of `"latest"` (one),
two runs mint two distinct local webhook secrets and neither asks Secret Manager for the
webhook secret (many), the live-key guard still fires even if the pin were ever wrong
(failure).

    before: 3 failed, 1 passed (AttributeError: no STRIPE_TEST_KEY_VERSION; and
            stripe-webhook-secret still requested from Secret Manager)
    after:  4 passed

**Evidence.**
- `.venv\Scripts\python.exe scripts\ci.py` — green, 734 passed, 15 skipped,
  `DESIGN AUDIT: 0 P0, 0 P1, 0 P2`, ruff clean.
- Free half of the walk, for real: `scripts\run_funnel.py --serve-only` on
  `127.0.0.1:8099` (test key read at version 4, dummy Turnstile keys, local webhook
  secret), then `RUN_FUNNEL=1 pytest tests/e2e/test_funnel.py -v -s` (no
  `RUN_FUNNEL_PAID`) — `6 passed, 2 skipped in 21.90s`, the two skipped being the paid
  cases. No fal image was spent (the free half never calls fal) and no Stripe charge was
  made (the two paid cases never ran).
- Deployed revision unchanged by this task: `studioface-api-00117-5jg` (from task 06);
  this change touches only the local walk harness, not the deployed app, so no new
  deploy was expected or watched for this commit beyond the ordinary GitOps push.

**Operational note, repeated from the 20 Sep "paying half" entry above because it bit
again.** Stopping the server with a forceful process kill (`Stop-Process -Force`) skips
`run_funnel.py`'s `finally: rebuild_the_real_export()`, leaving `frontend/out` built with
Cloudflare's dummy site key. Caught this time before the gate ran again; rebuilt by hand
(`npm run build` in `frontend/`) and confirmed the dummy key string is absent from the
export before re-running `ci.py` green. `frontend/out` is git-ignored, so nothing was
ever at risk of being committed, but a stale poisoned export would have made the next
`ci.py` run's design/turnstile checks lie about what ships.

**Not done, deliberately.** The paid half of the walk was not run tonight — the brief
said not to, and nothing here changes what task 07's price/webhook migration still owes.

## 2026-09-21 (Claude Code) — task 09: favicon

The site was serving Next.js's default triangle favicon (md5
`c30c7d42707a47a3f4591831641e50dc`) and its five template SVGs (next.svg, vercel.svg,
globe.svg, window.svg, file.svg). Replaced with one StudioFace mark: the letter S in
Newsreader, ink (`#141312`) on paper (`#f2f1ed`), the two tokens `docs/DESIGN.md` already
names.

**What changed.**
- `scripts/make_favicon.py` (new, Pillow only — already a dependency, see
  `pyproject.toml`): draws the mark at 4x supersample then LANCZOS-downscales, so a 16px
  favicon is antialiased rather than blocky. Writes `frontend/src/app/favicon.ico`
  (sizes 16/32/48/256, saved RGBA — Turbopack's ICO decoder rejects an RGB PNG frame:
  "The PNG is not in RGBA format!", found only by actually running `next build`),
  `frontend/src/app/icon.svg`, and `frontend/src/app/apple-icon.png` (180x180) — the
  three places Next.js's file-based icon convention looks (`docs/verified.md` N1).
  Not wired into `scripts/ci.py`, same as `scripts/make_share_image.py`: a manual
  generation step, re-run only when the mark changes. It downloads the Newsreader
  variable font from Google's own font source repo on first run (no static instance
  exists — the live page loads the family through `next/font/google` at build time, not
  from a committed asset) and caches it under `.fonts-cache/` (gitignored, added to
  `.gitignore`) so a second run is offline. `docs/verified.md` N2 records the exact
  upstream file, the OFL 1.1 licence (same family/licence already declared in
  `docs/DESIGN.md`), and the font's two variation axes.
- `frontend/public/{next,vercel,globe,window,file}.svg` deleted.
- `scripts/demo_server.py`: `PLACEHOLDERS` pointed three of its four demo gallery
  thumbnails at the now-deleted SVGs. Repointed at the `muestras` "despues" (after)
  crops already shipped in the export — a better fit for "finished headshot" thumbnails
  than a vendor icon ever was, and no new asset needed.
- `tests/test_source_scanners.py`: added `test_favicon.py` to the comment-stripping
  meta-test's exempt set — it reads a generated SVG artefact (no comments to strip) and
  a plain Python list by membership, not product source prose.
- `docs/verified.md` N1 (Next.js file-based icon conventions, version-matched to our
  pinned `next@16.3.5`) and N2 (Newsreader's upstream source and licence) added before
  writing code, per the researcher-before-code rule.

**Test first.** `tests/test_favicon.py` (new), ten cases: before —
`ModuleNotFoundError: No module named 'make_favicon'` (collection error, nothing
existed yet); after — `10 passed`. Covers the committed favicon/icon/apple-icon files
(existence, path, not-the-default md5, all four ICO sizes present, SVG carries the
project tokens, PNG is square), the five deleted template files, `demo_server.py` no
longer pointing at a deleted or missing placeholder, and the pure `mark()` compositing
function using Pillow's built-in scalable font (`ImageFont.load_default(size=...)`) so
the unit tests need no network — only the real generation run does.

**Evidence.**
- Before: `.venv\Scripts\python.exe -m pytest tests\test_favicon.py -v` →
  `ImportError`/`ModuleNotFoundError: No module named 'make_favicon'`, 1 error, 0 passed.
- After: `10 passed in 0.60s`.
- `.venv\Scripts\python.exe scripts\ci.py` → `744 passed, 15 skipped`,
  `DESIGN AUDIT: 0 P0, 0 P1, 0 P2`, `CI MIRROR GATE: green in 44s`. (One fix needed to
  get there: `scripts/ci.py`'s frontend build step failed the first time with
  `Error: Processing image failed / unable to decode image data / The PNG is not in
  RGBA format!` — Turbopack decoding the 256px ICO frame Pillow had saved as RGB;
  converting to RGBA before save fixed it, confirmed by re-running the real
  `next build`, not guessed.)
- Production, before this task (read-only GET, no cost):
  `.venv\Scripts\python.exe scripts\check.py favicon` → 6 problems (`favicon is still
  the Next.js default triangle` plus all five template leftovers still serving 200).
- Pushed `git push origin main` (pre-push CI mirror gate green, `744 passed, 15
  skipped`). GitHub Actions run `35542331644`, all jobs green: `ci`, `emulator`,
  `design`, `infra`, `deploy` (including its `verify production from outside` step).
  Deployed revision `studioface-api-00123-bbk`, serving 100% of traffic.
- Production, after deploy: `.venv\Scripts\python.exe scripts\check.py favicon` →
  `GREEN`, exit 0.

**Not verified, deliberately left for a human to look at.** The mark's visual quality
(legibility of the S at 16px, whether the border weight reads well in an actual browser
tab) was checked here by rendering PNG previews and reading them as images, not by a
human eyeballing a live browser tab or a phone home-screen icon — no design-critic pass
was run over a single static asset outside a page, and the studioface-ui skill's
verification protocol is written for pages, not icons. If the mark reads wrong in an
actual tab, `scripts/make_favicon.py` is a five-minute re-run, not a rebuild.

## 2026-09-21 (Claude Code) — task 11: upload thumbnails

After choosing photos the visitor saw only a file name — no way to confirm it was the
right selfie without reopening the OS file dialog. `frontend/src/components/upload-form.tsx`
now shows a 64px square thumbnail per kept file (`object-cover`, `rounded-lg` — `--radius`
is 10px in `globals.css`, so that token already is the required 10px, no arbitrary value
needed), in a row (`data-sf-thumbs`) inside the dropzone, each with `alt="Foto elegida N"`.

**What changed.**
- Two small pure helpers, `extensionOf` and `isHeic`: Safari reports HEIC/HEIF files with
  that MIME type, Chromium reports the same files with an empty type but keeps the
  extension, so both are checked. Neither browser decodes HEIC into an `<img>`, so a HEIC
  file gets a labelled 64px tile (`role="img"`, the same alt text) showing its extension
  instead of a broken-image icon.
- One `useEffect` keyed on `files`: creates one `URL.createObjectURL` per non-HEIC file,
  and returns a single cleanup that revokes every one of them. That cleanup is not
  duplicated for "on change" versus "on unmount" — React's own contract is that the exact
  function an effect returns is what runs both when its dependency changes and when the
  owning component unmounts, so there is one code path to get right, not two.

**Whether every object URL is revoked on both change and unmount, and how it was proved.**
Proved for real, in a browser, for the "on change" half: `tests/test_upload_thumbnails.py`
serves a **copy** of the built `frontend/out` (verification protocol #1 — never the
directory itself), spies on `URL.createObjectURL`/`revokeObjectURL` from the page, uploads
two real sample photos (`frontend/public/muestras/*-despues.jpg`), confirms two URLs are
created and nothing is revoked yet, then uploads a different single file and asserts the
first two URLs are revoked before the wait times out. That is a real measurement, not a
read of the source.
"On unmount" was not driven separately with a real unmount, because this landing page never
conditionally unmounts `UploadForm` in production and forcing one would have meant adding
test-only harness code to the shipped component. What is proved instead, also for real: there
is exactly ONE `useEffect` governing the thumbnails and exactly ONE `return () => {...}`
inside it (`test_the_effect_has_one_cleanup_for_both_paths`), so the function proved to run
on change is, by construction, the only function React can also run at unmount — not a second,
untested implementation of the same idea. Browsers also release blob URLs on document unload
regardless (MDN), which is a second, independent net under the same case.

**Test first.**

    before: 7 failed, 3 passed  (data-sf-thumbs, isHeic, the effect, the cleanup: none exist)
    after:  10 passed

**Evidence.**
- `.venv\Scripts\python.exe scripts\ci.py` → `758 passed, 15 skipped`, ruff clean,
  `DESIGN AUDIT: 0 P0, 0 P1, 0 P2`, `CI MIRROR GATE: green in 61s`.
- Production before this task (read-only GET, no cost):
  `.venv\Scripts\python.exe scripts\check.py upload_thumbnails` → `RED   upload form
  shows no thumbnails (marker data-sf-thumbs absent)`, exit 1 — expected, nothing was
  deployed yet.
- No new dependency: `URL.createObjectURL`/`revokeObjectURL` are browser globals.
  `test_no_new_dependency_was_added` checks `package.json` for an added HEIC-decoding
  package; none was added.
- Design tokens: 64px is Tailwind's `size-16` (16 × 4px); 10px radius is `rounded-lg`,
  which `globals.css`'s `@theme` block points at `var(--radius)` = 10px on this page, not
  the Tailwind default — verified by reading `frontend/src/app/globals.css`, not assumed.

**Not done, deliberately.** No onError fallback for a non-HEIC file that fails to decode
for some other reason (a corrupt upload, say) — out of scope for this task, which asked
only for the HEIC case. `docs/CONVERSION.md` and `docs/DESIGN.md` are unchanged: this is a
micro-interaction inside an existing step, not a new hypothesis or a new token.

## 2026-09-21 (Claude Code) — task 10: the human check looks like the rest of the page

The Cloudflare Turnstile widget rendered dark, in English, and left-aligned on a light
Spanish page, because `turnstile.render()` never told it otherwise and fell back to its
own defaults.

**What changed.** `frontend/src/components/upload-form.tsx`: added `theme: "light"`,
`language: "es"`, `size: "flexible"` to the existing `turnstile.render()` options object.
Nothing else in that call changed — same `sitekey`, same `callback`/`error-callback`/
`expired-callback`, same widgetId ref, same mount effect, same F1 reset/getResponse poll.
Three keys documented at
developers.cloudflare.com/turnstile/get-started/client-side-rendering/widget-configurations
(verified through Context7, 20 Sep 2026).

**Failing test first.** New `tests/test_turnstile_look.py`: asserts the three options are
in the render() call, asserts the four pre-existing keys in that same call are untouched,
asserts the mount/reset machinery (`rendered.current`, `widgetId.current`,
`window.turnstile.reset(`, `getResponse`) was not restructured, and asserts the built
bundle really ships the three options (skipped if there is no build yet, the same pattern
`test_turnstile_reset.py` already uses).

    before: 2 failed, 2 passed (the two "did not restructure" guards already held; the
            three options did not exist yet)
    after:  4 passed (once frontend/out was rebuilt with the change)

**Evidence.**
- Production, before this task (read-only GET, no cost):
  `.venv\Scripts\python.exe scripts\check.py human_check_look` → 3 problems (`human check
  lacks light theme`, `lacks Spanish`, `lacks flexible width`).
- Free half of the browser walk, for real: `scripts\run_funnel.py --serve-only` on
  `127.0.0.1:8099` (test Stripe key, dummy Turnstile keys, local webhook secret), then
  `RUN_FUNNEL=1 pytest tests/e2e/test_funnel.py -v -s` (no `RUN_FUNNEL_PAID`) — `6 passed,
  2 skipped in 23.18s`, the two skipped being the paid cases. The walk's own output
  confirms the F1 reset path this task was told not to touch still works with the three
  new options in place: `TOKEN AFTER RESET IS DELIVERED BY: the render() callback
  re-fires`. No fal image was spent (the free half never calls fal) and no Stripe charge
  was made (the two paid cases never ran). The server was stopped gracefully
  (`taskkill /PID <pid>`, no `/F`), so `run_funnel.py`'s own `finally:
  rebuild_the_real_export()` ran and put the real Cloudflare site key back — confirmed by
  grepping the rebuilt export for the Cloudflare test site keys (none found) and for
  `flexible` (found, in the same `sitekey:...,theme:"light",language:"es",size:"flexible"`
  minified snippet that ships).
- `.venv\Scripts\python.exe scripts\ci.py` — green, `748 passed, 15 skipped`,
  `DESIGN AUDIT: 0 P0, 0 P1, 0 P2`, ruff clean.
- Pushed `git push origin main` (pre-push CI mirror gate first refused on a stale-export
  false alarm — `git checkout`/merge had touched `upload-form.tsx`'s mtime past the
  already-correct export's — fixed by rebuilding once by hand, then the gate was green and
  the push went through). GitHub Actions run `35558379294`, job `deploy`, green
  (`gh run watch 35558379294 --exit-status` confirms). Deployed revision
  `studioface-api-00124-chr`, serving 100% of traffic. `self-heal` correctly skipped
  (nothing to heal).
- Production, after deploy: `.venv\Scripts\python.exe scripts\check.py human_check_look`
  → `GREEN`, exit 0. Re-ran every other check.py entry immediately after
  (`stripe_live`, `favicon`, `robots`, `sitemap`, `head`, `attribution`,
  `gallery_hidden`) — all still `GREEN`; the three that were already red before this task
  (`redirect`, `upload_thumbnails`, `waiting_state`) are unrelated, unfinished queue items
  (`work/queue/11-upload-thumbnails.md`, `12-waiting-state.md`, `13-secure-forwarding.md`)
  and this task did not touch them.

**Not verified.** Whether the widget visually reads as intended in an actual browser
(colour contrast, RTL-safe centring at `flexible` width on a narrow phone) was checked
only through the compiled options object and the production bundle grep, not through a
design-critic screenshot pass — this task's brief was the three named options, not a
visual review.

## 2026-09-21 (Claude Code) — task 12: the wait shows a face, not an empty box

Both money-in-flight waits — the free preview's frame and the gallery's four frames
while a paid order generates — used to be an empty box. `sf-wait` (plain CSS in
`frontend/src/app/globals.css`, never a Tailwind arbitrary value, so
`scripts/check.py waiting_state` can find it in the stylesheet a GET of the home page
actually links) dims, blurs and slowly pulses the visitor's own first chosen photo on
the upload form; the gallery has no photo client-side (that page is opened fresh from a
link, nothing was ever uploaded in that browser), so the same class pulses the four
empty frames there instead.

**The one named exception, and only the one.** `sf-wait` loops and runs 2.4s a cycle —
both against the standing motion budget — because CLAUDE.md's brief for this task says
so explicitly: "A slow pulse is allowed; an unbounded spinner is not." Both exceptions
are pinned narrowly in `tests/test_motion.py` (`test_nothing_loops` now fails on any
`infinite` NOT attached to `sf-wait`; the 400ms ceiling test carries the same one-name
carve-out) so neither exception can be reused for anything else without the test
failing. Everything else about the budget is unchanged: opacity only (the static
`filter: blur() brightness()` sits outside the guard because dimming a photo is not
motion; only the pulse itself is gated), and the `animation` declaration lives ONLY
inside `@media (prefers-reduced-motion: no-preference)`, so under `reduce` there is no
animation on `.sf-wait` at all — proved by regex against the compiled rule
(`tests/test_waiting_state.py`), not merely read. `docs/DESIGN.md` documents it as a
sixth rule outside the five-row moment table, since it has no single trigger and is not
a "moment" — a held-out test (`test_every_moment_is_written_down_with_all_five_columns`)
still expects exactly five rows, unchanged.

**The timer line and focus behaviour are untouched.** `Generating`'s elapsed-seconds
counter, its `status.current?.focus()` on mount, and its `role="status"
aria-live="polite"` paragraph are byte-identical to before this task; only the empty
`<div className={FRAME} />` gained a conditional `<img>` fed `thumbs[0]?.url` (the same
blob URL O12 already creates for the upload-target thumbnails — one source of truth,
not a second decode). A HEIC first file has no decodable blob URL, so the frame falls
back to the old empty box rather than a broken image.

**Test first.**

    before: 6 failed, 2 passed (sf-wait: no CSS, no upload-form use, no gallery use;
            the two that already held — timer/focus, and Loading() left alone — passed)
    after:  8 passed

**Evidence.**
- `.venv\Scripts\python.exe scripts\ci.py` → `766 passed, 15 skipped`, ruff clean,
  `DESIGN AUDIT: 0 P0, 0 P1, 0 P2`, `CI MIRROR GATE: green in 47-62s`.
- Production, before this task (read-only GET, no cost):
  `.venv\Scripts\python.exe scripts\check.py waiting_state` → `RED   no designed
  waiting state (class sf-wait absent from the stylesheet)`, exit 1 — expected, nothing
  deployed yet.
- Pushed `git push origin main`. First attempt was refused by the pre-push gate on a
  stale-export false alarm — the same class of bug task 10 hit — `git checkout main` +
  `git merge --ff-only` touches the mtime of every changed `frontend/src` file past the
  export already built before the merge; a second `npm run build` after the merge fixed
  it and the second push went through. GitHub Actions run `35562647275`, all five jobs
  green (`emulator`, `ci`, `design`, `infra`, `deploy`), confirmed via
  `gh run view 35562647275 --exit-status` (exit 0). Deployed revision
  `studioface-api-00126-ctv`, serving 100% of traffic
  (`gcloud run deploy` log: "has been deployed and is serving 100 percent of traffic").
- Production, after deploy: `.venv\Scripts\python.exe scripts\check.py waiting_state` →
  `GREEN`, exit 0. Re-ran every other `check.py` entry immediately after: `stripe_live`,
  `favicon`, `robots`, `sitemap`, `head`, `attribution`, `gallery_hidden`,
  `human_check_look`, `upload_thumbnails` all still `GREEN`. `redirect` is still `RED`
  (307 instead of 301/308, `http://` instead of `https://` in the Location header) —
  unrelated, already red before this task per the 09-21 human-check-look entry above,
  and unchanged by anything touched here (`work/queue/13-secure-forwarding.md`).
- No purchase was made and no paid-walk test was run: `RUN_FUNNEL`/`RUN_FUNNEL_PAID`
  were never set, and production's `stripe_mode` reads `live` unchanged before and after
  (`stripe_live` GREEN both times). The `--- PREVIEW REQUEST ---`/`--- DELIVERED PHOTO
  ---` lines printed mid-`pytest` are `tests/`'s existing fake-fal-client logging (the
  pipeline unit tests print the request the fake would have received); no network call
  left this machine and no fal credit was spent by this task.

**Not verified, deliberately.** Whether the pulse and blur read well on an actual phone
screen (contrast of the "Foto N de 4" label once blurred, whether 2.4s reads as
"working" rather than sluggish) was checked only through compiled CSS and static
analysis, not a design-critic screenshot pass or a live browser walk — this task's
brief was the treatment and the motion-budget exception, not a visual review.

## 2026-09-21 (Claude Code) — task 13: secure forwarding

A bare directory address forwarded to `http://` and then back to `https://`, both
marked TEMPORARY. Measured on production before any change:

    GET https://studioface.app/legal/privacidad
    307 -> http://studioface.app/legal/privacidad/

Two independent causes, both root-caused before writing anything.

**Cause 1, the scheme.** Cloud Run terminates TLS itself and proxies the request to
the container as plain HTTP/1, naming the true scheme in `X-Forwarded-Proto`
(docs/verified.md 13b, Google's own container-contract and triggering/https-request
pages). uvicorn's `--proxy-headers` is already the CLI default, but the installed
source (`.venv/Lib/site-packages/uvicorn/middleware/proxy_headers.py`) only reads that
header from a connecting address inside `--forwarded-allow-ips`, which itself defaults
to `127.0.0.1,::1` (uvicorn's own docs/settings.md, docs/verified.md 13a) — never
Cloud Run's address — so the header was always parsed and then ignored, and
Starlette's own redirect code built its Location from the literal, plain-http
connection scheme.

**Cause 2, the status code.** Even with the right scheme, Starlette's `StaticFiles`
(serving the Next.js export) answers a bare directory path with a 307 by
construction (`starlette/staticfiles.py`) — TEMPORARY, so no browser or CDN may cache
it and every visit paid for the redirect again. The address always means the same
thing, so it needed to be a single 308 (permanent; kept over 301 because RFC 9110
15.4.9 guarantees the method/body replay unchanged, free here since this route only
ever serves GET/HEAD).

**What changed.**
- `Dockerfile` CMD: `--proxy-headers --forwarded-allow-ips='*'` added, single-quoted
  so `sh -c` never glob-expands the bare `*` against files in `/srv` (verified locally:
  `touch -- "--forwarded-allow-ips=zzz"` in a test directory, then the quoted form
  still printed the literal `*`, unquoted did not go untested because it was never
  shipped unquoted).
- `app/main.py`: `CachedStatic.get_response` (new) wraps `StaticFiles.get_response` —
  if the result is a `RedirectResponse` (Starlette's own directory-slash redirect,
  always 307), it is re-answered as a 308 to the same Location. Nothing else about
  `CachedStatic.file_response`'s cache-control logic changed.

**Vendor facts, docs/verified.md 13a/13b/13c, researcher agent, 21 Sep 2026.**
Confirmed: uvicorn's `--forwarded-allow-ips` default and `'*'`'s meaning (13a,
uvicorn's own docs/settings.md); Cloud Run terminates TLS before the container and
names `X-Forwarded-Proto` as the header carrying the real scheme (13b, two Cloud Run
doc pages). **Not confirmed, and recorded as such rather than guessed past:** no
Cloud Run page (checked container-contract, triggering/https-request,
securing/security, run/docs/issues) states that Cloud Run sets `X-Forwarded-For`, or
explicitly endorses trusting every connecting address. Using `'*'` is this session's
own inference from the ingress path Google does document (GFE -> HTTP proxy -> app
server, securing/security) — nothing else reaches this container — not a vendor
claim, and the Dockerfile comment says so rather than attributing it to Google.

**Test first**, `tests/test_secure_forwarding.py` (new, 6 cases).

    before: 4 failed, 2 passed (the two rate-limiter "confirm" cases already held —
            the leftmost-X-Forwarded-For-entry key was already correct and untouched;
            the Dockerfile had neither flag, and the redirect was still a 307)
    after:  6 passed

The two rate-limiter cases are a held-out confirmation, not a fix: they prove that
trusting the proxy for the *scheme* does not change which address `/api/preview`'s
ceiling counts against — a visitor forwarded through two different proxy hops is
still capped once (keyed on the leftmost, visitor, entry), and two different visitors
sharing one trailing hop are never merged into one counter. `_register_preview`'s
`x_forwarded_for.split(",")[0].strip()` reads the header itself and never touches
`request.client`, so this was already correct and is now pinned rather than assumed.

**Evidence.**
- `.venv\Scripts\python.exe -m pytest tests\test_secure_forwarding.py -v` — 4 failed
  before code changed, 6 passed after.
- `.venv\Scripts\python.exe scripts\ci.py` — green, `772 passed, 15 skipped`, ruff
  clean, `DESIGN AUDIT: 0 P0, 0 P1, 0 P2`, `CI MIRROR GATE: green in 46s`. No frontend
  files touched, so `npm ci`/frontend build were correctly skipped as unchanged.
- Production, before this task (read-only GET, no cost):
  `.venv\Scripts\python.exe scripts\check.py redirect` → 2 problems (`answers 307,
  wanted 301 or 308`; `forwards to 'http://...', wanted 'https://...'`), exit 1.
- Pushed `git push origin main`: the local `git commit` result and a concurrent
  process's push landed on the identical commit `54521e9` before this session's own
  push ran — the remote rejected it with "cannot lock ref ... is at 54521e9 but
  expected 7aefa25", which on inspection meant origin/main already equalled local
  main byte-for-byte (`git fetch` + `git rev-parse` both sides confirmed it), so no
  further push was made, per the standing instruction to check ancestry rather than
  force anything. GitHub Actions run `35566663397`, all five jobs green (`ci`,
  `design`, `emulator`, `infra`, `deploy`; `gh run view --json conclusion` ->
  `success` for every job). Deployed revision `studioface-api-00128-tdp`, serving
  100% of traffic.
- Production, after deploy: `.venv\Scripts\python.exe scripts\check.py redirect` →
  `GREEN`, exit 0. Raw check: `curl -sD - https://studioface.app/legal/privacidad` ->
  `HTTP/1.1 308 Permanent Redirect`, `location: https://studioface.app/legal/privacidad/`
  — one hop, straight to https, permanent. Re-ran every other `check.py` entry
  immediately after: `stripe_live`, `favicon`, `robots`, `sitemap`, `head`,
  `attribution`, `gallery_hidden`, `human_check_look`, `upload_thumbnails`,
  `waiting_state` — all `GREEN`.
- The rate limiter was not re-tested against production (no way to observe its
  Firestore-backed key from outside without spending preview/fal budget); confirmed
  at the unit level instead, in the same commit, against the real ASGI app that
  Cloud Run runs (`tests/test_secure_forwarding.py`'s two rate-limiter cases, both
  passing before and after this task's code changes, since `_register_preview`
  reads the `X-Forwarded-For` header itself and never touches `request.client`,
  which is the only thing `--forwarded-allow-ips='*'` changes).

## 2026-09-21 (Claude Code) — task 14: visitor address

Both rate-limit call sites keyed on `x_forwarded_for.split(",")[0].strip()` — the
FIRST entry of `X-Forwarded-For`, which is whatever the connecting client put in its
own request. A script can set that header itself and prepend a fresh fake address on
every call, so the per-visitor preview cap (and the `/api/recuperar` cap) could be
dodged entirely by rotating it.

**Fix.** One new function, `visitor_address(x_forwarded_for, request)` in
`app/main.py`, used by both call sites. `X-Forwarded-For` grows client-first
(`visitor, hop1, hop2, ...`); Google Front End (GFE) is the single hop between the
public internet and this container (docs/verified.md 13c: "GFE -> HTTP proxy -> app
server", the same ingress fact task 13 already researched — not re-researched here)
and, per the ordinary X-Forwarded-For convention, appends the address it actually
observed the connection from. So the LAST entry is the one no visitor can forge — they
can only pad the header with fake entries in front of it. An absent, empty, or
malformed header (e.g. a trailing comma leaving the last entry blank) falls back to
the raw socket peer, same as before this function existed. docs/verified.md 13c is
explicit that no Cloud Run page states outright that Cloud Run sets `X-Forwarded-For`;
using the trailing entry is this task's own inference from the documented single-hop
ingress path, not a vendor claim — no new vendor research was needed or done.

**Where the two call sites actually are.** The task brief's line numbers (301, 386)
predate tonight's other changes. They are now `_register_preview` (`app/main.py:341`,
inside the `/api/preview` route) and `_register_recovery` (`app/main.py:426`, inside
the `/api/recuperar` route) — found by what they do (both build the rate-limit key
from `x_forwarded_for`), not by line number.

**Task 13's own test pinned the bug.** `tests/test_secure_forwarding.py` had
`test_preview_rate_limit_keys_on_the_leftmost_forwarded_for_entry` and
`test_preview_rate_limit_does_not_key_on_the_proxy_hop`, which asserted the FIRST
entry was correct — the opposite of this task's fix. Both were corrected in place
(renamed to `..._trailing_forwarded_for_entry` and `..._a_shared_leading_entry`,
docstrings and IP roles swapped to match GFE's real single-hop ingress) rather than
left to fail or deleted; nothing else in that file changed.

**Test first**, `tests/test_visitor_address.py` (new, 9 cases: the pure function
directly — spoofed leading entry, trailing-entry-wins, single-entry, missing header,
malformed trailing comma, whitespace-only header, no socket peer either — plus two
through the real `/api/preview` route: a visitor cannot dodge the cap by prepending
addresses, and two real visitors sharing a spoofed leading entry are not merged).

    before: ImportError collecting the module (`visitor_address` did not exist)
    after:  9 passed

**Evidence.**
- `.venv\Scripts\python.exe -m pytest tests\test_visitor_address.py -q` — 9 passed
  (pasted in the task report).
- `.venv\Scripts\python.exe -m pytest tests/test_secure_forwarding.py tests/test_visitor_address.py tests/test_recuperar.py tests/test_guards_http.py -q`
  — 52 passed, confirming the corrected task-13 tests and every other consumer of
  `x-forwarded-for` (`test_recuperar.py`, `test_guards_http.py`, both single-value
  headers, unaffected by first-vs-last) still hold.
- `.venv\Scripts\python.exe scripts\ci.py` — green, `781 passed, 15 skipped`, ruff
  clean, `DESIGN AUDIT: 0 P0, 0 P1, 0 P2`, `CI MIRROR GATE: green in 47s`. No frontend
  files touched, so `npm ci`/frontend build were correctly skipped as unchanged. The
  `--- PREVIEW REQUEST ---`/`--- DELIVERED PHOTO ---` lines mid-pytest are the
  existing fake-fal-client test logging; no network call left this machine.
- Pushed `git push origin main`. Pre-push CI mirror gate ran again and was green
  (`781 passed, 15 skipped`, `CI MIRROR GATE: green in 47s`). GitHub Actions run
  `35567912904`, all five jobs green (`ci`, `emulator`, `design`, `infra`, `deploy`),
  confirmed via `gh run watch 35567912904 --exit-status` (exit 0). The deploy job log
  shows one `##[error]Process completed with exit code 1` annotation from the
  `lighthouse (alarm not gate)` step — that step runs with `continue-on-error` by
  design (it is an alarm, not a gate, per this file's own 16-17 Sep entries) and did
  not fail the job or the run. Deployed revision `studioface-api-00130-v5b`, serving
  100% of traffic (`gcloud run deploy` log: "has been deployed and is serving 100
  percent of traffic").
- Production, after deploy (read-only GETs, no cost, no email):
  `.venv\Scripts\python.exe scripts\check.py stripe_live` -> `GREEN` (still live,
  unchanged); `redirect`, `head`, `robots` -> all `GREEN`. No `check.py` entry
  exercises `/api/preview` or `/api/recuperar` directly, so this task's fix itself
  is proven by the unit/integration tests above, not by a further production probe;
  no purchase was made and no preview was posted against production.

**What happens at the edges, stated plainly.** Absent header (no proxy in front, or
a direct connection reaching the container some other way) or a malformed one (e.g.
a trailing comma leaving the trailing entry blank) both fall back to the raw socket
peer, exactly as the two call sites already did before this task for a totally empty
header — this task only changed which entry of a *present, multi-value* header is
trusted. A visitor cannot dodge the cap by prepending addresses: everything before
the last comma is visitor-supplied and now ignored for keying purposes; only the
entry GFE itself appends moves the counter.

**Not verified.** Whether GFE's real production behaviour actually appends exactly
one entry (never zero, never more than one) was not observed against a live request
with a hand-crafted spoofed header — docs/verified.md 13c already records that no
Cloud Run page confirms Cloud Run sets `X-Forwarded-For` at all, so this remains an
inference from the documented single-hop ingress path, as task 13 left it, not a
vendor-confirmed fact newly settled here.

## 2026-09-21 (Claude Code) — task 15: short ids in logs

Task 08's audit found a real production line that prints the full order id — which is
also the gallery's public id (the `/g/` link Cloud Tasks and the delivery email both
build with it) — in the clear:

    ga4 purchase sent order_id=cs_test_REDACTED
    value=19.99 status=204

Anyone who can read that Cloud Run log line can open that customer's gallery.
`id_prefix` (app/logs.py) already existed for exactly this and just was not used
everywhere.

**Test first**, `tests/test_log_ids.py` (new, 3 cases): scans every `.py` file under
`app/`, not only `app/adapters/ga4.py`, so a future `logger.info(..., order.id)`
cannot slip back in unnoticed. Comments are stripped first (tests/source_scan.py,
per the rule tests/test_source_scanners.py enforces) and, within each
`logger.<level>(...)` / `log_call(...)` call span, string literals are stripped too
(`strip_string_literals`, opt-in per that module's own docstring) — every offending
line's own format string literally contains the text `order_id=%s`, and without
stripping it the scanner would fire on its own label rather than the code argument
after it. The value leaked under three spellings in this codebase, all three
flagged unless wrapped in `id_prefix(...)`: the `Order.id` attribute, and the bare
`order_id` / `session_id` parameters that hold that same string in `app/entry.py`
(`enqueue`, `refund`) — Stripe's checkout session id IS this app's order id, read
straight from the call sites, not assumed. `order.ga_session_id` (GA4's own visitor
session id, a different value, never logged) and `SESSION_ID_PREFIX` correctly do
not match.

    before: 1 failed (10 hits across app/adapters/ga4.py, app/core.py, app/entry.py,
             app/main.py), 2 passed
    after:  3 passed

**Every hit found and fixed** (10 call-site arguments across 4 files, each wrapped
in `id_prefix(...)`; `app/logs.py` and `app/logs.py` import added to
`app/adapters/ga4.py` and `app/core.py`, already present in `app/entry.py` and
`app/main.py`):
- `app/adapters/ga4.py`: `_send`'s two log lines ("ga4 purchase sent", "ga4 purchase
  failed") and the "ga4 not configured" line — all three logged `order.id` bare.
- `app/core.py`: `Pipeline.run`'s "generation already claimed" line, and
  `Pipeline._refund`'s "refund FAILED" and "refund not confirmed" lines — all three
  logged `order.id` bare.
- `app/entry.py`: `_enqueue_factory`'s "enqueued" line and `_stripe_refund`'s "refund
  requested" line logged the bare `order_id` parameter (same full id, different
  local name); `FirestoreOrderStore.put`'s "order stored" line logged `order.id`
  bare.
- `app/main.py`: the Stripe refund webhook's "refund settled" line logged `order.id`
  bare.

Deliberately unchanged: `ga4.py`'s `_transaction_id` (never logs — derives GA4's
`transaction_id` from `order.payment_intent` or a `sha256` of `order.id`, exactly as
before) and `payload["client_id"]`. **The transaction id GA4 actually receives is
unaffected — only the log line shortens.** Also unchanged: every non-logging use of
the full `order.id` (Firestore document keys, the `/g/` gallery URL, the delivery
token, the Cloud Tasks URL, Stripe metadata) — id_prefix is a logging-only rule, and
truncating any of those would break the product.

**Evidence.**
- `.venv\Scripts\python.exe -m pytest tests/test_log_ids.py -q` — 3 passed (pasted in
  the task report).
- `.venv\Scripts\python.exe -m pytest -q` — 784 passed, 15 skipped (up from 781 passed
  before this task; +3 for the new test file, nothing else moved).
- `.venv\Scripts\python.exe scripts\ci.py` — green, ruff clean, `DESIGN AUDIT: 0 P0, 0
  P1, 0 P2`, `CI MIRROR GATE: green in 48s`. No frontend files touched, so `npm ci` /
  frontend build were correctly skipped as unchanged.
- Pushed `git push origin main` (merged fast-forward from `task/15-short-ids-in-logs`,
  commit `ae75726`). GitHub Actions run `35569719364`, all five jobs green (`ci`,
  `design`, `emulator`, `infra`, `deploy`; `gh run view --json conclusion` -> `success`).
  Deployed revision `studioface-api-00132-pb4`, serving 100% of traffic.

**Not verified.** Whether the shortened line actually appears twelve-characters-long
in a real Cloud Run log entry was not observed against a live purchase — production is
on live Stripe payments and this task made no purchase, per standing instruction. The
fix is proved at the unit level (this task's failing-then-passing test, run against the
exact literal `logger.info` call in `app/adapters/ga4.py`) and by the `id_prefix`
function itself, which is unchanged and already covered elsewhere in the suite.

## 2026-09-21 (Claude Code) — task 16: secret script on Windows

`scripts/set_secret.py` called `subprocess.run(["gcloud", ...])` directly. On this
Windows machine `gcloud` is really `gcloud.cmd`, and CreateProcess does not search
PATHEXT, so that call raised `WinError 2` even with `gcloud` on PATH — the same class
of bug `scripts/_exec.py` already exists to fix for `bootstrap.py` and others. Kevin
needs this script working to set the live Stripe secret key.

**The original file's second bug**: `name = sys.argv[1]` and
`value = getpass.getpass(...)` ran at module import time, not inside a function. That
made the module impossible to import for testing without also crashing on a missing
argv or blocking on a hidden prompt — a `main(argv)` function now holds all of it,
guarded by `if __name__ == "__main__":`.

**The fix**: argv[0] now goes through `_exec.resolve` (the same `shutil.which` fix
`bootstrap.py`, `scripts/go_live.py` and others already use) before
`subprocess.run`. `main()` catches the `FileNotFoundError` `resolve()` raises when
gcloud is missing and prints its message to stderr with exit code 127, instead of
letting a raw `WinError` traceback reach the terminal.

**Test first**, `tests/test_set_secret.py` (new, loads the module fresh via
`importlib.util.spec_from_file_location`, the same pattern `tests/test_bootstrap.py`
uses). Four cases plus cold start, this repo's own rule:
- cold start: importing the module runs no subprocess and asks for no secret —
  pins the second bug above so it cannot come back.
- one: a single secret is resolved and piped on stdin; the resolved executable is
  exactly what `shutil.which` returned, and the placeholder value never appears in
  argv or in anything printed to stdout.
- empty: an empty hidden prompt is still piped to gcloud, not silently dropped.
- many: three secrets set in sequence never mix up which value went with which name,
  and no placeholder value ever appears in any call's argv.
- failure: `shutil.which` returning `None` for `gcloud` must never let
  `subprocess.run` be reached with a bare `"gcloud"` — `main()` returns a non-zero
  exit code and prints a message containing "not on PATH", never "WinError".

Every test uses an obvious placeholder string (`PLACEHOLDER_VALUE`,
`PLACEHOLDER_ONE`/`TWO`/`THREE`), never a real-looking secret, and doubles
`subprocess.run` and `shutil.which` throughout — no test ever adds a real Secret
Manager version or shells out to a real `gcloud`.

    before: OSError (module-level getpass.getpass blocked on stdin under pytest's
             captured input) on all 5 collected tests
    after:  5 passed

**Evidence.**
- `.venv\Scripts\python.exe -m pytest tests/test_set_secret.py -q` — 5 passed
  (pasted in the task report).
- `.venv\Scripts\python.exe scripts\ci.py` — green, `789 passed, 15 skipped` (up
  from 784 before this task, +5 for the new test file), ruff clean,
  `DESIGN AUDIT: 0 P0, 0 P1, 0 P2`, `CI MIRROR GATE: green in 47s`. No frontend
  files touched, so `npm ci` / frontend build were correctly skipped as unchanged.
- Deploy: see the line appended immediately below this entry once the push has been
  watched to green.

**Never verified against a real secret, by design.** This task's own instruction is
that the value must never appear on a screen, in a log, in shell history, or in an
argv list — proving that with a real Stripe key would itself be the violation. No
test shells out to a real `gcloud`, no test adds a real Secret Manager version, and
the script was not run interactively against production during this task. The fix is
proved at the unit level, with `subprocess.run` and `shutil.which` always doubled.

## 2026-09-21 (Claude Code) — task 17: go-live rehearsal (audit of task 07)

Task 07 (live-switch) ran overnight. This task is the morning-after audit: run
`scripts/go_live.py --dry-run`, fix whatever in it still assumed the two-Terraform-
state-prefix plan docs/GO-LIVE.md explicitly withdrew before task 07 ran, record a
terraform plan and the fal balance, and write a plain-language purchase-and-refund
runbook for Kevin — surfacing two things from the live switch he did not yet know
about.

**go_live.py fix.** `check_live_prefix()` shelled out to `gcloud storage ls
gs://.../studioface-live/` and always reported "empty" — correctly, because nothing
ever wrote there; the design that would have used that prefix was withdrawn before
task 07 ran. Checking it was checking dead ground. Replaced with
`check_stripe_state()`: reads `terraform -chdir=infra state show
stripe_product.headshots` (a state READ against the GCS backend, no Stripe/Cloudflare
provider credentials needed, never touches the live key) and compares the tracked
product id against `CURRENT_LIVE_PRODUCT = "prod_VISvkPEoVJ3lPM"` — task 07's actual,
current, second-generation live product. This catches the failure mode that matters
now (state drifting back to an orphaned generation) instead of one that no longer can
happen. `tests/test_go_live.py` needed no changes; none of its 6 tests reference the
removed function or constants by name, and all 6 still pass.

**Terraform plan.** Could not run one from this machine: `infra/providers.tf`
configures the Stripe and Cloudflare providers from `STRIPE_API_KEY` /
`CLOUDFLARE_API_TOKEN` in the environment, and getting either onto this machine here
means reading a live secret's value, which both this task's rule and CLAUDE.md's
GitOps rule ("terraform apply is CI's alone... never touch secrets") forbid outside
CI. `terraform init` and `terraform state show <address>` do not need those
credentials (GCS-backend reads only) and both ran clean with none. Substituted the
real plan+apply CI already ran on the current HEAD (run `35570828196`, this morning):
`Plan: 0 to add, 1 to change, 0 to destroy` — the one change is
`google_cloud_run_v2_service.api`'s `client = "gcloud" -> null`, a known harmless
oscillation (the deploy job's own `gcloud run deploy` step stamps that annotation
after Terraform runs, so the next apply always reverts it) unrelated to Stripe and
recurring on every ordinary deploy. Zero Stripe resources changed. Full detail and
the state-show confirmation of which Stripe objects are tracked now:
`docs/audit/go-live-dry-run-2026-09-20.txt`.

**fal balance**, read-only GET to `https://rest.alpha.fal.ai/billing/user_balance`
(docs/verified.md, 2026-09-17), fal key held in memory only long enough to build the
Authorization header, never printed: **$5.8856 USD**. No generation ran in this task.

**Two findings written up for Kevin** in the new `docs/GO-LIVE-KEVIN.md`, not
previously documented anywhere he'd see them:
1. Task 07's very first deploy (task 05's push, ~20:24 UTC 20 Sep) hit the live API
   before task 07's state-rm ran, read "not found" as drift, and created a full
   orphaned FIRST generation of live Stripe objects (`prod_VISFzDNBbZzaQo`, prices
   ending `L23`/`DJYT`, webhook `we_..L33..`) minutes before task 07's real second
   generation (`prod_VISvkPEoVJ3lPM`, prices `...VfWNga0R`/`...xKS00M8J`, webhook
   `we_1UHrzY3SzksBW0B3DV4oNARv`) — confirmed as the one currently tracked, via
   `terraform state show`. The orphaned webhook is very likely still enabled in live
   Stripe, signed with a now-destroyed secret, so real payments will make it fail
   delivery, retry, and email Kevin a "webhook failing" notice. Checking whether it is
   actually still enabled needs the live Stripe API (`GET /v1/webhook_endpoints`),
   which needs the live secret key — not done here, per this task's rule never to read
   a secret value. `docs/GO-LIVE-KEVIN.md` gives Kevin the exact dashboard path
   (Developers -> Webhooks, the endpoint NOT ending `DV4oNARv`) to disable or delete it
   by hand, and states plainly that fulfilment is not at risk either way: the app
   answers unsigned/mis-signed webhook deliveries with 400 and also fulfils from the
   success redirect (`app/main.py`'s `_fulfil_session`, unit C2).
2. The pre-switch TEST-mode objects in `docs/stripe-test-objects.md` are orphaned on
   purpose (they let `docs/TEST-PURCHASE.md` be re-run later without touching real
   money) and must not be deleted — stated in `docs/GO-LIVE-KEVIN.md` so a future
   cleanup pass does not remove them.

**docs/GO-LIVE-KEVIN.md** also walks the one real purchase-and-refund rehearsal: what
the Stripe checkout address must start with (`https://checkout.stripe.com/c/pay/
cs_live_`, and what it means if it ever says `cs_test_` instead), the redirect and
delivery-email shape, the dashboard click-path to refund, which email confirms the
refund (Stripe's own, separate from the app's Resend delivery email), and the five
exact `logger.info` lines — read from `app/entry.py`, `app/core.py`,
`app/adapters/ga4.py` at the actual call sites, not from memory — that confirm the
payment notice arrived once and generation ran to `delivered` once: `order stored
...status=paid`, `enqueued...`, `order stored...status=generating`, `order
stored...status=delivered outputs=4`, `ga4 purchase sent...`.

**Evidence.**
- `.venv\Scripts\python.exe -m pytest tests/test_go_live.py -q` — 6 passed (unchanged
  by the fix; asserted before and after editing `check_stripe_state()` in).
- `.venv\Scripts\python.exe scripts\ci.py` — green, `789 passed, 15 skipped`, ruff
  clean, `DESIGN AUDIT: 0 P0, 0 P1, 0 P2`, `CI MIRROR GATE: green in 49s`.
- `.venv\Scripts\python.exe -c "import sys,pathlib; sys.exit(0 if 'READY:' in
  pathlib.Path('docs/audit/go-live-dry-run-2026-09-20.txt').read_text(encoding='utf-8')
  else 1)"` — exit 0.
- Pushed `git push origin main` (merged fast-forward from `task/17-go-live-rehearsal`).
  The pre-push CI mirror gate ran again and was green (`789 passed, 15 skipped`,
  `CI MIRROR GATE: green in 47s`). The first push attempt was blocked locally by the
  gitleaks pre-push hook, which correctly flagged the live webhook endpoint id quoted
  in `docs/audit/go-live-dry-run-2026-09-20.txt` as high-entropy (`generic-api-key`
  rule) — it is an object id, not the endpoint's signing secret, which this task never
  read or printed; allowlisted in `.gitleaksignore` with the id itself not spelled out
  in the comment, so the entry does not trip the same rule on itself. GitHub Actions
  run `35573392509`, all five jobs green (`ci`, `design`, `emulator`, `infra`,
  `deploy`; `gh run watch 35573392509 --exit-status` exit 0). Deployed revision
  `studioface-api-00135-tj8`, serving 100% of traffic. Production after deploy:
  `curl -s https://studioface.app/health` -> `{"ok":true,"killswitch":false,
  "stripe_mode":"live"}`.

**Not verified.** Whether the orphaned first-generation webhook endpoint is actually
still enabled in the live Stripe account — reading that needs the live secret key,
which this task's absolute rule forbids reading even to check a boolean. Left as an
explicit action item for Kevin in `docs/GO-LIVE-KEVIN.md`, with the exact dashboard
path. No purchase was made and nothing was refunded in this task; that is Kevin's
step, walked in the new document, not run here.
