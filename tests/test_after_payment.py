"""The ninety seconds after the customer pays.

Two defects live here, and both of them are invisible to every other test in this
suite because nothing exercised the link Stripe actually sends the browser to.

1. The success_url was f"{public_url}/g/?o={CHECKOUT_SESSION_ID}" — order id only.
   The gallery needs ?o= AND ?t=, the HMAC delivery token, and refuses outright
   without it (frontend/src/app/g/page.tsx: `if (!order || !token) notfound`). So
   every paying customer was redirected straight to "Este enlace no es válido o ha
   caducado." The working link existed only in the delivery email. Stripe can only
   substitute {CHECKOUT_SESSION_ID}, and the token is an HMAC over the app secret,
   so the redirect has to land on us first and we mint the token.

2. Even with the token, the gallery latched onto "notfound": the status endpoint
   404s when the order is missing, and the order is missing for the few seconds
   between Stripe's redirect and the webhook. A 404 is the browser's signal that a
   link is forged, and it is permanent — the poller stops. The token is verifiable
   without the order, so an unknown order under a GOOD token is "pending", not gone.
"""

import sys
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
        # /api/gracias asks Stripe whether the session was paid (U2). This file tests the
        # REDIRECT and the token it carries, not the payment check, so it presents a
        # session Stripe confirms; the check itself is
        # tests/test_gracias_verifies_payment.py.
        # Unit C2 made /api/gracias fulfil as well as redirect, so the fake session
        # now has to look like a real one: our own checkout always sets metadata,
        # and a session without it is not a shape Stripe can hand us.
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


# ---------------------------------------------------------------- the redirect


def test_the_redirect_after_payment_carries_a_token_the_gallery_accepts():
    """The defect itself: without t= the gallery renders "enlace no válido"."""
    c, _, _ = build()
    r = c.get(THANKS_PATH, params={"session_id": SESSION})
    assert r.status_code == 302
    target = r.headers["location"]
    assert target.startswith(GALLERY_BASE)
    assert f"o={SESSION}" in target
    assert f"t={delivery_token(SESSION, APP_SECRET)}" in target


def test_a_local_composition_root_can_point_the_gallery_at_itself():
    """20 September, the paid walk: a real browser was redirected to
    https://studioface.app/g/ holding an order that existed only on 127.0.0.1, and
    polled production for the full ten minutes before the walk gave up
    (docs/audit/paid-walk-2026-09-20.txt). GALLERY_BASE was a module constant, so no
    composition root could say otherwise - not the walk, and not any future one."""
    local = "http://127.0.0.1:8099/g/"
    c, _, _ = build(gallery_base=local)
    r = c.get(THANKS_PATH, params={"session_id": SESSION})
    assert r.status_code == 302
    assert r.headers["location"].startswith(local), r.headers["location"]


def test_the_redirect_target_is_the_link_the_delivery_email_sends():
    """Held-out check: two code paths mint the same gallery link — this redirect and
    Pipeline.run's email. If they ever disagree, one of them is a dead link."""
    c, store, emails = build()
    store.put(paid_order())
    c.post("/internal/generate/" + SESSION, headers={"X-Tasks-Token": "tt"})
    redirect = c.get(THANKS_PATH, params={"session_id": SESSION}).headers["location"]
    assert emails and emails[0][1] == redirect


def test_the_thank_you_route_refuses_anything_that_is_not_a_checkout_session():
    """It mints an HMAC for whatever it is handed, so it is an oracle. Confining it
    to cs_ ids keeps it exactly as wide as the order namespace and no wider."""
    c, _, _ = build()
    for bad in ("", "../etc", "o9", "sk_live_pretend"):
        assert c.get(THANKS_PATH, params={"session_id": bad}).status_code == 404


# ---------------------------------------------------------------- the race


