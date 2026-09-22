"""scripts/killswitch.py gives Kevin a way to read and flip the kill switch from
outside a browser, using the exact document the app itself reads
(app/entry.py's FirestoreOrderStore.killswitch, doc config/killswitch).

Run against tests/fake_firestore.py, in process, same convention as
tests/test_firestore_store.py -- no real Firestore, no real gcloud call.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import killswitch  # noqa: E402

from app.entry import FirestoreOrderStore  # noqa: E402
from tests.fake_firestore import FakeFirestore  # noqa: E402

# The exact gate app/main.py's /api/checkout and /api/preview routes use
# (app/main.py:406 and app/main.py:520): "if d.pipeline.store.killswitch: refuse".
# Reproduced here rather than imported, since the routes want a full FastAPI Deps
# object this test has no reason to build.
SHOP_IS_SELLING = "not paused"


def selling(store: FirestoreOrderStore) -> str:
    return "paused" if store.killswitch else SHOP_IS_SELLING


# ---------------------------------------------------------------- empty


def test_status_on_a_never_touched_document_reads_selling():
    db = FakeFirestore()
    store = FirestoreOrderStore(db)
    assert killswitch.read_status(store) is False
    assert selling(store) == SHOP_IS_SELLING


# ---------------------------------------------------------------- one


def test_status_reads_what_the_app_reads():
    db = FakeFirestore()
    FirestoreOrderStore(db).killswitch = True  # written by the app's own code path
    assert killswitch.read_status(FirestoreOrderStore(db)) is True

    FirestoreOrderStore(db).killswitch = False
    assert killswitch.read_status(FirestoreOrderStore(db)) is False


def test_off_after_on_leaves_the_app_selling_again():
    db = FakeFirestore()
    store = FirestoreOrderStore(db)
    killswitch.turn_on(store)
    assert FirestoreOrderStore(db).killswitch is True
    assert selling(FirestoreOrderStore(db)) == "paused"

    killswitch.turn_off(store)
    assert FirestoreOrderStore(db).killswitch is False
    assert selling(FirestoreOrderStore(db)) == SHOP_IS_SELLING


# ---------------------------------------------------------------- many


def test_on_then_status_then_off_then_status_matches_each_step():
    db = FakeFirestore()
    store = FirestoreOrderStore(db)
    killswitch.turn_on(store)
    assert killswitch.read_status(FirestoreOrderStore(db)) is True
    killswitch.turn_off(store)
    assert killswitch.read_status(FirestoreOrderStore(db)) is False
    killswitch.turn_on(store)
    assert killswitch.read_status(FirestoreOrderStore(db)) is True


# ---------------------------------------------------------------- failure


def test_off_when_already_off_is_a_no_op_not_an_error():
    db = FakeFirestore()
    store = FirestoreOrderStore(db)
    killswitch.turn_off(store)  # never was on
    assert FirestoreOrderStore(db).killswitch is False


def test_on_writes_only_the_killswitch_document_nothing_else():
    db = FakeFirestore()
    killswitch.turn_on(FirestoreOrderStore(db))
    assert set(db.docs) == {"config/killswitch"}
    assert db.docs["config/killswitch"] == {"on": True}


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
