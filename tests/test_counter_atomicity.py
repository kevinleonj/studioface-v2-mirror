"""FirestoreCounter under genuinely concurrent writes. CI only.

This is the last untested thing on the money path, and it is the one that bounds the
fal bill: every free preview passes through RateLimiter, and RateLimiter is only as
good as this counter's read-modify-write being atomic. Production has already shown
it works SEQUENTIALLY — /api/recuperar returned 200 x5 then 429 from one IP across
Cloud Run instances (docs/verified.md, 2026-09-17). Sequential is the easy half.
Cloud Run runs many instances at once, and a lost update there is a bill.

Why the emulator and not the fake: tests/fake_firestore.py deep-copies to mimic the
wire, but it cannot fail a transaction and make the client retry, which is the entire
mechanism under test. Why not production: writing contention traffic into the live
counters collection would rate-limit real customers.

Honest limit on what this proves. Google documents that the emulator "uses simple
locking" for transactions and does not reproduce production's concurrency control,
and that a lock from a failed transaction can take up to 30 seconds to release
(https://docs.cloud.google.com/firestore/docs/emulator). So a pass here proves our
transaction is written correctly and never loses an update under contention. It does
not prove production's exact retry semantics. That is strictly more than we had.

That limitation is not theoretical: the first CI run of this file (35242208491) had
24 threads exhaust the client's five retry attempts on one document and raise
ValueError("Failed to commit transaction in 5 attempts"). So the assertions here are
written as the property that actually matters — the document NEVER grants more than
`limit`, whoever wins — rather than as "exactly `limit` threads win", which is a claim
about scheduling fairness that the emulator cannot honour and that we do not need.

Worth carrying forward into production thinking: that same exhaustion is possible on
the one genuinely hot document we have, the global daily key `g:{day}`, which every
single preview writes to. Firestore sustains roughly one write per second per
document. At the 300/day ceiling that is nowhere near the limit, but under a burst the
transaction can raise and /api/preview will answer 500. It fails CLOSED — no fal call
is made — so the bill stays bounded, which is the right direction to fail in.
"""

import os
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EMULATOR = os.environ.get("FIRESTORE_EMULATOR_HOST")

# Gated on the emulator's own variable rather than on `which java`: this is what the
# client library reads, and it is the thing whose absence makes the test meaningless.
# Only .github/workflows/*.yml set it — pinned by tests/test_ci_contract.py, because a
# test that skips everywhere is worse than no test at all.
pytestmark = pytest.mark.skipif(
    not EMULATOR,
    reason="needs the Firestore emulator (Java 21+); FIRESTORE_EMULATOR_HOST unset. CI runs it.",
)

PROJECT = "studioface-emulator-test"
THREADS = 24


@pytest.fixture
def counter():
    from google.cloud import firestore

    from app.adapters.firestore_counter import FirestoreCounter

    # One client shared by every thread, which is what a Cloud Run instance does.
    return FirestoreCounter(firestore.Client(project=PROJECT), collection="counters_test")


def key(name: str) -> str:
    """A fresh document per test run; the emulator keeps state for the whole job."""
    return f"{name}-{time.time_ns()}"


def hammer(counter, k: str, limit: int, threads: int = THREADS) -> tuple[int, int]:
    """Every thread waits on the barrier, then they all hit one document at once.

    Returns (granted, exhausted). `exhausted` counts threads whose transaction ran out
    of retries — the client raises ValueError("Failed to commit transaction in N
    attempts") — which under the emulator's simple locking is common and is NOT a
    counter bug. An exhausted attempt grants nothing, so it never overspends; it is
    counted rather than swallowed so the arithmetic below stays exact.
    """
    barrier, lock = threading.Barrier(threads), threading.Lock()
    granted = exhausted = 0

    def one():
        nonlocal granted, exhausted
        barrier.wait()
        try:
            got = counter.increment_if_below(k, limit, 3600)
        except ValueError:  # retries exhausted; the transaction committed nothing
            with lock:
                exhausted += 1
            return
        with lock:
            granted += int(got)

    workers = [threading.Thread(target=one) for _ in range(threads)]
    for w in workers:
        w.start()
    for w in workers:
        w.join(timeout=120)
    assert not any(w.is_alive() for w in workers), "a worker never finished"
    return granted, exhausted


def settled(counter, k: str, limit: int) -> bool:
    """One increment once the storm is over. The emulator can hold a lock from an
    aborted transaction for up to 30 s, so this waits it out instead of flaking."""
    for _ in range(40):
        try:
            return counter.increment_if_below(k, limit, 3600)
        except ValueError:
            time.sleep(1)
    raise AssertionError("the emulator never released the lock")


# ---------------------------------------------------------------- many


def test_never_more_than_the_limit_gets_through_however_many_arrive_at_once(counter):
    """The safety property, and the one that bounds the bill. A lost update shows up
    here as MORE than `limit` grants, and every extra grant is fal work nobody paid
    for. Under-granting is safe; over-granting is money."""
    granted, _ = hammer(counter, key("many"), limit=10)
    assert granted <= 10, f"{granted} grants from a limit of 10 — a lost update"


def test_the_document_ends_at_exactly_the_limit_no_matter_who_won(counter):
    """The exactness claim, stated so that the emulator's locking cannot make it flaky.
    Whoever lost a race is simply drained sequentially afterwards, and the total number
    of grants the document ever issues must come to `limit` — not fewer (a grant was
    lost), not more (a grant was duplicated)."""
    k = key("exact")
    granted, _ = hammer(counter, k, limit=3, threads=8)
    assert granted <= 3
    drained = 0
    while settled(counter, k, 3):
        drained += 1
        assert granted + drained <= 3, "the counter kept granting past its limit"
    assert granted + drained == 3, f"{granted} under contention + {drained} after = not 3"


# ---------------------------------------------------------------- one


def test_a_limit_of_one_admits_at_most_one_of_twenty_four(counter):
    granted, _ = hammer(counter, key("one"), limit=1)
    assert granted <= 1


# ---------------------------------------------------------------- empty


def test_a_limit_of_zero_admits_nobody(counter):
    granted, _ = hammer(counter, key("zero"), limit=0)
    assert granted == 0


def test_cold_start_the_document_does_not_exist_yet(counter):
    """The first caller of every new hour, and of every new IP, hits a missing doc."""
    assert counter.increment_if_below(key("cold"), 2, 3600) is True


# ---------------------------------------------------------------- failure


def test_the_window_expires_and_the_count_starts_again(counter):
    """Held-out check: the ttl branch is the one that cannot be proven by counting.
    If `exp` were never honoured, a client blocked once would be blocked forever."""
    k = key("ttl")
    assert counter.increment_if_below(k, 1, 1) is True
    assert counter.increment_if_below(k, 1, 1) is False
    time.sleep(1.2)
    assert counter.increment_if_below(k, 1, 1) is True


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
