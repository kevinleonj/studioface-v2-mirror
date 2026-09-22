"""Failing-test-first for scripts/funnel_report.py (task 46: funnel-report-and-
kill-rule). The ad test's kill rule needs numbers to read; this proves the report
reads them correctly against tests/fake_firestore.FakeFirestore -- the same
in-process stand-in app/entry.py's own tests use, for the same reason (no Java
21+ JRE on this machine for the real emulator).

Two required cases:
1. A day with two paid orders and one refund is reported correctly.
2. An empty range prints zeros, not an error.
Plus one check not asked for: a reversed range (no days at all) still renders,
the likeliest way a date-parsing mistake would actually break this script.
"""

from __future__ import annotations

from scripts.funnel_report import (
    DAY_SECONDS,
    build_report,
    format_report,
    stored_batches_total,
)
from tests.fake_firestore import FakeFirestore

DAY = 19_990  # an arbitrary UTC day-int, far from any real date math edge


def _seed_order(db, order_id: str, status: str, started_at: float, outputs=None) -> None:
    db.collection("orders").document(order_id).set(
        {
            "id": order_id,
            "email": "buyer@example.com",
            "source_image_urls": ["gs://studioface-src/previews/b/0.jpg"],
            "style": "corporativo",
            "amount_cents": 1999,
            "status": status,
            "outputs": outputs or [],
            "attempts": 4,
            "started_at": started_at,
        }
    )


def test_a_day_with_two_paid_orders_and_one_refund_is_reported_correctly():
    db = FakeFirestore()
    at = DAY * DAY_SECONDS + 3600  # inside the day, comfortably clear of midnight
    db.collection("counters").document(f"orders:{DAY}").set({"n": 2, "exp": at + 86400})
    db.collection("counters").document(f"g:{DAY}").set({"n": 5, "exp": at + 3600})
    _seed_order(db, "cs_delivered", "delivered", at, outputs=["gs://o/1.jpg"] * 4)
    _seed_order(db, "cs_refunded", "failed_refunded", at + 10)

    rows = build_report(db, DAY, DAY)

    assert len(rows) == 1
    row = rows[0]
    assert row.previews == 5
    assert row.orders_paid == 2
    assert row.orders_delivered == 1
    assert row.orders_refunded == 1
    assert row.paid_per_preview == 2 / 5


def test_an_empty_range_prints_zeros_not_an_error():
    db = FakeFirestore()
    start, end = 20_000, 20_006  # 7 UTC days, nothing ever written to this db

    rows = build_report(db, start, end)
    report = format_report(rows, stored_batches_total(db))

    assert len(rows) == 7
    assert all(
        r.previews == 0
        and r.orders_paid == 0
        and r.orders_delivered == 0
        and r.orders_refunded == 0
        and r.paid_per_preview == 0.0
        for r in rows
    )
    assert "TOTAL" in report  # renders a real table, never raises


def test_a_reversed_range_renders_no_rows_instead_of_crashing():
    db = FakeFirestore()

    rows = build_report(db, 20_010, 20_005)  # end before start
    report = format_report(rows, stored_batches_total(db))

    assert rows == []
    assert "TOTAL" in report