def test_polling_before_the_webhook_lands_is_now_a_404_and_the_client_absorbs_it():
    """This asserted `200 pending` until 19 September, and the reason was sound: Stripe
    redirects faster than it delivers the webhook, so for a few seconds a good link points
    at an order that does not exist and a 404 stopped the poller for good.

    It was also how somebody who never paid saw an endless pending gallery, because
    /api/gracias handed out valid tokens for invented ids (U2).

    The contract changed rather than the reason going away: the server says what is true,
    and /g/ polls through 404s for NOTFOUND_GRACE_MS before believing one. The race is
    handled where it belongs, in the client that knows when it started asking."""
    c, _, _ = build()
    r = c.get(f"/api/orders/{SESSION}/{delivery_token(SESSION, APP_SECRET)}")
    assert r.status_code == 404, r.text


def test_a_forged_token_is_still_404_whether_or_not_the_order_exists():
    c, store, _ = build()
    assert c.get(f"/api/orders/{SESSION}/deadbeef").status_code == 404
    store.put(paid_order())
    assert c.get(f"/api/orders/{SESSION}/deadbeef").status_code == 404


def test_a_delivered_order_still_returns_its_signed_images():
    """Regression guard on the change above: the happy path must be untouched."""
    c, store, _ = build()
    store.put(paid_order(status="delivered", outputs=["gs://out/a.jpg"]))
    r = c.get(f"/api/orders/{SESSION}/{delivery_token(SESSION, APP_SECRET)}")
    # F3 added `downloads`. This fixture signs with a ONE-argument lambda, so the
    # route degrades to the display address rather than crashing - which is the
    # behaviour the held-out test in tests/test_download.py pins.
    assert r.json() == {
        "status": "delivered",
        "images": ["https://signed/gs://out/a.jpg"],
        "downloads": ["https://signed/gs://out/a.jpg"],
    }


def test_an_order_that_is_still_generating_reports_no_images():
    c, store, _ = build()
    store.put(paid_order(status="generating"))
    r = c.get(f"/api/orders/{SESSION}/{delivery_token(SESSION, APP_SECRET)}")
    assert r.json() == {"status": "generating", "images": [], "downloads": []}


# ---------------------------------------------------------------- what Stripe is told


class FakeSession:
    created: dict = {}

    @classmethod
    def create(cls, **kwargs):
        cls.created = kwargs
        return type("S", (), {"url": "https://checkout.stripe.com/c/pay/cs_test_x"})()


def fake_stripe():
    mod = type("stripe", (), {})()
    mod.api_key = None
    mod.checkout = type("checkout", (), {"Session": FakeSession})()
    return mod


def test_the_stripe_success_url_points_at_the_thank_you_route(monkeypatch):
    """The other half of defect 1, at the only place that decides it. Nothing tested
    _checkout_factory at all, which is how a success_url with no token shipped."""
    from app.config import Settings

    monkeypatch.setitem(sys.modules, "stripe", fake_stripe())
    from app import entry

    env = {
        "GCP_PROJECT": "sf",
        "GCP_REGION": "europe-west1",
        "PUBLIC_URL": "https://studioface.app",
        "BUCKET_SRC": "sf-src",
        "BUCKET_OUT": "sf-out",
        "TASKS_QUEUE": "generate",
        "TASKS_TOKEN": "tt",
        "APP_TOKEN_SECRET": APP_SECRET,
        "STRIPE_SECRET_KEY": "sk_test_x",
        "STRIPE_WEBHOOK_SECRET": "whsec_x",
        "RESEND_API_KEY": "re_x",
        "TURNSTILE_SECRET": "0x-secret",
        "STRIPE_PRICE_EUR": "price_123",
    }
    entry._checkout_factory(Settings.from_env(env))("batch1", 2, "corporativo", None)
    success = FakeSession.created["success_url"]
    assert success == f"https://studioface.app{THANKS_PATH}?session_id={{CHECKOUT_SESSION_ID}}"
    # Stripe substitutes this literal string and nothing else; it must survive verbatim.
    assert "{CHECKOUT_SESSION_ID}" in success


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
