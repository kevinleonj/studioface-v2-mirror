"""U2: `/api/gracias` minted a gallery token for anything starting `cs_`.

Measured against production on 19 September, before the fix:

    $ curl -i "https://studioface.app/api/gracias?session_id=cs_test_fake"
    HTTP/1.1 302 Found
    location: https://studioface.app/g/?o=cs_test_fake&t=REDACTED

Deterministic — two calls returned the same token. The only check was the three-character
prefix; Stripe was never asked whether the session existed or was paid.

`delivery_token` is the same token that gates `/api/orders`, so this route was a
token-minting oracle for the whole order namespace: supply an id, receive its token.

What proves payment, from Stripe's own object reference (docs/verified.md, R1, 19 Sep):
"The payment status of the Checkout Session, one of `paid`, `unpaid`, or
`no_payment_required`", where `paid` means "The payment funds are available in your
account." For a one-time `mode: payment` session that is the only acceptable value —
`no_payment_required` belongs to `setup` mode and to billing-cycle anchors, neither of
which this product uses.

**The retriever defaults to returning nothing**, so an unwired or broken Stripe client
closes the route rather than opening it.
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


def session(status: str, session_id: str = PAID) -> dict:
    return {
        "id": session_id,
        "payment_status": status,
        "customer_details": {"email": "k@example.com"},
        "metadata": {"source_urls": "gs://src/a.jpg", "style": "corporativo"},
        "amount_total": 1999,
    }


def build(retrieve_session=None):
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
        enqueue=lambda i: None,
        preview_fn=lambda f, batch: "",
        webhook_secret="whsec",
        tasks_token="tt",
        **kwargs,
    )
    from fastapi.testclient import TestClient

    return TestClient(app, follow_redirects=False), store


def get(client, session_id):
    return client.get("/api/gracias", params={"session_id": session_id})


def test_a_session_stripe_does_not_know_gets_no_token():
    """The production defect. Stripe returns nothing for an invented id."""
    c, _ = build(retrieve_session=lambda sid: None)
    r = get(c, "cs_test_fake")
    assert r.status_code == 404, r.status_code
    assert "location" not in r.headers, r.headers.get("location")


def test_an_unpaid_session_gets_no_token():
    """A session can exist and not be paid — an abandoned Checkout is exactly that."""
    c, _ = build(retrieve_session=lambda sid: session("unpaid", sid))
    r = get(c, PAID)
    assert r.status_code == 404
    assert "location" not in r.headers


def test_no_payment_required_is_accepted_after_all():
    """SUPERSEDED BY C2, and worth keeping as a record of the correction.

    This test used to assert 404, on the reasoning that `no_payment_required` "belongs
    to setup mode and to billing-cycle anchors" and that accepting it would be a free
    gallery. Stripe's own fulfilment guide disagrees: its reference implementation gates
    on `payment_status != "unpaid"`, which fulfils `paid` AND `no_payment_required`.

    The case that reasoning missed is a 100%-off coupon on a `mode: payment` session.
    That customer owes nothing, has completed checkout, and would have been refused.
    """
    c, _ = build(retrieve_session=lambda sid: session("no_payment_required", sid))
    assert get(c, PAID).status_code == 302


def test_a_paid_session_still_redirects_with_its_token():
    """Held-out check. Returning 404 for everything would pass every test above and break
    every real purchase."""
    c, _ = build(retrieve_session=lambda sid: session("paid", sid))
    r = get(c, PAID)
    assert r.status_code == 302, r.text
    location = r.headers["location"]
    assert f"o={PAID}" in location and "&t=" in location, location


def test_the_default_retriever_refuses():
    """Unwired or broken Stripe client closes the route rather than opening it."""
    c, _ = build()
    assert get(c, PAID).status_code == 404


def test_a_stripe_failure_is_a_502_page_not_a_silent_404():
    """SUPERSEDED BY C2, and this one caused the incident.

    It used to assert 404, reasoning that "a 5xx here would retry-loop the browser and,
    worse, read as a server problem when it is a refusal". The second half is exactly
    backwards: a Stripe client that raises IS a server problem, and turning it into 404
    is what sent a paying customer `{"detail":"Not Found"}` on 19 September.

    A refusal and a breakage must look different, and the person who has already paid
    gets a Spanish page with a way out rather than a JSON body.
    """

    def boom(sid):
        raise RuntimeError("stripe is down")

    c, _ = build(retrieve_session=boom)
    r = get(c, PAID)
    assert r.status_code == 502
    assert "recuperar" in r.text.lower()


def test_the_prefix_check_is_still_there_so_stripe_is_not_asked_about_junk():
    """Cheap guard first: no network call for a string that cannot be a session id."""
    asked = []
    c, _ = build(retrieve_session=lambda sid: asked.append(sid) or None)
    assert get(c, "../../etc/passwd").status_code == 404
    assert asked == [], f"Stripe was asked about {asked}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
