"""Task 71 (daily-cap-alert). When a daily ceiling fires, nobody was told: under paid
ad traffic the shop can quietly stop serving free previews (RateLimiter.daily_global)
or stop taking paid orders (DailyOrderCeiling) while the ads that sent the traffic
keep spending. This adds the missing owner alert for the free-preview ceiling, and
puts it and the two existing daily alerts (the paid-order ceiling, the refund-rate
alarm) behind the exact same once-per-UTC-day gate.

That gate, `Pipeline._alert_once`, is the shared atomic Counter every ceiling in this
codebase already uses (`Counter.increment_if_below(key, limit=1, ttl_s)`), run inside
one Firestore transaction in production (app/adapters/firestore_counter.py). Of any
number of Cloud Run instances racing on the same key in the same instant, exactly one
`increment_if_below` call returns True; every other one -- on this instance or any
other -- returns False. Task 42's refund alarm used to decide "already emailed today"
with a set living in OrderStore's own process (`app/core.py`, before this task); a
second instance never saw it, so the alarm could fire twice from two instances or be
silently skipped after a restart. This file proves the replacement by making two
separate Pipeline instances (two OrderStores, standing in for two Cloud Run
containers) share one alert_counter and race the same threshold crossing.
"""

import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import emails  # noqa: E402
from app.core import (  # noqa: E402
    DAILY_CEILING_ALERT_PREFIX,
    DAILY_PREVIEW_CAP_ALERT_PREFIX,
    REFUND_ALARM_PREFIX,
    Order,
    OrderStore,
    Pipeline,
    Refund,
)
from app.guards import DailyOrderCeiling, MemoryCounter, RateLimiter  # noqa: E402
from app.main import make_app  # noqa: E402

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


def build_pipeline(model=None, owner_email=OWNER, now=None, alert_counter=None, order_ceiling=None):
    store = OrderStore()
    emails_sent: list[tuple[str, str]] = []
    clock = now or time.time
    p = Pipeline(
        store=store,
        model=model or working_model(),
        storage=fake_storage(),
        send_email=lambda to, body: emails_sent.append((to, body)),
        refund=lambda order_id, cents: Refund(id="re_1", status="succeeded"),
        track_conversion=lambda o: None,
        secret=APP_SECRET,
        owner_email=owner_email,
        now=clock,
        alert_counter=alert_counter if alert_counter is not None else MemoryCounter(now=clock),
        order_ceiling=order_ceiling,
    )
    return p, store, emails_sent


# ---------------------------------------------------------------- route: the free
# ---------------------------------------------------------------- preview ceiling


def build_app(daily_global=2, owner_email=OWNER, alert_counter=None):
    store = OrderStore()
    emails_sent: list[tuple[str, str]] = []
    counter = alert_counter if alert_counter is not None else MemoryCounter()
    pipeline = Pipeline(
        store=store,
        model=working_model(),
        storage=fake_storage(),
        send_email=lambda to, body: emails_sent.append((to, body)),
        refund=lambda order_id, cents: Refund(id="re_1", status="succeeded"),
        track_conversion=lambda o: None,
        secret=APP_SECRET,
        owner_email=owner_email,
        alert_counter=counter,
    )
    limiter = RateLimiter(
        counter=MemoryCounter(),
        per_client=1000,
        per_subnet=1000,
        daily_global=daily_global,
    )
    app = make_app(
        pipeline,
        limiter,
        enqueue=lambda order_id: None,
        preview_fn=lambda files, batch: "https://cdn/preview.png",
        webhook_secret="whsec",
        tasks_token="tt",
    )
    return TestClient(app), store, emails_sent


JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100


def preview(client, ip):
    return client.post(
        "/api/preview",
        data={"turnstile_token": "x"},
        files={"files": ("a.jpg", JPEG, "image/jpeg")},
        headers={"x-forwarded-for": ip},
    )


def test_the_preview_under_the_daily_ceiling_gets_through_with_no_alert():
    """Refused case's twin: nothing pages Kevin while the shop is still serving."""
    c, store, emails_sent = build_app(daily_global=2)
    r = preview(c, "203.0.113.1")
    assert r.status_code == 200
    assert r.json()["preview_url"] is not None
    assert [b for to, b in emails_sent if to == OWNER] == []


def test_the_preview_that_hits_the_daily_ceiling_is_refused_and_pages_kevin_with_the_count():
    """Real measured behaviour through the actual route: two previews spend the
    (deliberately tiny, for the test) daily_global budget of 2; the third, from a
    brand new visitor so it cannot be the per-client or per-subnet cap, still comes
    back 200 (never-block-a-buyer: it gets a stored handle, not a hard failure) but
    is the one that tells Kevin."""
    c, store, emails_sent = build_app(daily_global=2)
    assert preview(c, "203.0.113.1").status_code == 200
    assert preview(c, "203.0.114.1").status_code == 200
    r = preview(c, "203.0.115.1")
    assert r.status_code == 200
    assert r.json()["limited"] is True
    owner_emails = [b for to, b in emails_sent if to == OWNER]
    assert owner_emails == [f"{DAILY_PREVIEW_CAP_ALERT_PREFIX}2"]


def test_a_second_preview_over_the_same_days_ceiling_does_not_page_kevin_again():
    c, store, emails_sent = build_app(daily_global=1)
    assert preview(c, "203.0.113.1").status_code == 200
    preview(c, "203.0.114.1")  # first refusal, pages Kevin
    emails_sent.clear()
    preview(c, "203.0.116.1")  # second refusal, same UTC day
    assert [b for to, b in emails_sent if to == OWNER] == []


