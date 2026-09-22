# StudioFace v2 — rules for Claude Code

Read HANDOFF.md and GOAL.md first. Then the file you were asked to touch. Nothing else unless asked.

## What this is
AI headshot web app for Spain. One Cloud Run service (FastAPI), Firestore, two Cloud Storage
buckets, Cloud Tasks, fal.ai nano-banana-2/edit, Stripe Checkout, Resend, static React front.
Settled decisions live in docs/DECISIONS.md. Do not re-open them.

## Non-negotiables
- AUDIT THEN FIX. Print actual code with `cat -n <file>` and line numbers before proposing a change.
- Failing test first for every feature. `.venv\Scripts\python.exe scripts\ci.py` green before every commit. No exceptions.
- Secrets only via environment variables. Never read, print or write .env or SecretsDoNotEdit.
- No new dependency without one line of reason in the commit message and a yes from Kevin.
- No FastAPI BackgroundTasks for generation (Cloud Run throttles CPU after response). Use Cloud Tasks.
- Counters and idempotency live in Firestore (transactions), never in process memory (many instances).
- GitOps: push to main -> CI runs the gate, applies infra/ (Terraform), builds and deploys. You never deploy, never touch secrets, never run terraform apply. A red deploy starts self-heal.yml; if you are the healer, commit as `heal: ...`.
- Vendor facts go through the researcher agent (Context7) and into docs/verified.md before code.
- Every fal / Stripe / Google Cloud fact: verify with Context7 (fal: /websites/fal_ai) or the
  vendor page before writing code. Write the citation with today's date to docs/verified.md.
- Commands name one explicit absolute path. Unknown path => discovery command first.
- One commit per logical unit. `git add <named files>`, never `git add .`.
- Update HANDOFF.md at the end of every task: what changed, evidence, follow-ups.

## Clutter rules (enforced by `ruff` in pyproject.toml, complexity <= 8)
- No function over 40 lines. No file over 300 lines. Split before you exceed.
- No dead code, no commented-out code, no TODO without an issue number.
- No abstractions for one caller. No "utils.py". Name the file after the thing it does.
- Delete before you add. If a change removes more lines than it adds, that is the good sign.

## Definition of done (copy into every task report)
1. Failing test existed and now passes (paste the before/after pytest lines)
2. `.venv\Scripts\python.exe scripts\ci.py` output pasted, green
3. Runtime evidence pasted (curl output, screenshot path, or log line)
4. No secrets, no hard-coded client values
5. HANDOFF.md updated

## Lessons, 17 Sep 2026 (from two days of build mistakes)
1. Environment is fixed: Windows box, PowerShell, .venv in the repo. Never propose Mac, WSL or Git Bash.
2. Only commands that have been run and verified on this machine. Nothing typed from memory.
3. One interpreter: .venv\Scripts\python.exe. Never install into the global Python.
4. Pin the gate's tools (ruff, pytest, httpx, keyring). An unpinned gate is not a mirror of CI.
5. GitOps only: push to main is the sole deploy path. Push with exactly `git push origin main`, as its own command.
6. Nobody replaces a file another agent owns. Specs and diffs, never whole-file drops over live work.
7. Diagnose with the tool that decides before editing: /openapi.json for routes, revision logs, `curl -i`, `terraform plan`. No guessing.
8. Every fix starts with a failing test. Production wiring counts: entry.py must be exercised with only network boundaries faked.
9. Infra steps are idempotent and proven by `terraform plan` before apply. Secret versions are never added blindly.
10. When a step needs money, credentials or a console action, open "needs Kevin: <what>" with the exact command and move to the next item. Never idle waiting.
11. One worktree per task, never a shared checkout. Before starting task N, create
    `..\wt-N` (a sibling of this checkout, e.g. `C:\Users\KEVIN\dev\wt-40` next to
    `C:\Users\KEVIN\dev\studioface-v2`) on its own branch, and do every edit, test run,
    commit and push for that task inside it. The main checkout is for reading only
    while a task worktree is open. This is what stops two agents from switching
    branches under each other, landing a commit on the wrong branch, or racing a push
    — all three happened in one shared checkout on 20-21 Sep 2026 (see HANDOFF.md).
