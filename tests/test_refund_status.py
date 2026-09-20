"""A refund is a request, not an outcome, and the pipeline treated it as an outcome.

Pipeline.run called self.refund(...) and immediately wrote status "failed_refunded" —
a word that asserts the customer's money is back. For a card that is near enough:
Stripe returns a refund already in status "succeeded". For Bizum it is false. Bizum
refunds are asynchronous, take up to about five minutes, and reach their real state on
refund.updated / refund.failed (docs/verified.md, 2026-09-17). A Bizum refund that
ends "failed" left an order reading "failed_refunded", nobody paid back, and not one
line in the log.

This is on an AUTOMATIC path, which is what makes it serious. Pipeline.run refunds by
itself whenever generation cannot produce four images; no human is watching.

The second defect is worse and predates Bizum. "failed_refunded" was in the replay
guard, so a retried Cloud Task on an already-refunded order returned early. Any status
that is NOT in that guard means a Cloud Tasks retry calls stripe.Refund.create a
second time. So the new pending state had to join the guard in the same commit that
introduced it, or the fix for a silent refund would have created a double one.
"""

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import Order, OrderStore, Pipeline, Refund  # noqa: E402

# One placeholder for every credential-shaped variable. Settings only checks that they
# are non-empty, and writing realistic-looking values next to their names is exactly
# what the secrets guard exists to stop.
PLACEHOLDER = "placeholder-value"
CREDENTIAL_VARS = (
    "TASKS_TOKEN",
    "APP_TOKEN_SECRET",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "RESEND_API_KEY",
    "TURNSTILE_SECRET",
)
FAKE_ENV = {
    "GCP_PROJECT": "sf",
    "GCP_REGION": "europe-west1",
    "PUBLIC_URL": "https://studioface.app",
    "BUCKET_SRC": "bucket-src",
    "BUCKET_OUT": "bucket-out",
    "TASKS_QUEUE": "generate",
    **dict.fromkeys(CREDENTIAL_VARS, PLACEHOLDER),
}


class DeadModel:
    """Never produces an image, so every order reaches the refund branch."""

    def edit(self, urls, prompt):
        raise RuntimeError("fal is down")


def build(refund):
    store = OrderStore()
    calls = []

    def recording(order_id, cents):
        calls.append((order_id, cents))
        return refund

    pipeline = Pipeline(
        store=store,
        model=DeadModel(),
        storage=type("S", (), {"put": lambda self, k, u: k})(),
        send_email=lambda t, b: None,
        refund=recording,
        track_conversion=lambda o: None,
        secret=PLACEHOLDER,
    )
    return pipeline, store, calls


def an_order(order_id="cs_test_1"):
    return Order(
        id=order_id,
        email="cliente@example.com",
        source_image_urls=["gs://src/a.jpg"],
        style="corporativo",
        amount_cents=1999,
    )


def run_with(refund):
    pipeline, store, calls = build(refund)
    store.put(an_order())
    return pipeline.run("cs_test_1"), store, calls


# ---------------------------------------------------------------- the outcome


def test_a_pending_refund_is_not_reported_as_refunded():
    """The defect itself. 'failed_refunded' claims the money is back."""
    order, _, _ = run_with(Refund(id="re_1", status="pending"))
    assert order.status == "failed_refund_pending"
    assert order.refund_id == "re_1"
    assert order.refund_status == "pending"


def test_a_succeeded_refund_is_reported_as_refunded():
    order, _, _ = run_with(Refund(id="re_2", status="succeeded"))
    assert order.status == "failed_refunded"
    assert order.refund_id == "re_2"
    assert order.refund_status == "succeeded"


def test_a_failed_refund_is_logged_at_error(caplog):
    """Nobody is watching this path, so the log line is the only alarm there is."""
    with caplog.at_level(logging.ERROR, logger="app.core"):
        order, _, _ = run_with(Refund(id="re_3", status="failed"))
    assert order.status == "failed_refund_pending"
    assert order.refund_status == "failed"
    assert any(r.levelno == logging.ERROR and "re_3" in r.getMessage() for r in caplog.records), (
        f"no ERROR naming the refund: {[r.getMessage() for r in caplog.records]}"
    )


def test_the_refund_state_is_persisted_not_just_returned():
    """Held-out check: the gallery and /recuperar read the STORE, never the object the
    pipeline happened to return, so an in-memory-only update would be invisible."""
    _, store, _ = run_with(Refund(id="re_4", status="pending"))
    saved = store.get("cs_test_1")
    assert (saved.status, saved.refund_id, saved.refund_status) == (
        "failed_refund_pending",
        "re_4",
        "pending",
    )


# ---------------------------------------------------------------- replay


def test_a_retried_task_does_not_refund_a_second_time():
    """Cloud Tasks retries any non-2xx. Without the pending state in the replay guard,
    the fix above would turn one silent refund into two real ones."""
    pipeline, store, calls = build(Refund(id="re_5", status="pending"))
    store.put(an_order())
    pipeline.run("cs_test_1")
    pipeline.run("cs_test_1")
    assert calls == [("cs_test_1", 1999)], f"refund called {len(calls)} times"


def test_a_retried_task_does_not_refund_a_confirmed_order_again():
    pipeline, store, calls = build(Refund(id="re_6", status="succeeded"))
    store.put(an_order())
    pipeline.run("cs_test_1")
    pipeline.run("cs_test_1")
    assert len(calls) == 1


# ---------------------------------------------------------------- the old port


def test_a_port_that_reports_nothing_keeps_the_old_behaviour():
    """Every existing test fakes refund as `lambda o, c: None`. A port that reports no
    status gets what it always got, rather than every one of those tests quietly
    asserting a state the code no longer produces. Production never takes this path —
    the test below pins that."""
    order, _, _ = run_with(None)
    assert order.status == "failed_refunded"
    assert order.refund_id is None


def test_the_production_adapter_reports_id_and_status(monkeypatch):
    """The other half: _stripe_refund must never be the silent port above."""
    from app.config import Settings

    created = {}

    class FakeRefund:
        @staticmethod
        def create(**kw):
            created.update(kw)
            return type("R", (), {"id": "re_live", "status": "pending"})()

    class FakeSession:
        @staticmethod
        def retrieve(oid):
            return type("S", (), {"payment_intent": "pi_1"})()

    stripe = type("stripe", (), {})()
    stripe.api_key = None
    stripe.Refund = FakeRefund
    stripe.checkout = type("c", (), {"Session": FakeSession})()
    monkeypatch.setitem(sys.modules, "stripe", stripe)

    from app import entry

    result = entry._stripe_refund(Settings.from_env(FAKE_ENV))("cs_test_1", 1999)
    assert isinstance(result, Refund)
    assert (result.id, result.status) == ("re_live", "pending")
    assert created["amount"] == 1999


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
