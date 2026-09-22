"""Task 42 (daily-money-stops). Two stops that need no human under paid ad traffic.

1. Daily order ceiling -- 20 paid orders per UTC day. Stripe has already taken the
   money by the time an order is fulfilled, so "refuse" here cannot mean "decline the
   payment": it means this order (and every one after it, until Kevin resets the
   switch by hand) is refunded instead of generated, the switch is killed, and Kevin
   is paged once. Checked in Pipeline.admit(order), called from app/main.py's
   _fulfil_session -- the ONE place (shared by the Stripe webhook and the
   post-payment redirect) that turns a paid Checkout Session into an Order, already
   idempotency-guarded there for exactly this reason (FULFIL_PREFIX). Counting
   earlier, at /api/checkout, would count checkout ATTEMPTS -- free to make, and
   Stripe may never complete them -- not orders that actually took money, which is
   what this stop exists to cap.

2. Refund-rate alarm -- 3 or more orders refunded in one UTC day pages Kevin once,
   naming the order id prefixes and why, and does NOT stop the shop: a bad photo, a
   change of heart and a real defect all look identical from here, so this is "go
   look", not "stop selling". Counted inside Pipeline._refund, the one method every
   refund path already calls (an undeliverable order, a fal credit lockout, and the
   new daily-ceiling refusal below) -- the same choke point task 41 used for the
   credit-exhaustion alert.

Both alerts reuse task 41's exact shape: a sentinel prefix app/emails.py's for_body
sniffs, the same send_email port, the same _shell/_button styling, and (for the
ceiling) the same off-to-on killswitch transition _handle_credit_exhausted uses so a
second incident on the same day never pages Kevin twice.
"""

import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import (  # noqa: E402
    DAILY_CEILING_ALERT_PREFIX,
    REFUND_ALARM_PREFIX,
    Order,
    OrderStore,
    Pipeline,
    Refund,
)
from app.guards import DailyOrderCeiling, MemoryCounter, RateLimiter  # noqa: E402
from app.main import THANKS_PATH, make_app  # noqa: E402

OWNER = "kevin@example.com"
APP_SECRET = "app"


def working_model():
    return type("M", (), {"edit": lambda self, u, p: "https://fal/1.jpg"})()


def failing_model():
    return type("M", (), {"edit": lambda self, u, p: (_ for _ in ()).throw(RuntimeError("no"))})()


def fake_storage():
    return type("S", (), {"put": lambda self, k, u: f"gs://out/{k}"})()


def paid_order(oid: str) -> Order:
    return Order(
        id=oid,
        email=f"{oid}@example.com",
        source_image_urls=["gs://src/a.jpg"],
        style="corporativo",
        amount_cents=1999,
    )


def build_pipeline(model=None, limit=20, owner_email=OWNER, now=None, ceiling=True):
    store = OrderStore()
    emails_sent: list[tuple[str, str]] = []
    clock = now or time.time
    kwargs = dict(
        store=store,
        model=model or working_model(),
        storage=fake_storage(),
        send_email=lambda to, body: emails_sent.append((to, body)),
        refund=lambda order_id, cents: Refund(id="re_1", status="succeeded"),
        track_conversion=lambda o: None,
        secret=APP_SECRET,
        owner_email=owner_email,
        now=clock,
    )
    if ceiling:
        kwargs["order_ceiling"] = DailyOrderCeiling(
            counter=MemoryCounter(now=clock), limit=limit, now=clock
        )
    p = Pipeline(**kwargs)
    return p, store, emails_sent


# ---------------------------------------------------------------- daily order ceiling


def test_the_20th_paid_order_of_the_day_is_admitted():
    p, store, emails_sent = build_pipeline(limit=20)
    for i in range(20):
        assert p.admit(paid_order(f"o{i}")) is True
    assert store.killswitch is False
    assert [b for to, b in emails_sent if to == OWNER] == []


