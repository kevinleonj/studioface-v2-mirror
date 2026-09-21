"""Firestore-backed Counter: the shared ceiling every Cloud Run instance reads.

Proven against a real Firestore transaction by tests/test_counter_atomicity.py, which
runs 24 threads at one document and asserts exactly `limit` get through. That test
needs the emulator (Java 21+) and therefore runs in CI, not on a developer machine.
"""

from __future__ import annotations

import time

from google.cloud import firestore


class FirestoreCounter:
    def __init__(self, client: firestore.Client, collection: str = "counters") -> None:
        self.col = client.collection(collection)
        self.client = client

    def increment_if_below(self, key: str, limit: int, ttl_s: int) -> bool:
        ref = self.col.document(key)

        @firestore.transactional
        def txn(t: firestore.Transaction) -> bool:
            snap = ref.get(transaction=t)
            now = time.time()
            n, exp = (0, now + ttl_s)
            if snap.exists:
                d = snap.to_dict()
                n, exp = d.get("n", 0), d.get("exp", 0)
                if now >= exp:
                    n, exp = 0, now + ttl_s
            if n >= limit:
                return False
            t.set(ref, {"n": n + 1, "exp": exp})
            return True

        return txn(self.client.transaction())

    def decrement(self, key: str) -> None:
        """Give back one try (task 28: refund a preview the model refused or failed).
        A rolled-over window or a count already at 0 is left alone, same rule as
        MemoryCounter.decrement, so this can never resurrect a stale window or send a
        document below zero.
        """
        ref = self.col.document(key)

        @firestore.transactional
        def txn(t: firestore.Transaction) -> None:
            snap = ref.get(transaction=t)
            if not snap.exists:
                return
            d = snap.to_dict()
            n, exp = d.get("n", 0), d.get("exp", 0)
            if time.time() >= exp or n <= 0:
                return
            t.set(ref, {"n": n - 1, "exp": exp})

        txn(self.client.transaction())