def test_no_owner_email_configured_the_ceiling_alert_does_not_crash():
    c, store, emails_sent = build_app(daily_global=1, owner_email=None)
    preview(c, "203.0.113.1")
    r = preview(c, "203.0.114.1")
    assert r.status_code == 200  # still never-blocks-a-buyer
    assert emails_sent == []


def test_two_instances_racing_the_same_days_preview_ceiling_still_page_kevin_once():
    """The property that actually matters under many Cloud Run instances: two
    Pipelines standing in for two containers, sharing the one alert_counter a real
    deployment shares through Firestore, both crossing the ceiling for the same UTC
    day. Only one of the two ever gets the atomic increment."""
    shared_counter = MemoryCounter()
    p1, _, emails1 = build_pipeline(alert_counter=shared_counter)
    p2, _, emails2 = build_pipeline(alert_counter=shared_counter)
    p1.note_daily_preview_cap(300)
    p2.note_daily_preview_cap(300)
    all_owner_emails = [b for to, b in emails1 + emails2 if to == OWNER]
    assert all_owner_emails == [f"{DAILY_PREVIEW_CAP_ALERT_PREFIX}300"]


def test_the_preview_ceiling_alert_fires_again_on_a_new_utc_day():
    clock = {"t": 0.0}
    p, _, emails_sent = build_pipeline(now=lambda: clock["t"])
    p.note_daily_preview_cap(300)
    clock["t"] += 86400
    p.note_daily_preview_cap(300)
    owner_emails = [b for to, b in emails_sent if to == OWNER]
    assert owner_emails == [
        f"{DAILY_PREVIEW_CAP_ALERT_PREFIX}300",
        f"{DAILY_PREVIEW_CAP_ALERT_PREFIX}300",
    ]


# ---------------------------------------------------------------- the email body


def test_daily_preview_cap_alert_maps_to_a_real_email_naming_the_count():
    message = emails.for_body(f"{DAILY_PREVIEW_CAP_ALERT_PREFIX}300")
    assert "300" in message.subject or "300" in message.text
    assert "preview" in message.text.lower()


def test_the_two_daily_preview_cap_prefixes_agree():
    assert DAILY_PREVIEW_CAP_ALERT_PREFIX == emails.DAILY_PREVIEW_CAP_ALERT_PREFIX


# ---------------------------------------------------------------- the paid-order
# ---------------------------------------------------------------- ceiling, same gate


def test_two_instances_racing_the_same_days_order_ceiling_still_page_kevin_once():
    """Same race, for the OTHER trigger the task names: the daily order ceiling.
    Two Pipelines share one alert_counter and one Firestore-style order_ceiling
    counter (a real deployment shares both through Firestore the same way); both see
    order 21 the moment the 20th has already landed, both refuse and refund it, but
    the atomic alert_counter still lets only one of them send."""
    shared_alert_counter = MemoryCounter()
    shared_order_counter = MemoryCounter()
    ceiling1 = DailyOrderCeiling(counter=shared_order_counter, limit=1)
    ceiling2 = DailyOrderCeiling(counter=shared_order_counter, limit=1)
    p1, store1, emails1 = build_pipeline(alert_counter=shared_alert_counter, order_ceiling=ceiling1)
    p2, store2, emails2 = build_pipeline(alert_counter=shared_alert_counter, order_ceiling=ceiling2)
    assert p1.admit(paid_order("o1")) is True  # spends the one shared slot
    assert p2.admit(paid_order("o2")) is False  # instance 2 sees it already spent
    assert p1.admit(paid_order("o3")) is False  # instance 1 also refuses now
    all_owner_emails = [b for to, b in emails1 + emails2 if to == OWNER]
    assert all_owner_emails == [f"{DAILY_CEILING_ALERT_PREFIX}1"]


# ---------------------------------------------------------------- the refund alarm,
# ---------------------------------------------------------------- moved off the
# ---------------------------------------------------------------- in-process set


def test_two_instances_racing_the_same_days_refund_alarm_still_page_kevin_once():
    """The bug this task fixes, reproduced directly: before this task, "already
    emailed today" lived in a set on OrderStore (app/core.py's old
    `_refund_alarmed`), which a second instance's own OrderStore never saw -- two
    instances could each independently reach 3 refunds and each send its own alert.
    Here p1 and p2 are two separate OrderStores (so their tallies do not share
    entries, exactly like two Cloud Run containers would not) but one shared
    alert_counter, exactly like two containers sharing one Firestore project would."""
    shared_counter = MemoryCounter()
    p1, store1, emails1 = build_pipeline(model=failing_model(), alert_counter=shared_counter)
    p2, store2, emails2 = build_pipeline(model=failing_model(), alert_counter=shared_counter)
    for oid in ("a1", "a2", "a3"):
        store1.put(paid_order(oid))
        p1.run(oid)
    for oid in ("b1", "b2", "b3"):
        store2.put(paid_order(oid))
        p2.run(oid)
    all_owner_emails = [b for to, b in emails1 + emails2 if to == OWNER]
    refund_alarms = [b for b in all_owner_emails if b.startswith(REFUND_ALARM_PREFIX)]
    assert len(refund_alarms) == 1


def test_fewer_than_three_refunds_on_one_instance_still_never_pages_kevin():
    """Refused case's twin for the refund alarm too: under threshold, still silent."""
    p, store, emails_sent = build_pipeline(model=failing_model())
    for oid in ("o1", "o2"):
        store.put(paid_order(oid))
        p.run(oid)
    assert [b for to, b in emails_sent if to == OWNER] == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
