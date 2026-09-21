"""POST /api/recuperar — resend the gallery link to the buyer's own address.

Two rules shape this endpoint. It answers the same thing whether or not the address
exists, because a different answer would turn it into a way to test whether a given
person bought. And it is rate limited on its own counter, because it sends mail to
an address the caller chose, which is a way to use us to spam someone.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import Order, OrderStore, Pipeline, delivery_token  # noqa: E402
from app.entry import FirestoreOrderStore  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import make_app  # noqa: E402
from tests.fake_firestore import FakeFirestore  # noqa: E402

APP_SECRET = "app_secret"


def an_order(oid, email="cliente@example.com", status="delivered"):
    return Order(
        id=oid,
        email=email,
        source_image_urls=["gs://src/a.jpg"],
        style="corporativo",
        amount_cents=1999,
        status=status,
        outputs=["gs://out/0.jpg"] * 4 if status == "delivered" else [],
    )


def build(store=None):
    store = store if store is not None else OrderStore()
    emails = []
    pipeline = Pipeline(
        store=store,
        model=type("M", (), {"edit": lambda self, u, p: "x"})(),
        storage=type("S", (), {"put": lambda self, k, u: k})(),
        send_email=lambda to, body: emails.append((to, body)),
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret=APP_SECRET,
    )
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter(), per_client=50, per_subnet=50),
        enqueue=lambda i: None,
        preview_fn=lambda f, batch: "",
        webhook_secret="whsec",
        tasks_token="tt",
    )
    return TestClient(app), store, emails


def recover(client, email, ip="9.9.9.9"):
    return client.post("/api/recuperar", json={"email": email}, headers={"x-forwarded-for": ip})


# ---------------------------------------------------------------- one


def test_a_delivered_order_gets_its_link_resent():
    c, store, emails = build()
    store.put(an_order("cs_1"))
    r = recover(c, "cliente@example.com")
    assert r.status_code == 200 and r.json() == {"sent": True}
    to, body = emails[0]
    assert to == "cliente@example.com"
    assert body == f"https://studioface.app/g/#o=cs_1&t={delivery_token('cs_1', APP_SECRET)}"


def test_the_address_is_matched_case_insensitively_and_trimmed():
    """People type their address by hand here, unlike at checkout."""
    c, store, emails = build()
    store.put(an_order("cs_1", email="Cliente@Example.com"))
    assert recover(c, "  cliente@example.com ").json() == {"sent": True}
    assert len(emails) == 1


# ---------------------------------------------------------------- empty


def test_an_unknown_address_gets_the_same_answer_and_no_email():
    """The whole point: the response must not reveal whether the order exists."""
    c, store, emails = build()
    store.put(an_order("cs_1", email="alguien@example.com"))
    known = recover(c, "alguien@example.com")
    unknown = recover(c, "nadie@example.com", ip="9.9.9.8")
    assert known.status_code == unknown.status_code
    assert known.json() == unknown.json() == {"sent": True}
    assert len(emails) == 1  # only the real one was sent


def test_an_order_that_is_not_delivered_yet_is_not_resent():
    c, store, emails = build()
    store.put(an_order("cs_1", status="generating"))
    assert recover(c, "cliente@example.com").json() == {"sent": True}
    assert emails == []


def test_a_refunded_order_is_not_resent():
    c, store, emails = build()
    store.put(an_order("cs_1", status="failed_refunded"))
    recover(c, "cliente@example.com")
    assert emails == []


# ---------------------------------------------------------------- many


def test_several_orders_for_one_address_all_get_a_link():
    c, store, emails = build()
    for i in range(3):
        store.put(an_order(f"cs_{i}"))
    recover(c, "cliente@example.com")
    assert len(emails) == 3
    assert {e[0] for e in emails} == {"cliente@example.com"}


# ---------------------------------------------------------------- failure


def test_recovery_has_its_own_rate_limit():
    """Held-out check: this sends mail to an address the CALLER types. Without a cap
    it is a way to use us to deliver mail to someone repeatedly."""
    c, store, emails = build()
    store.put(an_order("cs_1"))
    codes = [recover(c, "cliente@example.com").status_code for _ in range(8)]
    assert 429 in codes, codes
    assert codes.count(200) <= 5


def test_the_recovery_cap_does_not_consume_the_free_preview_budget():
    """Held-out check: sharing one counter would let a recovery attempt burn the
    stranger's free preview, and vice versa."""
    c, store, emails = build()
    store.put(an_order("cs_1"))
    for _ in range(5):
        recover(c, "cliente@example.com", ip="7.7.7.7")
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 200
    r = c.post(
        "/api/preview",
        files=[("files", ("a.jpg", jpeg, "image/jpeg"))],
        data={"turnstile_token": "ok"},
        headers={"x-forwarded-for": "7.7.7.7"},
    )
    assert r.status_code == 200, r.text


def test_a_missing_or_malformed_email_is_refused():
    c, store, emails = build()
    assert c.post("/api/recuperar", json={}).status_code == 422
    assert c.post("/api/recuperar", json={"email": "not-an-address"}).status_code == 422
    assert emails == []


# ---------------------------------------------------------------- firestore


def test_the_firestore_store_finds_orders_by_email():
    db = FakeFirestore()
    store = FirestoreOrderStore(db)
    store.put(an_order("cs_1"))
    store.put(an_order("cs_2", email="otro@example.com"))
    found = store.find_by_email("cliente@example.com")
    assert [o.id for o in found] == ["cs_1"]
    assert store.find_by_email("nadie@example.com") == []


def test_recovery_works_end_to_end_against_the_firestore_store():
    db = FakeFirestore()
    store = FirestoreOrderStore(db)
    c, _, emails = build(store=store)
    store.put(an_order("cs_9"))
    assert recover(c, "cliente@example.com").json() == {"sent": True}
    assert emails[0][1].startswith("https://studioface.app/g/#o=cs_9&t=")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
