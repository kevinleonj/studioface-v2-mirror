"""Task 41 (credit-runs-out). What used to happen when fal refuses for lack of
credit or any other billing reason: nothing distinguished it from an ordinary fal
outage. `Pipeline._generate` -> `_attempt` caught EVERY exception, logged it, and
counted it as one spent attempt of the order-level retry budget
(app/core.py:_attempt, before this task). A locked account fails every one of those
calls identically, so the order burned the full n_images + extra_attempts budget
(8 calls today) finding that out, then fell through to the existing "could not
produce four images" branch: _refund() and the existing cancellation email — so the
CUSTOMER was already made whole. Nobody else was told anything, and nothing stopped
the shop selling: the next order paid, was enqueued, and repeated exactly the same
eight wasted calls and refund. Kevin's own dozen-orders-per-credit-dollar shop could
burn through a whole business day of orders, refunding every single one, with no one
told until he happened to check the fal dashboard.

fal itself documents no stable status code or error `type` for this case
(docs/verified.md, 2026-09-22) — only its FAQ prose: "When your credit balance drops
below your account's lock threshold, your account is locked and API requests will be
rejected." app/adapters/fal.py's `_is_billing_refusal` heuristic (one of fal's own
documented authorization codes, 401/403, or the conventional 402, together with a
credit/balance/lock hint in the message) is what turns that into `BillingRefused`,
distinct from both `ModelRefused` (the visitor's to fix) and an ordinary outage (fal
5xx, a timeout — still retried exactly as before, held out by the second half of this
file).

This file proves both halves: the adapter's classification, and the pipeline's
response to it — refund automatically, kill the switch, tell Kevin once, and do none
of that for a transient failure.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import emails  # noqa: E402
from app.adapters.fal import FalModel  # noqa: E402
from app.core import (  # noqa: E402
    OWNER_ALERT_PREFIX,
    BillingRefused,
    Order,
    OrderStore,
    Pipeline,
    Refund,
    threaded_batch,
)

# ---------------------------------------------------------------- the adapter


class FakeFalError(Exception):
    """Stands in for fal_client.FalClientHTTPError: status_code, error_type and
    message are the three attributes app/adapters/fal.py actually reads."""

    def __init__(self, status_code, message=None, error_type=None):
        super().__init__(message or error_type or "fal error")
        self.status_code = status_code
        self.message = message
        self.error_type = error_type


class RaisingSubscribe:
    def __init__(self, error):
        self.error, self.calls = error, 0

    def __call__(self, application, arguments=None, **kw):
        self.calls += 1
        raise self.error


def sign(uri):
    return f"https://storage.googleapis.com/{uri.removeprefix('gs://')}?X-Goog-Signature=ab"


def test_a_locked_account_raises_billing_refused():
    """The refusal quoted in fal's own FAQ: locked for lack of credit."""
    err = FakeFalError(
        403,
        error_type="authorization_error",
        message="Your account is locked: credit balance below the lock threshold.",
    )
    m = FalModel(sign=sign, subscribe=RaisingSubscribe(err))
    with pytest.raises(BillingRefused):
        m.edit(["gs://sf-src/a.jpg"], "p")


def test_a_402_with_balance_wording_is_also_billing_refused():
    err = FakeFalError(402, message="insufficient balance")
    m = FalModel(sign=sign, subscribe=RaisingSubscribe(err))
    with pytest.raises(BillingRefused):
        m.edit(["gs://sf-src/a.jpg"], "p")


def test_an_ordinary_outage_is_not_billing_refused():
    """Held-out check: the heuristic must not swallow a plain 5xx into a permanent
    shutdown. A dead provider is still just a dead provider."""
    err = FakeFalError(503, message="upstream unavailable")
    m = FalModel(sign=sign, subscribe=RaisingSubscribe(err))
    with pytest.raises(FakeFalError):
        m.edit(["gs://sf-src/a.jpg"], "p")


def test_a_403_without_billing_wording_is_not_billing_refused():
    """Held-out check the other way: fal's own authorization code, but for a reason
    that has nothing to do with money (a bad API key), must not pause the whole shop."""
    err = FakeFalError(403, error_type="authorization_error", message="invalid API key")
    m = FalModel(sign=sign, subscribe=RaisingSubscribe(err))
    with pytest.raises(FakeFalError):
        m.edit(["gs://sf-src/a.jpg"], "p")


# ---------------------------------------------------------------- the pipeline


class AlwaysBillingRefused:
    """Every call fails the identical way an account-wide lock actually would."""

    def __init__(self):
        self.calls = 0

    def edit(self, urls, prompt):
        self.calls += 1
        raise BillingRefused("account locked")


