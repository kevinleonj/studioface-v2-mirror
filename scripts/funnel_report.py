"""Funnel report: prints the numbers the ad test's kill rule (docs/ads/CAMPAIGN.md,
"Pre-registered test") needs to read. Task 46.

Read-only. Every Firestore call here is `.get()` or `.stream()` -- never `.set()`,
`.create()`, `.delete()` or a transaction -- so running this against production
reads a handful of documents and writes nothing, real or fake. No order is ever
touched.

WHAT IS ACTUALLY IN FIRESTORE, and what is not:

- previews requested / previews produced: both rows read the SAME document,
  counters/g:<day> (guards.RateLimiter's daily global counter). `check()` in
  app/guards.py increments it the moment a preview attempt is admitted, and
  `refund()` DECREMENTS it again the instant a failed attempt is refunded
  (app/main.py's `d.limiter.refund(...)`, called only on ModelRefused/ValueError).
  Firestore keeps only the net value, so a request that failed and was refunded is
  indistinguishable, after the fact, from a request that never happened. Until a
  separate attempt log exists, "requested" and "produced" are the same number by
  construction -- stated here rather than invented as two different ones.
- batches stored at the limit: guards.RateLimiter.check_store's counter
  (key `store:<hash>`) is keyed per visitor, not per day -- there is no UTC-day
  component in it at all. Reported once, as a current total, not scoped to the
  requested range.
- checkout sessions created / previews per checkout: app/main.py's /api/checkout
  route creates a Stripe Checkout Session and writes nothing to Firestore. The
  only app record of "began checkout" is the browser-only GA4 event
  `begin_checkout` (frontend/src/lib/track.ts), which this server-side script
  cannot read. Reported as not available -- the same honesty the task that asked
  for this script already applied to landing visits by page.
- orders paid: counters/orders:<day> (guards.DailyOrderCeiling, wired in
  app/entry.py's build()). Incremented once per order admitted under the daily
  ceiling, which is every ordinary paid order; capped at the ceiling's own limit
  (20/day) if that limit is ever hit, which a 150 EUR test never will.
- orders delivered / orders refunded: the "orders" collection itself, bucketed by
  `Order.started_at` (app/core.py), the one timestamp already on the document --
  set by `Pipeline.run` before it calls the model, for both a delivered order and
  every "undeliverable" or "fal_credit" refund. It is NOT set for the rare order
  refused outright by the daily ceiling (app/core.py's `Pipeline.admit`), because
  that order never reaches `run()`; such an order is refunded and stored, but
  cannot be placed on a day by this script. Named here rather than guessed past.
- cost of images per order: a flat figure, not per-day. docs/verified.md,
  2026-09-16: fal nano-banana-2/edit costs $0.08 per 1K-resolution image, sourced
  from https://fal.ai/models/fal-ai/nano-banana-2/edit/api. app/core.py's
  `Pipeline.n_images` (4) is how many a delivered order always wants, at the same
  1K resolution `app/adapters/fal.py`'s `FalModel` defaults to for a real order
  (the free preview alone uses 0.5K, a different, cheaper call). 4 x $0.08 =
  $0.32 in USD, independent of how many orders any one day had.

Usage:
    python scripts/funnel_report.py                  # last 7 UTC days
    python scripts/funnel_report.py --days 14
    python scripts/funnel_report.py --start 2026-09-15 --end 2026-09-21
    python scripts/funnel_report.py --since 2026-09-23  # + the step 1 kill-rule verdict
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.core import Pipeline

# Run as `python scripts/funnel_report.py`, `scripts` is not a package; its own folder
# goes on the path instead, the way go_live.py reaches _exec.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from found_us_report import format_found_us, found_us_counts  # noqa: E402

PROJECT = "studio-face-fresh-start"
DAY_SECONDS = 86400

# docs/verified.md, 2026-09-16: fal nano-banana-2/edit, $0.08 per 1K-resolution image.
PRICE_USD_PER_IMAGE = 0.08
IMAGES_PER_ORDER = Pipeline.__dataclass_fields__["n_images"].default
IMAGE_COST_USD_PER_ORDER = round(IMAGES_PER_ORDER * PRICE_USD_PER_IMAGE, 2)

REFUND_STATUSES = {"failed_refunded", "failed_refund_pending", "failed_refund_failed"}


def day_int(epoch: float) -> int:
    """The same UTC-day bucketing guards.py and core.py already use, unchanged:
    `str(int(now // 86400))`, here kept as an int since nothing needs the string
    form."""
    return int(epoch // DAY_SECONDS)


def day_label(day: int) -> str:
    return datetime.fromtimestamp(day * DAY_SECONDS, tz=UTC).strftime("%Y-%m-%d")


def default_range(days: int = 7, now: float | None = None) -> tuple[int, int]:
    """Inclusive [start, end] day-ints for the last `days` UTC days, today included."""
    end_day = day_int(time.time() if now is None else now)
    return end_day - (days - 1), end_day


@dataclass
class DayCounts:
    day: int
    previews: int = 0
    orders_paid: int = 0
    orders_delivered: int = 0
    orders_refunded: int = 0

    @property
    def paid_per_preview(self) -> float:
        return self.orders_paid / self.previews if self.previews else 0.0


def _counter_n(db, key: str) -> int:
    snap = db.collection("counters").document(key).get()
    data = snap.to_dict() if snap.exists else None
    return int((data or {}).get("n", 0))


def stored_batches_total(db) -> int:
    """Sum of every RateLimiter.check_store counter that currently exists. Not
    scoped to any date range -- see the module docstring."""
    return sum(
        int((snap.to_dict() or {}).get("n", 0))
        for snap in db.collection("counters").stream()
        if (snap.id or "").startswith("store:")
    )


def _orders_by_day(db, start_day: int, end_day: int) -> dict[int, list[dict]]:
    buckets: dict[int, list[dict]] = {d: [] for d in range(start_day, end_day + 1)}
    for snap in db.collection("orders").stream():
        data = snap.to_dict() or {}
        started = data.get("started_at")
        if started is None:
            continue  # never reached Pipeline.run -- see module docstring
        day = day_int(started)
        if day in buckets:
            buckets[day].append(data)
    return buckets


def build_report(db, start_day: int, end_day: int) -> list[DayCounts]:
    """One row per UTC day in [start_day, end_day]. A reversed range (end before
    start) yields no rows at all, never an error."""
    if end_day < start_day:
        return []
    orders_by_day = _orders_by_day(db, start_day, end_day)
    rows = []
    for day in range(start_day, end_day + 1):
        row = DayCounts(day=day)
        row.previews = _counter_n(db, f"g:{day}")
        row.orders_paid = _counter_n(db, f"orders:{day}")
        for order in orders_by_day[day]:
            if order.get("status") == "delivered":
                row.orders_delivered += 1
            elif order.get("status") in REFUND_STATUSES:
                row.orders_refunded += 1
        rows.append(row)
    return rows


def _totals(rows: list[DayCounts]) -> DayCounts:
    total = DayCounts(day=-1)
    for row in rows:
        total.previews += row.previews
        total.orders_paid += row.orders_paid
        total.orders_delivered += row.orders_delivered
        total.orders_refunded += row.orders_refunded
    return total


_HEADER = (
    f"{'day':<12}{'previews req':>14}{'previews made':>15}{'orders paid':>13}"
    f"{'delivered':>11}{'refunded':>10}{'paid/preview':>14}"
)


def _row_line(label: str, row: DayCounts) -> str:
    return (
        f"{label:<12}{row.previews:>14}{row.previews:>15}{row.orders_paid:>13}"
        f"{row.orders_delivered:>11}{row.orders_refunded:>10}{row.paid_per_preview:>14.3f}"
    )


def format_report(rows: list[DayCounts], stored_batches: int) -> str:
    lines = [_HEADER]
    lines += [_row_line(day_label(row.day), row) for row in rows]
    lines.append(_row_line("TOTAL", _totals(rows)))
    lines.append("")
    lines.append(
        "batches stored at the limit (current total, not scoped to the range "
        f"above -- see script docstring): {stored_batches}"
    )
    lines.append(
        "checkout sessions created: not available -- /api/checkout writes nothing to "
        "Firestore; begin_checkout is a browser-only GA4 event, see script docstring"
    )
    lines.append("previews per checkout: not available, same reason as above")
    lines.append(
        f"estimated image cost per order: ${IMAGE_COST_USD_PER_ORDER:.2f} "
        f"({IMAGES_PER_ORDER} images x ${PRICE_USD_PER_IMAGE:.2f}, fal nano-banana-2/edit, "
        "docs/verified.md 2026-09-16)"
    )
    return "\n".join(lines)


# docs/ads/CAMPAIGN.md, "Pre-registered test" (task 92). Clicks and spend live in Google
# Ads, which a server-side script cannot read, so the verdict line says so and computes
# the rest: the click ceiling the previews can cover and the spend ceiling the paid
# orders allow.
STEP1_DAYS = 14
STEP1_MIN_CLICKS = 25
CLICKS_PER_PREVIEW = 10  # kill if previews are FEWER than 1 in 10 clicks
MAX_EUR_PER_PAID_ORDER = 20


def step1_state(previews: int, paid: int, day: int) -> str:
    """What our own numbers decide about step 1 on its `day` (1 = the --since day).

    Step 1 ends after 14 days or 50 EUR, whichever first, and the spend is only in
    Google Ads, so before day 14 a kill reads "if step 1 ended today"."""
    if day < 1:
        return "NOT STARTED: --since is after today"
    kill = "KILL" if day >= STEP1_DAYS else "KILL IF STEP 1 ENDED TODAY"
    max_clicks = previews * CLICKS_PER_PREVIEW
    if paid == 0:
        return f"{kill}: zero paid orders"
    if max_clicks < STEP1_MIN_CLICKS:
        return (
            f"{kill}: {previews} previews cover at most {max_clicks} clicks, "
            f"under the {STEP1_MIN_CLICKS} the rule needs"
        )
    return (
        f"CONTINUE ONLY IF Google Ads shows {STEP1_MIN_CLICKS} to {max_clicks} clicks "
        f"and spend under {paid * MAX_EUR_PER_PAID_ORDER} EUR"
    )


def step1_line(db, since_day: int, today: int) -> str:
    total = _totals(build_report(db, since_day, today))
    day = today - since_day + 1
    return (
        f"STEP 1 VERDICT: {step1_state(total.previews, total.orders_paid, day)} | "
        f"day {day} of {STEP1_DAYS} since {day_label(since_day)} (or 50 EUR spent, "
        "whichever first) | clicks: read in Google Ads | spend: read in Google Ads | "
        f"previews started: {total.previews} | paid orders: {total.orders_paid}"
    )


def _parse_day(value: str) -> int:
    return day_int(datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


def _resolve_range(args: argparse.Namespace) -> tuple[int, int]:
    if args.since:
        return _parse_day(args.since), day_int(time.time())
    if args.start:
        start_day = _parse_day(args.start)
        end_day = _parse_day(args.end) if args.end else day_int(time.time())
        return start_day, end_day
    return default_range(days=args.days)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print the ad-test kill-rule funnel numbers.")
    parser.add_argument("--days", type=int, default=7, help="last N UTC days (default 7)")
    when = parser.add_mutually_exclusive_group()
    when.add_argument("--start", help="YYYY-MM-DD UTC, overrides --days")
    when.add_argument(
        "--since", help="YYYY-MM-DD UTC the ad test began: report to today + step 1 verdict"
    )
    parser.add_argument("--end", help="YYYY-MM-DD UTC, defaults to today (with --start)")
    return parser.parse_args(argv[1:])


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    start_day, end_day = _resolve_range(args)

    from google.cloud import firestore

    print(f"Firestore project: {PROJECT} (read-only: .get() and .stream() calls only)")
    db = firestore.Client(project=PROJECT)
    rows = build_report(db, start_day, end_day)
    print(format_report(rows, stored_batches_total(db)))
    print(format_found_us(found_us_counts(db, start_day, end_day)))
    if args.since:
        print()
        print(step1_line(db, start_day, end_day))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
