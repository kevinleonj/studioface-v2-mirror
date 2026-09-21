"""Serve the built frontend against the real API, with one delivered order.

For screenshots and for clicking through the site without GCP: every StudioFace
module is real, only the network boundaries are doubles (see tests/test_money_path).
Gallery images point at files inside the static export, so the page renders with no
broken images and no console errors.

    .venv\\Scripts\\python.exe scripts\\demo_server.py [port]

The signing key is generated per run (or taken from DEMO_TOKEN_SECRET), so this file
contains no credential and the demo link from one run does not work against another.
Not imported by the application and not part of the deployed image.
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import Order, OrderStore, Pipeline, delivery_token  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import make_app  # noqa: E402

DEMO_ORDER = "cs_demo"
TOKEN_SECRET = os.environ.get("DEMO_TOKEN_SECRET") or secrets.token_hex(16)
# Task 09-favicon deleted the five Next.js template SVGs these used to point at.
# The muestras "despues" (after) crops are already shipped in the export and read
# as finished headshots, which fits this demo gallery better than a placeholder icon.
PLACEHOLDERS = [
    "/muestras/hombre-25-despues.jpg",
    "/muestras/hombre-30-despues.jpg",
    "/muestras/mujer-40-despues.jpg",
    "/muestras/mujer-40-despues-hero.jpg",
]


class DemoModel:
    def edit(self, image_urls: list[str], prompt: str) -> str:
        return PLACEHOLDERS[0]


class DemoStorage:
    def put(self, key: str, url: str) -> str:
        return f"gs://demo-out/{key}"


def _placeholder_for(uri: str) -> str:
    """gs://demo-out/cs_demo/2.jpg -> one of the svgs shipped in the export."""
    index = uri.rsplit("/", 1)[-1].split(".")[0]
    return PLACEHOLDERS[int(index) % len(PLACEHOLDERS)] if index.isdigit() else PLACEHOLDERS[0]


def build_demo_app(static_dir: Path):
    store = OrderStore()
    pipeline = Pipeline(
        store=store,
        model=DemoModel(),
        storage=DemoStorage(),
        send_email=lambda to, body: None,
        refund=lambda oid, cents: None,
        track_conversion=lambda order: None,
        secret=TOKEN_SECRET,
    )
    store.put(
        Order(
            id=DEMO_ORDER,
            email="demo@studioface.app",
            source_image_urls=["gs://demo-src/0.jpg"],
            style="corporativo",
            amount_cents=1999,
            status="delivered",
            outputs=[f"gs://demo-out/{DEMO_ORDER}/{i}.jpg" for i in range(4)],
        )
    )
    return make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter()),
        enqueue=lambda order_id: None,
        preview_fn=lambda files, batch: PLACEHOLDERS[0],
        webhook_secret="unused-in-the-demo",
        tasks_token="unused-in-the-demo",
        verify_turnstile=lambda token, ip: True,
        # Swap the signed URL for a file that exists in the export, so the gallery
        # renders real images instead of four broken ones.
        sign_url=_placeholder_for,
        create_checkout=lambda batch, n, style, gclid: "/?demo-checkout=1",
        static_dir=str(static_dir),
        # F8: the local harness keeps its documentation; production does not.
        docs=True,
    )


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8124
    static_dir = ROOT / "frontend" / "out"
    if not static_dir.is_dir():
        raise SystemExit(f"build the frontend first: no {static_dir}")
    token = delivery_token(DEMO_ORDER, TOKEN_SECRET)
    # Fragment, matching what the real redirect and emails produce (task 31) — a
    # fragment is never sent to any server, so it never reaches this demo's own logs.
    print(f"gallery: http://127.0.0.1:{port}/g/#o={DEMO_ORDER}&t={token}")
    uvicorn.run(build_demo_app(static_dir), host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
