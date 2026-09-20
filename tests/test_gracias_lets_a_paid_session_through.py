"""I2: every paid customer was sent to raw JSON. Only made-up ids ever worked.

Kevin paid with the test card on 19 September. Stripe redirected to

    /api/gracias?session_id=cs_test_REDACTED

and got `HTTP 404 {"detail":"Not Found"}`. Still 404 minutes later, on both hosts, so
not a webhook delay. Everything behind the door had worked: the webhook fired, the order
exists in Firestore with `status='delivered'` and four images, and
`POST /internal/generate/<id>` returned 200 at 13:31:29.

## The cause, proven

`app/entry.py:108` did `dict(stripe.checkout.Session.retrieve(session_id))`. On
stripe-python 15.6.1, run against the real session:

    TypeError: Session is not iterable or a mapping; call .to_dict() for a plain dict.

The v15.0.0 migration guide says why: "`StripeObject` no longer inherits from `dict`, so
any `dict` methods will no longer exist". `except stripe.error.InvalidRequestError` does
not catch a TypeError, so it escaped `retrieve` into `/api/gracias`'s bare
`except Exception`, which logged at INFO - invisible, because nothing configures logging
- and raised 404.

## Why every check passed

P1. The guard was accepted on "a fake session returns 404". A handler that refuses
everything passes that, and this one refused everything. `scripts/verify_production.py`
asserted the negative case only, and so did the unit tests.

So every test here comes in a pair: one that must be refused, one that must be let
through. The held-out case is the one that was missing for a day.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import OrderStore, Pipeline  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import make_app  # noqa: E402

PAID = "cs_test_paid"
GENERATED = []


def session(status: str, session_id: str = PAID) -> dict:
    return {
        "id": session_id,
        "payment_status": status,
        "status": "complete",
        "customer_details": {"email": "k@example.com"},
        "metadata": {"source_urls": "gs://src/a.jpg", "style": "corporativo", "wardrobe": ""},
        "amount_total": 1999,
    }


def build(retrieve_session=None):
    GENERATED.clear()
    store = OrderStore()
    pipeline = Pipeline(
        store=store,
        model=type("M", (), {"edit": lambda self, u, p: "x"})(),
        storage=type("S", (), {"put": lambda self, k, u: k})(),
        send_email=lambda t, b: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret="app",
    )
    kwargs = {} if retrieve_session is None else {"retrieve_session": retrieve_session}
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter()),
        enqueue=GENERATED.append,
        preview_fn=lambda f, batch: "",
        webhook_secret="whsec",
        tasks_token="tt",
        **kwargs,
    )
    from fastapi.testclient import TestClient

    return TestClient(app, follow_redirects=False), store


def get(client, session_id=PAID):
    return client.get("/api/gracias", params={"session_id": session_id})


# ---------------------------------------------------------------- let through


def test_a_paid_session_reaches_the_gallery():
    """I2 itself. This is the assertion whose absence cost a real customer."""
    c, _ = build(retrieve_session=lambda sid: session("paid", sid))
    r = get(c)
    assert r.status_code == 302, f"{r.status_code} {r.text}"
    location = r.headers["location"]
    assert "/g/" in location, location
    assert f"o={PAID}" in location and "&t=" in location, location


def test_a_session_needing_no_payment_reaches_the_gallery_too():
    """Stripe's own fulfilment gate is `payment_status != 'unpaid'`, not `== 'paid'`:
    its reference implementation fulfils for `paid` AND `no_payment_required`. A
    100%-off coupon produces the latter and is a legitimate order.

    This corrects a stricter rule I wrote into this route earlier the same day, which
    would have refused a customer who owed nothing.
    """
    c, _ = build(retrieve_session=lambda sid: session("no_payment_required", sid))
    assert get(c).status_code == 302


def test_the_order_is_created_when_the_webhook_has_not_arrived_yet():
    """C2(a). Stripe: "trigger fulfillment from your landing page as well", because
    "webhooks can sometimes be delayed". The gallery 404s until an order exists, so
    redirecting to it without creating one only moves the dead end."""
    c, store = build(retrieve_session=lambda sid: session("paid", sid))
    assert store.get(PAID) is None
    get(c)
    order = store.get(PAID)
    assert order is not None, "the redirect led to a gallery with no order behind it"
    assert order.email == "k@example.com"
    assert GENERATED == [PAID], f"generation was not queued exactly once: {GENERATED}"


def test_a_late_webhook_is_a_no_op_and_nothing_is_generated_twice():
    """C2(a) again, and the reason it has to go through the same claim guard. Four
    images cost real money; generating them twice costs it twice and can overwrite a
    delivered order with a fresh one."""
    c, store = build(retrieve_session=lambda sid: session("paid", sid))
    get(c)
    assert GENERATED == [PAID]
    from app.main import FULFIL_PREFIX

    assert not store.claim_event(f"{FULFIL_PREFIX}{PAID}"), (
        "the session was not claimed, so a late webhook would generate four images again"
    )


def test_an_order_that_already_exists_is_never_fulfilled_again():
    """The defect this test was written after, measured in production.

    When C2 first shipped, `_fulfil_session` claimed a key of its own and nothing else.
    The webhook of 19 September had claimed the EVENT id, so the session key was free:
    re-requesting the success URL for an order that was already `delivered` with four
    images overwrote it with a fresh one and queued generation again. Four fal images,
    charged, for a visitor pressing back.

    The order document IS the fulfilment record - Stripe: "Record/save fulfillment
    status for this Checkout Session" - so its existence is what must be checked first.
    The claim key stays as the guard against two callers arriving at once.
    """
    c, store = build(retrieve_session=lambda sid: session("paid", sid))

    # The state the webhook of 19 September actually left: an order, delivered, with the
    # EVENT id claimed and the session key untouched. Calling gracias first instead would
    # let it claim the session key and hide the bug, which is what the first draft of
    # this test did - it passed against the broken code.
    from app.main import _order_from_session

    store.claim_event("evt_REDACTED")
    order = _order_from_session(session("paid"))
    order.status, order.outputs = "delivered", ["gs://out/1.jpg"] * 4
    store.put(order)
    GENERATED.clear()

    r = get(c)

    assert r.status_code == 302, "a returning customer must still reach their gallery"
    assert GENERATED == [], "generation was queued again for an order already delivered"
    again = store.get(PAID)
    assert again.status == "delivered", f"a delivered order was overwritten: {again.status}"
    assert len(again.outputs) == 4, "the delivered images were lost"


# ---------------------------------------------------------------- refuse


def test_a_session_stripe_does_not_know_is_404():
    c, _ = build(retrieve_session=lambda sid: None)
    r = get(c, "cs_test_fake")
    assert r.status_code == 404
    assert "location" not in r.headers


def test_an_unpaid_session_is_404():
    c, store = build(retrieve_session=lambda sid: session("unpaid", sid))
    assert get(c).status_code == 404
    assert store.get(PAID) is None, "an unpaid session created an order"
    assert GENERATED == [], "an unpaid session queued generation"


def test_something_that_cannot_be_a_session_id_never_reaches_stripe():
    asked = []
    c, _ = build(retrieve_session=lambda sid: asked.append(sid) or None)
    assert get(c, "../../etc/passwd").status_code == 404
    assert asked == []


# ---------------------------------------------------------------- never JSON


def test_a_stripe_failure_is_502_html_with_a_way_out_not_a_silent_404():
    """C2(c). A person who paid must never see `{"detail":"Not Found"}`.

    This is the exact shape of I2: an exception became a 404 and the customer got raw
    JSON. A refusal and a breakage are different answers and must look different.
    """

    def boom(sid):
        raise RuntimeError("stripe is down")

    c, _ = build(retrieve_session=boom)
    r = get(c)
    assert r.status_code == 502, f"{r.status_code} {r.text}"
    body = r.text
    assert "recuperar" in body.lower(), "no way back for someone who has already paid"
    assert "detail" not in body[:40].lower(), f"this still looks like JSON: {body[:80]}"
    assert r.headers["content-type"].startswith("text/html"), r.headers["content-type"]


def test_the_default_retriever_still_refuses():
    """Held-out the other way: an unwired Stripe client must not open the route."""
    c, _ = build()
    assert get(c).status_code == 404


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
