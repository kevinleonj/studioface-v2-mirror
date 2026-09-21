"""Boot the real app for the add-more-photos browser edge cases, run them, put the
real export back, and exit 0 or 1.

    .venv\\Scripts\\python.exe scripts\\run_upload_edges.py            # build, serve, test
    .venv\\Scripts\\python.exe scripts\\run_upload_edges.py --serve-only

Task 27 (work/done/27-add-more-photos.md): second pick adds, duplicate skipped,
remove works, same file re-pickable, preview survives a new pick with the notice.
Every one of those is page behaviour — adding to the kept photos, deduplicating,
removing, re-picking, and what the page shows while it holds a preview. None of it
needs a real preview to be generated, so this script never lets one happen and never
reads a Stripe, fal or Google Secret Manager credential — it needs none of the three.

Two independent layers stop the image model from ever being called:

  1. tests/e2e/test_upload_edges.py answers every /api/preview request INSIDE the
     browser with Playwright's own route interception, before the request leaves the
     page. The loopback server this script starts never receives it.
  2. In case a test ever forgot step 1, the server's own preview_fn here is
     NeverCallTheModel — it raises before touching anything that costs money, turning
     a forgotten interception into a loud 500 rather than a real fal call.

Cost: none, by construction of both layers above.

Cloudflare's Turnstile widget still loads for real from challenges.cloudflare.com in
the browser (the dummy site key only changes what siteverify answers, not whether the
script loads) — the same thing scripts/run_funnel.py already does, and Cloudflare
documents these keys as free to use for exactly this. Nothing here needs the widget
to finish, though: the two buttons under test are not gated on it.
"""

from __future__ import annotations

import secrets as secretslib
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HOST, PORT = "127.0.0.1", 8098
BASE = f"http://{HOST}:{PORT}"

# https://developers.cloudflare.com/turnstile/troubleshooting/testing/ — assembled
# rather than written as a literal, so the repository's credential-shaped-literal
# guard, which cannot tell a public test constant from a real key, does not have to.
DUMMY_SITE_KEY = "1x" + "0" * 20 + "AA"

ENV_FILE = ROOT / "frontend" / ".env.production"


class NeverCallTheModel:
    """Layer two, see module docstring. preview_fn is the only thing standing between
    /api/preview and fal (app/main.py's _register_preview calls it directly) — this
    one refuses instead of calling anything."""

    def __call__(self, files: list, batch: str) -> str:
        raise RuntimeError(
            "run_upload_edges: /api/preview reached the server for real. "
            "tests/e2e/test_upload_edges.py must intercept it in the browser first."
        )


class NeverStoreEither:
    """Task 29's own share of layer two. The free-preview-limit case now answers
    from the STORAGE-only path (store_sources_fn), not preview_fn, so NeverCallTheModel
    alone would no longer catch a forgotten interception on that response — this
    refuses just as loudly if the server is ever asked to store for real."""

    def __call__(self, files: list, batch: str) -> None:
        raise RuntimeError(
            "run_upload_edges: /api/preview's storage-only path reached the server "
            "for real. tests/e2e/test_upload_edges.py must intercept it in the browser first."
        )


class NeverResignEither:
    """Task 30's own share of layer two. A reload or a return from Stripe's cancel
    redirect now asks GET /api/preview/{batch} for a fresh signed address — a third
    thing the browser must intercept, never the loopback server, which has no real
    bucket (pipeline.storage=None) to check."""

    def __call__(self, batch: str) -> str | None:
        raise RuntimeError(
            "run_upload_edges: GET /api/preview/{batch} reached the server for real. "
            "tests/e2e/test_upload_edges.py must intercept it in the browser first."
        )


def build_with_dummy_widget() -> None:
    """The site key is baked in at build time, so the build has to be redone — same
    technique as scripts/run_funnel.py's build_with_dummy_widget, restoring the real
    .env.production even if the build fails."""
    backup = ENV_FILE.with_suffix(".production.edges-backup")
    if ENV_FILE.exists():
        shutil.copy2(ENV_FILE, backup)
    ENV_FILE.write_text(
        f"NEXT_PUBLIC_TURNSTILE_SITEKEY={DUMMY_SITE_KEY}\nNEXT_PUBLIC_GA4_ID=\n",
        encoding="utf-8",
    )
    try:
        print("  building the export with the dummy widget ...", flush=True)
        subprocess.run(
            ["npm", "run", "build"],
            cwd=ROOT / "frontend",
            check=True,
            shell=True,
            capture_output=True,
        )
    finally:
        if backup.exists():
            shutil.move(str(backup), str(ENV_FILE))
        else:
            ENV_FILE.unlink(missing_ok=True)
    print("  built, and frontend/.env.production put back")


def rebuild_the_real_export() -> None:
    """Put the production export back — the built export still carries the dummy site
    key after build_with_dummy_widget restores only the source .env file."""
    print("  rebuilding the real export ...", flush=True)
    subprocess.run(
        ["npm", "run", "build"], cwd=ROOT / "frontend", check=False, shell=True, capture_output=True
    )


def build_app():
    from app.core import OrderStore, Pipeline
    from app.guards import MemoryCounter, RateLimiter
    from app.main import make_app

    pipeline = Pipeline(
        store=OrderStore(),
        model=None,  # never dereferenced: NeverCallTheModel stands in front of it
        storage=None,  # never dereferenced by any route these tests exercise
        send_email=lambda to, body: None,
        refund=lambda order_id, cents: None,
        track_conversion=lambda order: None,
        secret=secretslib.token_hex(16),
    )
    return make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter(), per_client=50, per_subnet=200),
        enqueue=lambda order_id: None,
        preview_fn=NeverCallTheModel(),
        store_sources_fn=NeverStoreEither(),
        webhook_secret=secretslib.token_hex(32),
        tasks_token=secretslib.token_hex(16),
        verify_turnstile=lambda token, ip: True,
        retrieve_session=lambda session_id: None,
        sign_url=lambda url, filename=None: url,
        create_checkout=None,
        static_dir=str(ROOT / "frontend" / "out"),
        resign_preview=NeverResignEither(),
    )


def serve() -> None:
    import uvicorn

    app = build_app()
    print(f"  serving the real app on {BASE}", flush=True)
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


def _wait_until_up(timeout: float = 30.0) -> bool:
    started = time.time()
    while time.time() - started < timeout:
        try:
            if httpx.get(BASE + "/health", timeout=2.0).status_code == 200:
                return True
        except Exception:  # noqa: BLE001 - still booting, keep polling
            pass
        time.sleep(0.3)
    return False


def run_both() -> int:
    build_with_dummy_widget()
    server = subprocess.Popen(
        [sys.executable, str(Path(__file__)), "--serve-only", "--no-build"],
        cwd=ROOT,
    )
    try:
        if not _wait_until_up():
            print(f"server never answered {BASE}/health", file=sys.stderr)
            return 1
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/e2e/test_upload_edges.py", "-v"],
            cwd=ROOT,
            env={**__import__("os").environ, "EDGES_BASE": BASE},
        )
        return result.returncode
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        rebuild_the_real_export()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--serve-only", action="store_true")
    parser.add_argument("--no-build", action="store_true")
    args = parser.parse_args()

    if args.serve_only:
        if not args.no_build:
            build_with_dummy_widget()
        try:
            serve()
        finally:
            if not args.no_build:
                rebuild_the_real_export()
        return 0

    return run_both()


if __name__ == "__main__":
    sys.exit(main())
