"""Task 31: the gallery key must never travel in an address or a query string again.

Measured from outside, 21 September 2026: opening /g/?o=...&t=... sent the order
number and key to Google Analytics — even with cookies refused — and left both in the
query string of the address bar after load. `scripts/check_gallery_privacy.py` is the
outside-in proof of that and of the fix; this file is the in-repo, unit-level half:

1. the thank-you redirect (/api/gracias) now carries the key in a FRAGMENT, never a
   query — a fragment is a browser-only concept and is never sent to any server, so it
   cannot appear in a Referer, an access log, or an analytics request made by the page
   that receives it.
2. the server accepts the key from a request HEADER on the new route, held to the
   exact discipline the old path route already had: a good key is let through, a bad
   one is refused, and the two failures are indistinguishable.
3. the OLD route with the key in the path (`/api/orders/{order_id}/{token}`) still
   works, because it is what every link already sent to a customer's inbox calls —
   breaking it would strand real money already collected.
4. the recover-my-photos email produces the same fragment shape as the redirect.

Every guard gets its pair: one case that must be refused, one that must get through.
"""

import sys
import urllib.parse
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import GALLERY_BASE, Order, OrderStore, Pipeline, delivery_token  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import THANKS_PATH, make_app  # noqa: E402

APP_SECRET = "app_secret"
SESSION = "cs_test_a1b2c3d4e5"


def build(**overrides):
    store = OrderStore()
    emails: list[tuple[str, str]] = []
    pipeline = Pipeline(
        store=store,
        model=type("M", (), {"edit": lambda self, u, p: "https://fal/1.jpg"})(),
        storage=type("S", (), {"put": lambda self, k, u: f"gs://out/{k}"})(),
        send_email=lambda to, body: emails.append((to, body)),
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret=APP_SECRET,
    )
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter()),
        enqueue=lambda i: None,
        preview_fn=lambda files, batch: "",
        webhook_secret="whsec",
        tasks_token="tt",
        retrieve_session=lambda session_id: {
            "id": session_id,
            "payment_status": "paid",
            "customer_details": {"email": "k@example.com"},
            "metadata": {"source_urls": "gs://src/a.jpg", "style": "corporativo"},
            "amount_total": 1999,
        },
        sign_url=lambda url: f"https://signed/{url}",
        **overrides,
    )
    return TestClient(app, follow_redirects=False), store, emails


def paid_order(order_id=SESSION, status="paid", outputs=()):
    return Order(
        id=order_id,
        email="cliente@example.com",
        source_image_urls=["gs://src/previews/b/0.jpg"],
        style="corporativo",
        amount_cents=1999,
        status=status,
        outputs=list(outputs),
    )


# ---------------------------------------------------------------- 1. the redirect


def test_the_redirect_after_payment_carries_a_fragment_and_no_query():
    """The measured defect's first half: the old redirect put the key in a query, and
    a query is sent to every third party that ever sees the address."""
    c, _, _ = build()
    target = c.get(THANKS_PATH, params={"session_id": SESSION}).headers["location"]
    parsed = urllib.parse.urlparse(target)
    assert parsed.query == "", f"the redirect still carries a query string: {target}"
    assert parsed.fragment, f"the redirect carries no fragment at all: {target}"
    assert f"o={SESSION}" in parsed.fragment
    assert f"t={delivery_token(SESSION, APP_SECRET)}" in parsed.fragment
    assert target == f"{GALLERY_BASE}#o={SESSION}&t={delivery_token(SESSION, APP_SECRET)}"


# ---------------------------------------------------------------- 2. the header route


def _get(c, token: str):
    return c.get(f"/api/orders/{SESSION}", headers={"X-Gallery-Token": token})


def test_the_header_route_accepts_a_good_key():
    c, store, _ = build()
    store.put(paid_order(status="delivered", outputs=["gs://out/a.jpg"]))
    r = _get(c, delivery_token(SESSION, APP_SECRET))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "delivered"


def test_the_header_route_refuses_a_bad_key():
    c, store, _ = build()
    store.put(paid_order(status="delivered", outputs=["gs://out/a.jpg"]))
    r = _get(c, "deadbeefdeadbeefdeadbeefdeadbeef")
    assert r.status_code == 404
    assert r.json() == _get(c, "").json(), "a bad key and a missing key must answer identically"


# ---------------------------------------------------------------- 3. the old path route


def test_the_old_path_route_still_works_for_links_already_sent():
    """Links already in a customer's inbox call this shape. Breaking it strands money
    already collected, so it is never removed — only no longer produced."""
    c, store, _ = build()
    store.put(paid_order(status="delivered", outputs=["gs://out/a.jpg"]))
    token = delivery_token(SESSION, APP_SECRET)
    header_route = c.get(f"/api/orders/{SESSION}", headers={"X-Gallery-Token": token}).json()
    path_route = c.get(f"/api/orders/{SESSION}/{token}").json()
    assert (
        header_route
        == path_route
        == {
            "status": "delivered",
            "images": ["https://signed/gs://out/a.jpg"],
            "downloads": ["https://signed/gs://out/a.jpg"],
        }
    )


def test_the_old_path_route_still_refuses_a_bad_token():
    c, _, _ = build()
    assert c.get(f"/api/orders/{SESSION}/deadbeefdeadbeefdeadbeefdeadbeef").status_code == 404


# ---------------------------------------------------------------- 4. recover-my-photos


def test_recuperar_sends_a_fragment_link_too():
    c, store, emails = build()
    store.put(paid_order(status="delivered", outputs=["gs://out/a.jpg"]))
    r = c.post(
        "/api/recuperar",
        json={"email": "cliente@example.com"},
        headers={"x-forwarded-for": "9.9.9.9"},
    )
    assert r.status_code == 200
    to, body = emails[0]
    assert to == "cliente@example.com"
    token = delivery_token(SESSION, APP_SECRET)
    assert body == f"{GALLERY_BASE}#o={SESSION}&t={token}"
    assert "?" not in body, f"the recover email still carries a query string: {body}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
