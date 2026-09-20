"""POST /api/checkout — the only way an order is ever created.

The security question here is: who decides which photos an order generates from?
If the browser posted source URLs, anyone could point a paid order at any object in
the bucket. So the browser gets back an opaque handle for the batch it just
uploaded, signed with APP_TOKEN_SECRET, and the server rebuilds the gs:// keys
itself. The browser never names an object.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import OrderStore, Pipeline, preview_token  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import make_app  # noqa: E402

APP_SECRET = "app_secret"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200


class FakeCheckout:
    def __init__(self, error=None):
        self.calls, self.error = [], error

    def __call__(
        self,
        batch,
        count,
        style,
        gclid,
        wardrobe=None,
        gbraid=None,
        wbraid=None,
        ga_client_id=None,
        ga_session_id=None,
    ):
        self.calls.append(
            (batch, count, style, gclid, wardrobe, gbraid, wbraid, ga_client_id, ga_session_id)
        )
        if self.error:
            raise self.error
        return f"https://checkout.stripe.com/c/pay/{batch}"


def build(checkout=None):
    store = OrderStore()
    pipeline = Pipeline(
        store=store,
        model=type("M", (), {"edit": lambda self, u, p: "https://fal/1.jpg"})(),
        storage=type("S", (), {"put": lambda self, k, u: f"gs://out/{k}"})(),
        send_email=lambda t, b: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret=APP_SECRET,
    )
    ck = checkout or FakeCheckout()
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter(), per_client=50, per_subnet=50),
        enqueue=lambda i: None,
        preview_fn=lambda files, batch: "https://fal.media/preview.jpg",
        webhook_secret="whsec",
        tasks_token="tt",
        verify_turnstile=lambda token, ip: True,
        # The budget push is authenticated now (U1). These tests exercise the KILL
        # SWITCH, not the auth, so they present a caller the app accepts; the auth
        # itself is tests/test_budget_auth.py.
        verify_pubsub=lambda authorization: True,
        create_checkout=ck,
    )
    return TestClient(app), ck


def a_preview(client):
    """Do what the browser does first: upload, and keep the handle."""
    r = client.post(
        "/api/preview",
        files=[("files", ("a.jpg", JPEG, "image/jpeg"))],
        data={"turnstile_token": "good"},
    )
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- the handle


def test_preview_returns_a_signed_handle_for_the_batch_it_stored():
    c, _ = build()
    body = a_preview(c)
    assert body["preview_url"] == "https://fal.media/preview.jpg"
    assert body["n"] == 1
    assert body["t"] == preview_token(body["batch"], 1, APP_SECRET)


def test_two_previews_get_different_batches():
    c, _ = build()
    assert a_preview(c)["batch"] != a_preview(c)["batch"]


# ---------------------------------------------------------------- one


def test_checkout_returns_the_stripe_url():
    c, ck = build()
    h = a_preview(c)
    r = c.post("/api/checkout", json={"batch": h["batch"], "n": h["n"], "t": h["t"]})
    assert r.status_code == 200
    assert r.json() == {"url": f"https://checkout.stripe.com/c/pay/{h['batch']}"}
    assert ck.calls == [(h["batch"], 1, "corporativo", None, None, None, None, None, None)]


def test_style_and_gclid_are_passed_through():
    c, ck = build()
    h = a_preview(c)
    c.post(
        "/api/checkout",
        json={"batch": h["batch"], "n": h["n"], "t": h["t"], "style": "linkedin", "gclid": "g99"},
    )
    assert ck.calls == [(h["batch"], 1, "linkedin", "g99", None, None, None, None, None)]


def test_the_other_four_attribution_ids_are_passed_through():
    """Google Ads splits click ids across gclid/gbraid/wbraid, and GA4's own visitor
    and visit numbers are read separately with gtag('get', ...). All four have to
    reach create_checkout alongside gclid, or the sale cannot be tied to the click
    or the visit that made it."""
    c, ck = build()
    h = a_preview(c)
    c.post(
        "/api/checkout",
        json={
            "batch": h["batch"],
            "n": h["n"],
            "t": h["t"],
            "gbraid": "gb1",
            "wbraid": "wb1",
            "ga_client_id": "111.222",
            "ga_session_id": "333",
        },
    )
    assert ck.calls == [(h["batch"], 1, "corporativo", None, None, "gb1", "wb1", "111.222", "333")]


# ---------------------------------------------------------------- failure


def test_a_forged_handle_is_refused():
    """The whole point: without a valid signature no order is created."""
    c, ck = build()
    h = a_preview(c)
    r = c.post("/api/checkout", json={"batch": h["batch"], "n": h["n"], "t": "deadbeef"})
    assert r.status_code == 403
    assert ck.calls == []


def test_pointing_the_handle_at_another_batch_is_refused():
    """Held-out check: a token is bound to ITS batch. Swapping the batch id while
    keeping a signature that was valid for a different one must not pass."""
    c, ck = build()
    mine, theirs = a_preview(c), a_preview(c)
    r = c.post("/api/checkout", json={"batch": theirs["batch"], "n": 1, "t": mine["t"]})
    assert r.status_code == 403
    assert ck.calls == []


def test_inflating_the_file_count_is_refused():
    """Held-out check: n is signed too. Raising it would make the server build gs://
    keys for objects that were never uploaded, and every generation would fail."""
    c, ck = build()
    h = a_preview(c)
    r = c.post("/api/checkout", json={"batch": h["batch"], "n": 4, "t": h["t"]})
    assert r.status_code == 403
    assert ck.calls == []


def test_the_chosen_wardrobe_is_passed_through():
    """The customer picks a garment, and it has to survive the round trip to Stripe
    metadata and back, or they pay for clothes they did not choose."""
    c, ck = build()
    h = a_preview(c)
    c.post(
        "/api/checkout",
        json={"batch": h["batch"], "n": h["n"], "t": h["t"], "wardrobe": "blusa-sastre"},
    )
    assert ck.calls == [
        (h["batch"], 1, "corporativo", None, "blusa-sastre", None, None, None, None)
    ]


def test_an_unknown_wardrobe_is_refused_before_stripe_is_called():
    """Refused, not silently defaulted. A typo in the browser must not sell someone a
    different outfit, discovered only after the money has moved."""
    c, ck = build()
    h = a_preview(c)
    r = c.post(
        "/api/checkout",
        json={"batch": h["batch"], "n": h["n"], "t": h["t"], "wardrobe": "esmoquin-dorado"},
    )
    assert r.status_code == 422
    assert "unknown_wardrobe" in r.text
    assert ck.calls == []


def test_an_unknown_style_is_refused_before_stripe_is_called():
    c, ck = build()
    h = a_preview(c)
    r = c.post(
        "/api/checkout", json={"batch": h["batch"], "n": h["n"], "t": h["t"], "style": "anime"}
    )
    assert r.status_code == 422
    assert ck.calls == []


def test_missing_fields_are_refused():
    c, ck = build()
    assert c.post("/api/checkout", json={}).status_code == 403
    assert ck.calls == []


def test_checkout_is_closed_while_the_killswitch_is_on():
    """If the budget alert paused generation, taking more money would be fraud."""
    c, ck = build()
    h = a_preview(c)
    c.post("/internal/budget", json={"message": {"data": _budget_note()}})
    r = c.post("/api/checkout", json={"batch": h["batch"], "n": h["n"], "t": h["t"]})
    assert r.status_code == 503
    assert ck.calls == []


def _budget_note():
    import base64
    import json

    return base64.b64encode(json.dumps({"alertThresholdExceeded": 1.0}).encode()).decode()


def test_checkout_not_configured_returns_503_rather_than_a_500():
    """Expand-contract: the code ships before STRIPE_PRICE_EUR reaches Cloud Run."""
    c, _ = build(checkout=None.__class__ and _unconfigured())
    h = a_preview(c)
    r = c.post("/api/checkout", json={"batch": h["batch"], "n": h["n"], "t": h["t"]})
    assert r.status_code == 503
    assert "checkout_not_configured" in r.text


def _unconfigured():
    def raise_it(
        batch,
        count,
        style,
        gclid,
        wardrobe=None,
        gbraid=None,
        wbraid=None,
        ga_client_id=None,
        ga_session_id=None,
    ):
        raise RuntimeError("checkout_not_configured")

    return raise_it


# ---------------------------------------------------------------- token itself


def test_preview_token_is_bound_to_batch_count_and_secret():
    a = preview_token("b1", 2, APP_SECRET)
    assert a == preview_token("b1", 2, APP_SECRET)
    assert a != preview_token("b2", 2, APP_SECRET)
    assert a != preview_token("b1", 3, APP_SECRET)
    assert a != preview_token("b1", 2, "other")
    assert len(a) == 32


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
