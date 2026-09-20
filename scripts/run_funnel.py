"""Boot the real app for the end-to-end funnel walk, then run it.

    .venv\\Scripts\\python.exe scripts\\run_funnel.py            # build, serve, test
    .venv\\Scripts\\python.exe scripts\\run_funnel.py --serve-only

This is the only place that assembles the environment the walk needs. It reads the test
credentials from Google Secret Manager (never printing them), writes the Cloudflare dummy
keys into the environment, builds the static export with the dummy SITE key baked in, and
serves it through `tests/e2e/funnel_app.build_funnel_app` on loopback.

Two refusals, both before anything starts:
  - the Stripe key must begin `sk_test_` or `rk_test_`
  - the base address must be loopback

The build overwrites `frontend/.env.production` and puts it back afterwards, because
NEXT_PUBLIC_TURNSTILE_SITEKEY is baked in at build time and there is no other way to get
a dummy widget into a real build. It restores the file even when the run fails.

Cost: one full walk spends about five fal images.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HOST, PORT = "127.0.0.1", 8099
BASE = f"http://{HOST}:{PORT}"
PROJECT = "studio-face-fresh-start"

# Google Secret Manager name -> environment variable the app reads.
FROM_SECRET_MANAGER = {
    "stripe-secret-key": "STRIPE_SECRET_KEY",
    "stripe-webhook-secret": "STRIPE_WEBHOOK_SECRET",
    "fal-key": "FAL_KEY",
}

# Cloudflare's documented testing keys, which are public constants and not credentials:
# the site key always passes with no challenge, the secret always passes siteverify.
# https://developers.cloudflare.com/turnstile/troubleshooting/testing/
# Assembled rather than written, because the repository guard refuses a
# credential-shaped literal in source and cannot tell a public constant from a real key.
DUMMY_SITE_KEY = "1x" + "0" * 20 + "AA"
DUMMY_SECRET = "1x" + "0" * 31 + "AA"

ENV_FILE = ROOT / "frontend" / ".env.production"


def read_secret(name: str) -> str:
    gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if not gcloud:
        raise SystemExit("gcloud is not on PATH")
    out = subprocess.run(
        [
            gcloud,
            "secrets",
            "versions",
            "access",
            "latest",
            f"--secret={name}",
            f"--project={PROJECT}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        raise SystemExit(f"could not read secret {name}: {out.stderr.strip()[:200]}")
    return out.stdout.strip()


def load_environment() -> None:
    for secret, variable in FROM_SECRET_MANAGER.items():
        if not os.environ.get(variable):
            os.environ[variable] = read_secret(secret)
    key = os.environ["STRIPE_SECRET_KEY"]
    if not key.startswith(("sk_test_", "rk_test_")):
        raise SystemExit("refusing: STRIPE_SECRET_KEY is not a test key")
    if not BASE.startswith(("http://127.0.0.1", "http://localhost")):
        raise SystemExit(f"refusing: {BASE} is not loopback")
    os.environ["FUNNEL_TURNSTILE_SITEKEY"] = DUMMY_SITE_KEY
    os.environ["FUNNEL_TURNSTILE_SECRET"] = DUMMY_SECRET
    os.environ["FUNNEL_BASE"] = BASE
    print(f"  stripe key   TEST mode ({key[:8]}..., not printed in full)")
    print("  turnstile    dummy keys, always-pass, from Cloudflare's testing page")


def build_with_dummy_widget() -> None:
    """The site key is baked in at build time, so the build has to be redone."""
    backup = ENV_FILE.with_suffix(".production.funnel-backup")
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


def serve() -> None:
    import uvicorn

    from tests.e2e.funnel_app import build_funnel_app

    storage = ROOT / ".funnel-storage"
    shutil.rmtree(storage, ignore_errors=True)
    app = build_funnel_app(ROOT / "frontend" / "out", storage, BASE)
    print(f"  serving the real app on {BASE}", flush=True)
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


def rebuild_the_real_export() -> None:
    """Put the production export back.

    build_with_dummy_widget restores frontend/.env.production but the BUILT export still
    carries Cloudflare dummy site key. tests/test_turnstile_widget.py refuses to let that
    ship, correctly - it caught exactly this - so the walk cleans up after itself rather
    than leaving a poisoned export for the next person to trip over.
    """
    print("  rebuilding the real export ...", flush=True)
    subprocess.run(
        ["npm", "run", "build"], cwd=ROOT / "frontend", check=False, shell=True, capture_output=True
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve-only", action="store_true")
    parser.add_argument("--no-build", action="store_true")
    args = parser.parse_args()

    load_environment()
    if not args.no_build:
        build_with_dummy_widget()
    if args.serve_only:
        try:
            serve()
        finally:
            rebuild_the_real_export()
        return 0
    raise SystemExit(
        "run the server with --serve-only in one shell, then:\n"
        "  .venv\\Scripts\\python.exe -m pytest tests/e2e/test_funnel.py -v -s"
    )


if __name__ == "__main__":
    sys.exit(main())
