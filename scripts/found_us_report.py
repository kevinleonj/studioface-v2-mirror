"""Task 95e. How customers found StudioFace, counted from their orders.

The answer to "¿Cómo nos encontraste?" lives on the order (field `found_us`, see
app/found_us.py), asked only after delivery. Counted over orders that STARTED in the
range (Order.started_at, the same bucketing scripts/funnel_report.py uses). "sin
respuesta" counts delivered orders with no answer: only a delivered order was ever asked,
so a refunded order is neither an answer nor a silence.

Read-only: `.stream()` only. Its own file because funnel_report.py sits at the 300-line
limit.
"""

from __future__ import annotations

from app.found_us import FOUND_US

DAY_SECONDS = 86400
UNANSWERED = "sin respuesta"


def found_us_counts(db, start_day: int, end_day: int) -> dict[str, int]:
    counts = {answer: 0 for answer in FOUND_US} | {UNANSWERED: 0}
    for snap in db.collection("orders").stream():
        data = snap.to_dict() or {}
        started = data.get("started_at")
        if started is None or not start_day <= int(started // DAY_SECONDS) <= end_day:
            continue
        answer = data.get("found_us")
        if answer in counts:
            counts[answer] += 1
        elif data.get("status") == "delivered":
            counts[UNANSWERED] += 1
    return counts


def format_found_us(counts: dict[str, int]) -> str:
    rows = "  ".join(f"{answer}: {n}" for answer, n in counts.items())
    return f"how customers found us (orders started in range): {rows}"
