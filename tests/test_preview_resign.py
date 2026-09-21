"""Task 30: preview-survives.

WHY: the preview handle lived only in the page's own React state. Reloading, or
coming back from Stripe's cancel redirect, threw it away, and with it the buy
button — read from app/entry.py's `_checkout_factory` (PRINT FIRST, 21 Sep):

    cancel_url=f"{s.public_url}/?cancelado=1"

That is the plain home page with one inert query parameter — `grep -rn cancelado
frontend/src` finds nothing that ever reads it — so Stripe's own cancel button lands
on a page that remounts from nothing, exactly like an ordinary reload. Losing the
handle there costs the visitor one of their three tries an hour for nothing.

The signed picture address dies in 15 minutes (GALLERY_TTL, app/adapters/gcs.py), so
surviving a reload needs a FRESH signed address for the SAME stored result, never a
new generation. GET /api/preview/{batch} does that: it checks batch/n/t with the
exact same `preview_token` comparison /api/checkout uses — not a re-implementation,
imported from app.core the same way app/main.py's checkout route does — and hands
back a fresh signed address, or 404 when there is none.

Both sides of the guard:
  1. a valid handle gets a fresh address
  2. a made-up signature gets 404 — never the real address, and never a different
     status code that would tell an attacker their guess was close
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import OrderStore, Pipeline, preview_token  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import make_app  # noqa: E402

APP_SECRET = "app_secret"


class OneStoredPreview:
    """resign_preview double: answers for exactly one batch, the way the real
    GCS-backed one (app/adapters/gcs.py's preview_resigner) only answers for a batch
    that actually has a stored previews/{batch}/preview.jpg object."""

    def __init__(self, batch: str, url: str) -> None:
        self.batch = batch
        self.url = url
        self.calls: list[str] = []

    def __call__(self, batch: str) -> str | None:
        self.calls.append(batch)
        return self.url if batch == self.batch else None


def build(resign=None):
    pipeline = Pipeline(
        store=OrderStore(),
        model=type("M", (), {"edit": lambda self, u, p: "x"})(),
        storage=type("S", (), {"put": lambda self, k, u: k})(),
        send_email=lambda t, b: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret=APP_SECRET,
    )
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter(), per_client=50, per_subnet=200),
        enqueue=lambda i: None,
        preview_fn=lambda files, batch: "https://cdn/preview.png",
        webhook_secret="whsec",
        tasks_token="tt",
        resign_preview=resign or (lambda batch: None),
    )
    return TestClient(app)


# ---------------------------------------------------------------- 1: the real thing works


def test_a_valid_handle_gets_a_fresh_address():
    batch, n = "batch-1", 2
    t = preview_token(batch, n, APP_SECRET)
    resign = OneStoredPreview(batch, "https://storage.googleapis.com/fresh-signed-url")
    c = build(resign=resign)

    r = c.get(f"/api/preview/{batch}", params={"n": n, "t": t})

    assert r.status_code == 200, r.text
    assert r.json()["preview_url"] == "https://storage.googleapis.com/fresh-signed-url"
    assert resign.calls == [batch], "must ask for the SAME batch the signature verified"


# ---------------------------------------------------------------- 2: the guard refuses


def test_a_made_up_signature_gets_404():
    batch, n = "batch-1", 2
    real_t = preview_token(batch, n, APP_SECRET)
    resign = OneStoredPreview(batch, "https://storage.googleapis.com/fresh-signed-url")
    c = build(resign=resign)

    r = c.get(f"/api/preview/{batch}", params={"n": n, "t": "not-the-real-signature"})
    assert r.status_code == 404
    assert resign.calls == [], "a bad signature must never even ask whether a preview is stored"

    # The batch and the count are both bound into the signature — a real signature
    # for a DIFFERENT count is just as made-up as a random string. Same shape as
    # tests/test_buy_at_limit.py's test_a_genuine_limited_handle_tampered_with_is_
    # still_refused, proving the checkout-side guard the same way.
    r2 = c.get(f"/api/preview/{batch}", params={"n": n + 1, "t": real_t})
    assert r2.status_code == 404


def test_an_unknown_batch_with_a_well_formed_signature_still_gets_404():
    """A signature can be internally consistent for a batch nothing was ever
    generated for — a store-only handle from the free-preview limit (task 29), which
    never calls the image model. This is the 404 the frontend's restore-on-load
    falls back on: buy button back, no picture promised."""
    batch, n = "never-generated", 1
    t = preview_token(batch, n, APP_SECRET)
    c = build(resign=lambda b: None)  # nothing was ever stored for any batch

    r = c.get(f"/api/preview/{batch}", params={"n": n, "t": t})
    assert r.status_code == 404


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
