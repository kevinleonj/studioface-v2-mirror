import hashlib
import hmac
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import (  # noqa: E402
    Order,
    OrderStore,
    Pipeline,
    delivery_token,
    verify_stripe_signature,
)

SECRET = "whsec_test"
APP_SECRET = "app_secret"


def sign(payload: bytes, secret=SECRET, ts=None):
    ts = ts or int(time.time())
    v1 = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={v1}"


class FakeModel:
    """Fails the first `fail_first` calls, then succeeds."""

    def __init__(self, fail_first=0, always_fail=False):
        self.calls = 0
        self.fail_first = fail_first
        self.always_fail = always_fail

    def edit(self, image_urls, prompt):
        self.calls += 1
        if self.always_fail or self.calls <= self.fail_first:
            raise RuntimeError("fal 500")
        return f"https://fal.media/out{self.calls}.png"


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def put(self, key, url):
        self.objects[key] = url
        return f"https://cdn.studioface.app/{key}"


def build(model=None):
    store = OrderStore()
    emails, refunds, conversions = [], [], []
    p = Pipeline(
        store=store,
        model=model or FakeModel(),
        storage=FakeStorage(),
        send_email=lambda to, body: emails.append((to, body)),
        refund=lambda oid, cents: refunds.append((oid, cents)),
        track_conversion=lambda o: conversions.append(o.id),
        secret=APP_SECRET,
    )
    store.put(
        Order(
            id="o1",
            email="k@example.com",
            source_image_urls=["https://cdn/x.jpg"] * 3,
            style="corporativo",
            amount_cents=1499,
            gclid="abc",
        )
    )
    return p, store, emails, refunds, conversions


# ---------------------------------------------------------------- signature


def test_valid_signature_accepted():
    body = b'{"id":"evt_1"}'
    assert verify_stripe_signature(body, sign(body), SECRET)


def test_tampered_body_rejected():
    body = b'{"id":"evt_1"}'
    header = sign(body)
    assert not verify_stripe_signature(b'{"id":"evt_1","amount":1}', header, SECRET)


def test_replayed_old_signature_rejected():
    body = b'{"id":"evt_1"}'
    old = sign(body, ts=int(time.time()) - 3600)
    assert not verify_stripe_signature(body, old, SECRET)


def test_wrong_secret_rejected():
    body = b'{"id":"evt_1"}'
    assert not verify_stripe_signature(body, sign(body, secret="whsec_other"), SECRET)


# ---------------------------------------------------------------- idempotency


def test_duplicate_webhook_claimed_once():
    store = OrderStore()
    assert store.claim_event("evt_1") is True
    assert store.claim_event("evt_1") is False


def test_pipeline_rerun_does_not_regenerate_or_reemail():
    p, store, emails, refunds, conv = build()
    p.run("o1")
    calls_after_first = p.model.calls
    p.run("o1")  # Cloud Tasks redelivery / Stripe retry
    assert p.model.calls == calls_after_first == 4
    assert len(emails) == 1
    assert len(conv) == 1


# ---------------------------------------------------------------- failures


def test_transient_failures_are_retried_and_order_still_delivers():
    p, store, emails, refunds, conv = build(FakeModel(fail_first=2))
    order = p.run("o1")
    assert order.status == "delivered"
    assert len(order.outputs) == 4
    assert order.attempts == 6  # 2 wasted + 4 good
    assert refunds == []


def test_total_model_outage_refunds_and_never_marks_delivered():
    p, store, emails, refunds, conv = build(FakeModel(always_fail=True))
    order = p.run("o1")
    assert order.status == "failed_refunded"
    assert refunds == [("o1", 1499)]
    assert conv == []  # no conversion sent to Google Ads
    assert emails == [("k@example.com", "REFUND")]


def test_partial_output_is_never_delivered_as_complete():
    """Held-out check: 3 of 4 images is a failure, not a discount."""

    class ThreeThenDie:
        def __init__(self):
            self.calls = 0

        def edit(self, u, p):
            self.calls += 1
            if self.calls > 3:
                raise RuntimeError("fal 500")
            return f"https://fal.media/{self.calls}.png"

    p, store, emails, refunds, conv = build(ThreeThenDie())
    order = p.run("o1")
    assert order.status == "failed_refunded"
    assert len(order.outputs) == 3
    assert refunds == [("o1", 1499)]


# ---------------------------------------------------------------- delivery token


def test_delivery_token_is_deterministic_and_secret_bound():
    a = delivery_token("o1", APP_SECRET)
    assert a == delivery_token("o1", APP_SECRET)
    assert a != delivery_token("o1", "other_secret")
    assert a != delivery_token("o2", APP_SECRET)
    assert len(a) == 32


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