class AlwaysTransient:
    """An ordinary dead provider - the outage the existing retry budget is for."""

    def __init__(self):
        self.calls = 0

    def edit(self, urls, prompt):
        self.calls += 1
        raise RuntimeError("fal 503")


class Storage:
    def put(self, key, url):
        return f"gs://out/{key}"


def build(model, owner_email="kevin@example.com", killswitch=False):
    store = OrderStore()
    store.killswitch = killswitch
    emails_sent, refunds = [], []
    p = Pipeline(
        store=store,
        model=model,
        storage=Storage(),
        send_email=lambda to, body: emails_sent.append((to, body)),
        refund=lambda order_id, cents: Refund(id="re_1", status="succeeded"),
        track_conversion=lambda o: None,
        secret="app",
        owner_email=owner_email,
        run_batch=threaded_batch,  # matches app/entry.py's real wiring
    )
    store.put(
        Order(
            id="o1",
            email="cliente@example.com",
            source_image_urls=["gs://src/a.jpg"],
            style="corporativo",
            amount_cents=1999,
        )
    )
    return p, store, emails_sent, refunds


def test_a_credit_refusal_refunds_kills_and_notifies_once():
    model = AlwaysBillingRefused()
    p, store, emails_sent, _ = build(model)
    order = p.run("o1")

    # Refunded through the existing path, no images delivered.
    assert order.status == "failed_refunded"
    assert order.outputs == []

    # The customer gets the EXISTING cancellation email, same sentinel as any other
    # undeliverable order.
    assert ("cliente@example.com", "REFUND") in emails_sent

    # The switch is on: no further orders taken until Kevin resets it.
    assert store.killswitch is True

    # Kevin is told, exactly once, and the body says how many orders this told him
    # about.
    owner_emails = [b for to, b in emails_sent if to == "kevin@example.com"]
    assert owner_emails == [f"{OWNER_ALERT_PREFIX}1"]

    # Never burned the retry budget finding this out: stops within the first wave
    # (threaded_batch submits it eagerly, so up to n_images calls can already be in
    # flight before the exception is observed — but never a second wave on top).
    assert model.calls <= p.n_images
    assert order.attempts <= p.n_images


def test_a_second_order_caught_by_the_same_outage_does_not_page_kevin_again():
    """The switch is already on from a previous order's alert; this one still
    refunds, but does not send a second owner email for the same incident."""
    model = AlwaysBillingRefused()
    p, store, emails_sent, _ = build(model, killswitch=True)
    order = p.run("o1")

    assert order.status == "failed_refunded"
    assert store.killswitch is True
    assert ("cliente@example.com", "REFUND") in emails_sent
    assert [b for to, b in emails_sent if to == "kevin@example.com"] == []


def test_no_owner_email_configured_still_refunds_and_kills():
    """OWNER_ALERT_EMAIL is optional (app/config.py): an unconfigured deployment must
    not crash trying to alert nobody."""
    model = AlwaysBillingRefused()
    p, store, emails_sent, _ = build(model, owner_email=None)
    order = p.run("o1")

    assert order.status == "failed_refunded"
    assert store.killswitch is True
    assert ("cliente@example.com", "REFUND") in emails_sent


def test_an_ordinary_transient_fal_error_keeps_retrying_and_does_not_kill():
    """The side this task must NOT change: a plain outage still burns the full
    order-level retry budget and refunds through the existing no-images-delivered
    path — exactly tests/test_generation.py's
    test_total_outage_still_refunds_and_never_exceeds_the_budget, pinned again here
    because credit exhaustion must never regress it."""
    model = AlwaysTransient()
    p, store, emails_sent, _ = build(model)
    order = p.run("o1")

    assert order.status == "failed_refunded"
    assert order.outputs == []
    assert model.calls == p.n_images + p.extra_attempts  # 8: never more, never fewer
    assert ("cliente@example.com", "REFUND") in emails_sent

    # The one thing that must NOT have happened for an ordinary outage.
    assert store.killswitch is False
    assert [b for to, b in emails_sent if to == "kevin@example.com"] == []


# ---------------------------------------------------------------- the owner email


def test_owner_alert_maps_to_a_real_email_naming_the_count():
    message = emails.for_body(f"{OWNER_ALERT_PREFIX}3")
    assert "3" in message.subject or "3" in message.text
    assert "fal" in message.text.lower()
    assert "credit" in message.text.lower()


def test_the_two_owner_alert_prefixes_agree():
    """core.py and emails.py each define this constant independently (the same
    convention as REFUND_EMAIL_SENTINEL / emails.REFUND_SENTINEL) — held out so the
    two can never silently drift apart."""
    assert OWNER_ALERT_PREFIX == emails.OWNER_ALERT_PREFIX


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
