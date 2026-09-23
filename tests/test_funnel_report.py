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


# ------------------------------------------------ task 92: the step 1 verdict line
#
# docs/ads/CAMPAIGN.md, "Pre-registered test": kill after step 1 if clicks from Google
# Ads are fewer than 25, or previews started are fewer than 1 in 10 clicks, or paid
# orders are zero; continue to step 2 only if cost per paid order projects under 20 EUR.
# Step 1 ends after 50 EUR or 14 days. Clicks and spend live in Google Ads, which this
# script cannot read, so the line says so and computes everything else: the click
# ceiling the previews can cover, and the spend ceiling the paid orders allow.

import pytest  # noqa: E402

import scripts.funnel_report as fr  # noqa: E402

SINCE = DAY


def _seed_counter(db, key: str, n: int) -> None:
    db.collection("counters").document(key).set({"n": n})


def test_an_empty_first_day_says_kill_if_it_ended_today_and_where_clicks_live():
    """Empty: day 1, nothing yet."""
    line = fr.step1_line(FakeFirestore(), SINCE, SINCE)
    assert line.startswith("STEP 1 VERDICT: KILL IF STEP 1 ENDED TODAY: zero paid orders"), line
    assert "clicks: read in Google Ads" in line and "day 1 of 14" in line, line


def test_one_paid_order_gives_the_click_range_and_spend_ceiling():
    """One: 3 previews cover up to 30 clicks; 1 order allows up to 20 EUR."""
    db = FakeFirestore()
    _seed_counter(db, f"g:{SINCE}", 3)
    _seed_counter(db, f"orders:{SINCE + 4}", 1)
    line = fr.step1_line(db, SINCE, SINCE + 4)
    assert "CONTINUE ONLY IF Google Ads shows 25 to 30 clicks and spend under 20 EUR" in line
    assert "previews started: 3" in line and "paid orders: 1" in line and "day 5 of 14" in line


def test_many_days_are_summed_across_the_whole_step():
    """Many: counts from every day since --since, not just today."""
    db = FakeFirestore()
    for offset, previews in enumerate((4, 3, 3)):
        _seed_counter(db, f"g:{SINCE + offset}", previews)
    _seed_counter(db, f"orders:{SINCE}", 1)
    _seed_counter(db, f"orders:{SINCE + 2}", 1)
    line = fr.step1_line(db, SINCE, SINCE + 2)
    assert "previews started: 10" in line and "paid orders: 2" in line, line
    assert "25 to 100 clicks and spend under 40 EUR" in line, line


def test_day_14_with_zero_paid_orders_is_a_plain_kill():
    line = fr.step1_line(FakeFirestore(), SINCE, SINCE + 13)
    assert line.startswith("STEP 1 VERDICT: KILL: zero paid orders"), line


def test_too_few_previews_kill_whatever_the_click_count():
    """2 previews cover at most 20 clicks, but the rule needs at least 25: no click
    count satisfies both, so the server can call it without Google Ads."""
    db = FakeFirestore()
    _seed_counter(db, f"g:{SINCE}", 2)
    _seed_counter(db, f"orders:{SINCE}", 1)
    line = fr.step1_line(db, SINCE, SINCE + 13)
    assert line.startswith("STEP 1 VERDICT: KILL: 2 previews cover at most 20 clicks"), line


def test_a_since_date_after_today_is_refused_as_not_started():
    """Failure: a typo in --since must not print a verdict about a step that has not run."""
    line = fr.step1_line(FakeFirestore(), SINCE + 1, SINCE)
    assert line.startswith("STEP 1 VERDICT: NOT STARTED"), line


def test_exactly_one_preview_in_ten_clicks_still_passes():
    """Nobody asked for this one, and it is the likeliest off-by-one. The rule kills on
    FEWER than 1 in 10, so exactly 1 in 10 passes: the top of the range is 10 x previews,
    not 10 x previews - 1."""
    assert fr.step1_state(previews=3, paid=1, day=5).endswith(
        "25 to 30 clicks and spend under 20 EUR"
    )


def test_since_is_accepted_on_the_command_line_and_excludes_start():
    assert fr.parse_args(["funnel_report.py", "--since", "2026-09-23"]).since == "2026-09-23"
    with pytest.raises(SystemExit):
        fr.parse_args(["funnel_report.py", "--since", "2026-09-23", "--start", "2026-09-20"])
