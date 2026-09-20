"""The four images of an order are generated concurrently, with four different
prompts, inside the same retry budget as the sequential version.

Concurrency here is a thread pool, not asyncio: fal_client.subscribe is blocking,
/internal/generate is a sync FastAPI route (so it already runs in a worker thread),
and an async path would have forced the ImageModel port and every test that uses it
to become async for no gain. fal_client.subscribe_async exists if that changes.
"""

import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import Order, OrderStore, Pipeline, sequential_batch, threaded_batch  # noqa: E402


class RecordingModel:
    def __init__(self, delay=0.0, fail_first=0, always_fail=False):
        self.prompts, self.calls, self.lock = [], 0, threading.Lock()
        self.delay, self.fail_first, self.always_fail = delay, fail_first, always_fail
        self.peak, self._live = 0, 0

    def edit(self, image_urls, prompt):
        with self.lock:
            self.calls += 1
            self._live += 1
            self.peak = max(self.peak, self._live)
            n = self.calls
            self.prompts.append(prompt)
        time.sleep(self.delay)
        with self.lock:
            self._live -= 1
        if self.always_fail or n <= self.fail_first:
            raise RuntimeError("fal 500")
        return f"https://fal.media/{n}.jpg"


class Storage:
    def put(self, key, url):
        return f"gs://out/{key}"


def build(model, **kw):
    store = OrderStore()
    emails, refunds = [], []
    p = Pipeline(
        store=store,
        model=model,
        storage=Storage(),
        send_email=lambda to, b: emails.append((to, b)),
        refund=lambda o, c: refunds.append((o, c)),
        track_conversion=lambda o: None,
        secret="app",
        **kw,
    )
    store.put(
        Order(
            id="o1",
            email="k@example.com",
            source_image_urls=["gs://src/a.jpg"],
            style="corporativo",
            amount_cents=1999,
        )
    )
    return p, emails, refunds


# ---------------------------------------------------------------- the batch runners


def test_sequential_batch_empty_list():
    assert sequential_batch([]) == []


def test_threaded_batch_empty_list():
    assert threaded_batch([]) == []


def test_threaded_batch_preserves_order_not_completion_order():
    """The slowest job is first; its result must still come back first."""
    delays = [0.20, 0.01, 0.01, 0.01]

    def job(i):
        def run():
            time.sleep(delays[i])
            return f"r{i}"

        return run

    assert threaded_batch([job(i) for i in range(4)]) == ["r0", "r1", "r2", "r3"]


def test_threaded_batch_reports_a_failure_as_none_without_losing_the_others():
    def boom():
        raise RuntimeError("fal 500")

    assert threaded_batch([lambda: "a", boom, lambda: "c"]) == ["a", None, "c"]


def test_threaded_batch_actually_overlaps():
    """Four 0.15 s jobs sequentially take 0.6 s. Concurrently they take about 0.15 s."""
    started = time.monotonic()
    out = threaded_batch([lambda: (time.sleep(0.15), "x")[1] for _ in range(4)])
    elapsed = time.monotonic() - started
    assert out == ["x"] * 4
    assert elapsed < 0.35, f"took {elapsed:.2f}s, so the jobs did not overlap"


# ---------------------------------------------------------------- the pipeline


def test_four_images_are_generated_concurrently():
    model = RecordingModel(delay=0.15)
    p, *_ = build(model, run_batch=threaded_batch)
    started = time.monotonic()
    order = p.run("o1")
    elapsed = time.monotonic() - started
    assert order.status == "delivered" and len(order.outputs) == 4
    assert model.peak == 4, f"only {model.peak} fal calls were ever in flight at once"
    assert elapsed < 0.45, f"took {elapsed:.2f}s, so the four calls were serialised"


def test_each_image_gets_a_different_prompt():
    """The four outputs must be four different photos, not the same prompt four times."""
    model = RecordingModel()
    p, *_ = build(model, run_batch=threaded_batch)
    p.run("o1")
    assert len(set(model.prompts)) == 4
    for prompt in model.prompts:
        assert "Keep the exact same face" in prompt


def test_concurrent_retries_stay_inside_the_same_budget():
    model = RecordingModel(fail_first=2)
    p, *_ = build(model, run_batch=threaded_batch)
    order = p.run("o1")
    assert order.status == "delivered"
    assert len(order.outputs) == 4
    assert order.attempts == 6  # 2 wasted + 4 good, exactly as the sequential version


def test_total_outage_still_refunds_and_never_exceeds_the_budget():
    model = RecordingModel(always_fail=True)
    p, emails, refunds = build(model, run_batch=threaded_batch)
    order = p.run("o1")
    assert order.status == "failed_refunded"
    assert refunds == [("o1", 1999)]
    assert model.calls == 8  # n_images + extra_attempts, never more
    assert order.outputs == []


def test_output_keys_are_unique_and_jpeg():
    """Held-out check: four threads finishing at once must not race to the same key
    and overwrite each other — the customer would pay for four identical photos."""
    model = RecordingModel(delay=0.02)
    p, *_ = build(model, run_batch=threaded_batch)
    order = p.run("o1")
    assert len(set(order.outputs)) == 4
    assert order.outputs == [f"gs://out/o1/{i}.jpg" for i in range(4)]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
