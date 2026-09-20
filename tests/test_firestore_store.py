"""FirestoreOrderStore must behave exactly like the in-memory OrderStore the
pipeline is tested against — same three calls, same answers, but surviving a
process restart. Run against tests/fake_firestore.py (no JRE for the emulator).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import Order  # noqa: E402
from app.entry import FirestoreOrderStore  # noqa: E402
from tests.fake_firestore import FakeFirestore  # noqa: E402


def an_order(oid="cs_1", **kw) -> Order:
    base = dict(
        id=oid,
        email="k@example.com",
        source_image_urls=["gs://src/a.jpg", "gs://src/b.jpg"],
        style="corporativo",
        amount_cents=1999,
        gclid="g123",
    )
    return Order(**{**base, **kw})


def store() -> FirestoreOrderStore:
    return FirestoreOrderStore(FakeFirestore())


# ---------------------------------------------------------------- empty


def test_get_on_an_empty_database_returns_none():
    assert store().get("cs_nope") is None


# ---------------------------------------------------------------- one


def test_put_then_get_round_trips_every_field():
    s = store()
    s.put(an_order())
    got = s.get("cs_1")
    assert got == an_order()  # dataclass equality: every field, exactly


def test_none_gclid_survives_the_round_trip_as_none():
    s = store()
    s.put(an_order(gclid=None))
    assert s.get("cs_1").gclid is None


def test_put_is_idempotent_and_status_transitions_persist():
    s = store()
    o = an_order()
    s.put(o)
    o.status = "generating"
    s.put(o)
    o.status = "delivered"
    o.outputs = ["gs://out/cs_1/0.jpg"]
    s.put(o)
    got = s.get("cs_1")
    assert got.status == "delivered" and got.outputs == ["gs://out/cs_1/0.jpg"]


# ---------------------------------------------------------------- many


def test_four_outputs_and_attempts_survive():
    s = store()
    s.put(an_order(outputs=[f"gs://out/cs_1/{i}.jpg" for i in range(4)], attempts=6))
    got = s.get("cs_1")
    assert len(got.outputs) == 4 and got.attempts == 6


def test_many_orders_do_not_collide():
    s = store()
    for i in range(25):
        s.put(an_order(oid=f"cs_{i}", amount_cents=1000 + i))
    assert s.get("cs_7").amount_cents == 1007
    assert s.get("cs_24").amount_cents == 1024
    assert s.get("cs_25") is None


def test_orders_live_in_their_own_collection_not_mixed_with_events():
    s = store()
    s.put(an_order())
    s.claim_event("evt_1")
    assert set(s.db.docs) == {"orders/cs_1", "events/evt_1"}


# ---------------------------------------------------------------- idempotency


def test_claim_event_is_true_once_then_false():
    s = store()
    assert s.claim_event("evt_1") is True
    assert s.claim_event("evt_1") is False
    assert s.claim_event("evt_2") is True


def test_constructing_the_store_writes_nothing():
    """Regression: OrderStore.__init__ assigns `self.killswitch = False`, which lands
    on the property setter below. Inherited, that crashed before self.db existed."""
    db = FakeFirestore()
    FirestoreOrderStore(db)
    assert db.docs == {}


def test_a_cold_start_does_not_reset_a_kill_switch_that_is_on():
    """Regression, and the dangerous half: the budget alert flips the switch on,
    Cloud Run starts another instance, and that instance must not turn it back off."""
    db = FakeFirestore()
    FirestoreOrderStore(db).killswitch = True
    assert FirestoreOrderStore(db).killswitch is True


def test_killswitch_defaults_false_and_persists_when_flipped():
    s = store()
    assert s.killswitch is False
    s.killswitch = True
    assert s.killswitch is True
    s.killswitch = False
    assert s.killswitch is False


# ---------------------------------------------------------------- failure


def test_a_stored_document_missing_a_required_field_fails_loudly():
    s = store()
    s.db.docs["orders/cs_broken"] = {"id": "cs_broken", "email": "k@example.com"}
    with pytest.raises(TypeError):
        s.get("cs_broken")


def test_an_unknown_future_field_is_ignored_rather_than_crashing():
    """Held-out check: a newer revision adds a column, an older instance still reads.
    Cloud Run runs both revisions at once during a rollout."""
    s = store()
    s.put(an_order())
    s.db.docs["orders/cs_1"]["locale"] = "es-ES"  # written by a future version
    assert s.get("cs_1").id == "cs_1"


def test_mutating_the_order_after_put_does_not_change_the_database():
    """Held-out check: put must serialise, not hand Firestore a live reference.
    The pipeline mutates the same Order object between puts."""
    s = store()
    o = an_order()
    s.put(o)
    o.outputs.append("gs://out/leaked.jpg")
    o.status = "delivered"
    assert s.get("cs_1").outputs == []
    assert s.get("cs_1").status == "paid"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
