"""order_delivered fired on every gallery view.

`/g/` polls every 3 s until the order is delivered, and the poll loop already stops
firing `track(EVENTS.orderDelivered, ...)` more than once per page load - the branch
`return`s the moment it fires. The bug is across page loads: the delivery email points
at this same link, and the page itself says "recarga la pagina para renovarlos" because
the signed image URLs expire in 15 minutes. Both a re-opened email link and that
suggested reload run the whole effect again from a fresh `useState("loading")`, so the
poll loop restarts at zero and fires a second `order_delivered` for an order this
browser already saw delivered, sometimes seconds later.

The fix has to survive exactly the reload that causes the bug, so it cannot live in
React state or a ref - both are wiped on the very reload that re-triggers the poll loop.
It has to be:
- read BEFORE `track()` fires, or the second poll loop still fires it unconditionally;
- keyed to THIS order, not one global flag - a single flag would suppress
  `order_delivered` for every order after the first one this browser ever received;
- written AFTER `track()` fires, or nothing is ever recorded and every reload fires
  again anyway;
- wrapped in a try/catch, because private-mode Safari throws on localStorage access
  (see `frontend/src/components/consent.tsx`), and a tracker that throws takes the
  whole poll loop down with it.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from source_scan import strip_comments  # noqa: E402

PAGE = ROOT / "frontend" / "src" / "app" / "g" / "page.tsx"


def source() -> str:
    return strip_comments(PAGE.read_text(encoding="utf-8"), language="tsx")


def delivered_branch() -> str:
    """The `data.status === "delivered"` branch inside `poll`, where the event fires."""
    src = source()
    start = src.index('if (data.status === "delivered")')
    end = src.index('if (data.status === "failed_refunded")')
    return src[start:end]


def test_the_delivered_branch_still_fires_the_event():
    """Held-out: the fix de-duplicates the event, it does not delete it."""
    assert "track(EVENTS.orderDelivered" in delivered_branch()


def test_the_event_is_guarded_by_a_check_that_reads_before_it_fires():
    """A read anywhere else in the file is not a guard: it has to run before `track()`
    inside this same branch, or the restarted poll loop still fires unconditionally."""
    block = delivered_branch()
    track_at = block.index("track(EVENTS.orderDelivered")
    before = block[:track_at]
    assert "localStorage" in before, (
        "nothing reads persisted state before track() fires in the delivered branch"
    )


def test_the_guard_is_keyed_to_this_order_not_one_global_flag():
    """A single flag such as `sf-delivered` would suppress `order_delivered` for every
    order after the first one this browser ever received. The storage key must
    reference the order id."""
    block = delivered_branch()
    read = re.search(r"localStorage\.getItem\(([^)]*)\)", block)
    assert read, "no localStorage.getItem in the delivered branch"
    assert "order" in read.group(1), (
        f"the storage key does not reference the order id: {read.group(1)}"
    )


def test_the_order_is_marked_delivered_after_the_event_fires():
    """Read before, write after: without the write, every reload reads nothing and
    fires `order_delivered` again anyway."""
    block = delivered_branch()
    track_at = block.index("track(EVENTS.orderDelivered")
    after = block[track_at:]
    write = re.search(r"localStorage\.setItem\(([^,]*),", after)
    assert write, "nothing marks the order as delivered after track() fires"
    assert "order" in write.group(1), f"the write does not key on the order id: {write.group(1)}"


def test_the_storage_access_is_guarded_against_throwing():
    """consent.tsx's own rule: private-mode Safari throws on localStorage access, and a
    tracker that throws takes the whole poll loop down with it."""
    block = delivered_branch()
    assert "try" in block and "catch" in block, (
        "localStorage is read or written without a try/catch in the delivered branch"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
