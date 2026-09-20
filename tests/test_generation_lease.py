"""A retry must not start a second generation while the first is still running.

Reported from the outside as "the mail is triggering before completion". From the
inside it is worse than that.

The replay guard was `if order.status in DONE_STATUSES`, and DONE_STATUSES is
("delivered", "failed_refunded", "failed_refund_pending"). "generating" is not in it —
deliberately, because an order stuck in "generating" after a crashed worker has to be
recoverable or it stalls forever and nobody is refunded.

But Cloud Tasks retries on any non-2xx AND on its own dispatch deadline, and
/internal/generate takes one to three minutes of fal calls. So a retry arriving while
the first run is still working sails past the guard and starts a SECOND full generation
of the same order. That is four more paid fal calls, and two runs that each email the
customer when they finish — so the first email lands while the other run is still going.

The fix is a lease, not a lock. Claiming records `started_at`; a run that finds a FRESH
claim returns immediately and does no work, and the route turns that into a non-2xx so
Cloud Tasks backs off and comes again. A STALE claim is taken over, which is what stops
a killed worker from stranding an order that has been paid for. Neither case starts a
second concurrent run.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import LEASE_SECONDS, Order, OrderStore, Pipeline  # noqa: E402

PLACEHOLDER = "placeholder-value"


class CountingModel:
    def __init__(self):
        self.calls = 0

    def edit(self, urls, prompt):
        self.calls += 1
        return f"https://fal/{self.calls}.jpg"


def build(clock):
    store = OrderStore()
    model = CountingModel()
    emails: list[tuple[str, str]] = []
    pipeline = Pipeline(
        store=store,
        model=model,
        storage=type("S", (), {"put": lambda self, k, u: f"gs://out/{k}"})(),
        send_email=lambda to, body: emails.append((to, body)),
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret=PLACEHOLDER,
        now=clock,
    )
    return pipeline, store, model, emails


def an_order():
    return Order(
        id="cs_1",
        email="cliente@example.com",
        source_image_urls=["gs://src/a.jpg"],
        style="corporativo",
        amount_cents=1999,
    )


def claimed_one_second_ago():
    order = an_order()
    order.status = "generating"
    order.started_at = 999.0
    return order


# ---------------------------------------------------------------- the claim


def test_claiming_records_when_the_run_started():
    now = [1000.0]
    pipeline, store, _, _ = build(lambda: now[0])
    store.put(an_order())
    pipeline.run("cs_1")
    assert store.get("cs_1").started_at == 1000.0


def test_a_retry_arriving_mid_run_does_no_work_and_sends_nothing():
    """The money case. Four more paid fal calls for every spurious retry."""
    now = [1000.0]
    pipeline, store, model, emails = build(lambda: now[0])
    store.put(claimed_one_second_ago())

    returned = pipeline.run("cs_1")

    assert model.calls == 0, "a second generation started while the first was running"
    assert emails == [], "emailed the customer about a run it did not perform"
    assert returned.status == "generating"


def test_the_route_turns_a_held_lease_into_a_retry_rather_than_a_success():
    """Held-out check on the contract between run() and the HTTP layer. If the route
    ever answered 2xx for a held lease, Cloud Tasks would stop retrying and the order
    would be abandoned whenever the original worker had died."""
    from fastapi.testclient import TestClient

    from app.guards import MemoryCounter, RateLimiter
    from app.main import make_app

    now = [1000.0]
    pipeline, store, _, _ = build(lambda: now[0])
    store.put(claimed_one_second_ago())

    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter()),
        enqueue=lambda i: None,
        preview_fn=lambda f, b: "",
        webhook_secret="whsec",
        tasks_token="tt",
    )
    r = TestClient(app).post("/internal/generate/cs_1", headers={"X-Tasks-Token": "tt"})
    assert r.status_code >= 400, "a held lease must not look like success to Cloud Tasks"


# ---------------------------------------------------------------- the takeover


def test_a_stale_claim_is_taken_over_so_a_killed_worker_cannot_strand_an_order():
    """Why this is a lease and not a lock. Without the takeover a container killed
    mid-generation leaves the order at "generating" for ever: never delivered, never
    refunded, and the customer has paid."""
    now = [1000.0 + LEASE_SECONDS + 1]
    pipeline, store, model, emails = build(lambda: now[0])
    store.put(claimed_one_second_ago())

    returned = pipeline.run("cs_1")

    assert model.calls > 0, "a stale claim was never picked up"
    assert returned.status == "delivered"
    assert len(emails) == 1


def test_the_lease_is_long_enough_for_a_real_generation():
    """Four concurrent fal calls take one to three minutes. A lease shorter than that
    lets a retry take over a run that is merely still working, which is the exact
    double spend this file exists to prevent."""
    assert LEASE_SECONDS >= 300


# ---------------------------------------------------------------- unchanged


def test_a_finished_order_still_returns_early_and_emails_once():
    now = [1000.0]
    pipeline, store, _, emails = build(lambda: now[0])
    store.put(an_order())
    pipeline.run("cs_1")
    pipeline.run("cs_1")
    assert len(emails) == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