def test_the_21st_paid_order_of_the_day_is_refused_refunded_and_pages_kevin_once():
    p, store, emails_sent = build_pipeline(limit=20)
    for i in range(20):
        assert p.admit(paid_order(f"o{i}")) is True
    over = paid_order("o20")
    assert p.admit(over) is False
    assert over.status == "failed_refunded"
    assert (over.email, "REFUND") in emails_sent
    assert store.killswitch is True
    assert [b for to, b in emails_sent if to == OWNER] == [f"{DAILY_CEILING_ALERT_PREFIX}20"]


def test_a_second_order_the_same_day_over_the_ceiling_does_not_page_kevin_again():
    p, store, emails_sent = build_pipeline(limit=20)
    for i in range(21):
        p.admit(paid_order(f"o{i}"))
    emails_sent.clear()
    over = paid_order("o21")
    assert p.admit(over) is False
    assert over.status == "failed_refunded"
    assert store.killswitch is True
    assert [b for to, b in emails_sent if to == OWNER] == []


def test_no_ceiling_configured_always_admits():
    """Cold start: an unwired deployment (order_ceiling left at its default None)
    must not crash trying to consult a ceiling it was never given -- same convention
    as owner_email=None in task 41."""
    p, store, emails_sent = build_pipeline(ceiling=False)
    for i in range(25):
        assert p.admit(paid_order(f"o{i}")) is True
    assert store.killswitch is False


def test_the_ceiling_resets_on_a_new_utc_day():
    """The likeliest break in a 'per UTC day' counter: failing to roll over."""
    clock = {"t": 0.0}
    p, store, emails_sent = build_pipeline(limit=1, now=lambda: clock["t"])
    assert p.admit(paid_order("day1-a")) is True
    assert p.admit(paid_order("day1-b")) is False
    clock["t"] += 86400
    assert p.admit(paid_order("day2-a")) is True


# ---------------------------------------------------------------- refund-rate alarm


def test_three_refunds_in_one_day_page_kevin_once_with_ids_and_reasons():
    p, store, emails_sent = build_pipeline(model=failing_model(), ceiling=False)
    for oid in ("o1", "o2", "o3"):
        store.put(paid_order(oid))
        order = p.run(oid)
        assert order.status == "failed_refunded"
    owner_emails = [b for to, b in emails_sent if to == OWNER]
    assert len(owner_emails) == 1
    assert owner_emails[0].startswith(REFUND_ALARM_PREFIX)
    body = owner_emails[0].removeprefix(REFUND_ALARM_PREFIX)
    assert body.count(":undeliverable") == 3


def test_the_fourth_refund_the_same_day_does_not_page_kevin_again():
    p, store, emails_sent = build_pipeline(model=failing_model(), ceiling=False)
    for oid in ("o1", "o2", "o3", "o4"):
        store.put(paid_order(oid))
        p.run(oid)
    owner_emails = [b for to, b in emails_sent if to == OWNER]
    assert len(owner_emails) == 1


def test_fewer_than_three_refunds_never_pages_kevin():
    p, store, emails_sent = build_pipeline(model=failing_model(), ceiling=False)
    for oid in ("o1", "o2"):
        store.put(paid_order(oid))
        p.run(oid)
    assert [b for to, b in emails_sent if to == OWNER] == []


def test_refund_alarm_does_not_touch_the_kill_switch():
    p, store, emails_sent = build_pipeline(model=failing_model(), ceiling=False)
    for oid in ("o1", "o2", "o3"):
        store.put(paid_order(oid))
        p.run(oid)
    assert store.killswitch is False


def test_no_owner_email_configured_still_tallies_and_does_not_crash():
    p, store, emails_sent = build_pipeline(model=failing_model(), ceiling=False, owner_email=None)
    for oid in ("o1", "o2", "o3"):
        store.put(paid_order(oid))
        order = p.run(oid)
        assert order.status == "failed_refunded"
    assert emails_sent  # customer refund emails still went out
    assert [b for to, b in emails_sent if b.startswith(REFUND_ALARM_PREFIX)] == []


def test_refund_alarm_names_each_orders_own_reason():
    """Held-out: the refunds that trip the alarm can come from different causes (an
    ordinary undeliverable order, then one over the daily ceiling) -- the alarm must
    not relabel every entry with the same word."""
    p, store, emails_sent = build_pipeline(model=failing_model(), limit=1)
    store.put(paid_order("o1"))
    p.run("o1")  # undeliverable
    assert p.admit(paid_order("o2")) is True  # spends the ceiling's one slot
    over = paid_order("o3")
    assert p.admit(over) is False  # daily_ceiling
    store.put(paid_order("o4"))
    p.run("o4")  # undeliverable -- third refund of the day, fires the alarm

    owner_emails = [b for to, b in emails_sent if to == OWNER and b.startswith(REFUND_ALARM_PREFIX)]
    assert len(owner_emails) == 1
    body = owner_emails[0].removeprefix(REFUND_ALARM_PREFIX)
    assert ":undeliverable" in body
    assert ":daily_ceiling" in body


# ---------------------------------------------------------------- wiring: where the
# ---------------------------------------------------------------- ceiling actually sits


def build_app(limit=20):
    store = OrderStore()
    emails_sent: list[tuple[str, str]] = []
    ceiling = DailyOrderCeiling(counter=MemoryCounter(), limit=limit)
    pipeline = Pipeline(
        store=store,
        model=working_model(),
        storage=fake_storage(),
        send_email=lambda to, body: emails_sent.append((to, body)),
        refund=lambda order_id, cents: Refund(id="re_1", status="succeeded"),
        track_conversion=lambda o: None,
        secret=APP_SECRET,
        owner_email=OWNER,
        order_ceiling=ceiling,
    )

    def retrieve_session(session_id):
        return {
            "id": session_id,
            "payment_status": "paid",
            "customer_details": {"email": "cliente@example.com"},
            "metadata": {"source_urls": "gs://src/a.jpg", "style": "corporativo"},
            "amount_total": 1999,
        }

    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter()),
        enqueue=lambda order_id: None,
        preview_fn=lambda files, batch: "",
        webhook_secret="whsec",
        tasks_token="tt",
        retrieve_session=retrieve_session,
        sign_url=lambda url: url,
    )
    return TestClient(app, follow_redirects=False), store, emails_sent


def test_the_21st_paid_session_through_the_post_payment_redirect_is_refunded_not_generated():
    """The wiring proof named in the task: 20 sessions fulfilled through the actual
    post-payment redirect (THANKS_PATH, the same route Stripe sends a real browser
    to) are admitted exactly as before; the 21st is refunded and never enqueued --
    caught at _fulfil_session, the single place both the webhook and the redirect
    turn a paid session into an Order, not earlier at /api/checkout, which costs
    nothing to hit and proves nothing was paid."""
    c, store, emails_sent = build_app(limit=20)
    for i in range(20):
        sid = f"cs_test_{i:02d}"
        r = c.get(THANKS_PATH, params={"session_id": sid})
        assert r.status_code == 302
        assert store.get(sid).status == "paid"  # queued for generation, not refunded

    sid21 = "cs_test_20"
    r = c.get(THANKS_PATH, params={"session_id": sid21})
    assert r.status_code == 302  # still a clear redirect, never a raw error page
    order = store.get(sid21)
    assert order.status == "failed_refunded"
    assert order.outputs == []
    assert store.killswitch is True
    assert [b for to, b in emails_sent if to == OWNER] == [f"{DAILY_CEILING_ALERT_PREFIX}20"]


def test_a_stripe_webhook_retry_for_the_refused_session_is_a_harmless_duplicate():
    """A refused order is still stored (as failed_refunded), so Stripe retrying the
    same checkout.session.completed event lands on the existing idempotency guard
    instead of trying to refund it a second time."""
    c, store, emails_sent = build_app(limit=1)
    c.get(THANKS_PATH, params={"session_id": "cs_test_00"})
    c.get(THANKS_PATH, params={"session_id": "cs_test_01"})  # refused, refunded
    before = len(emails_sent)
    c.get(THANKS_PATH, params={"session_id": "cs_test_01"})  # redelivered link, e.g. back button
    assert len(emails_sent) == before  # no second refund, no second owner page


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
