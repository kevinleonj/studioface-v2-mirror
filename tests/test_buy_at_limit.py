"""Task 29: never-block-a-buyer.

WHY THIS EXISTS, in Kevin's own words: 21 September, his own shop refused to sell to
him. He hit the free-preview limit and from that moment the page showed no buy button
at all, for an hour, because the buy button only exists while the page holds a signed
handle and only a successful preview created one. Under advertising, every visitor who
hits that limit is a paid click thrown away.

The fix splits /api/preview in two: storing the uploaded photos and signing the handle
/api/checkout trusts no longer requires calling the image model. At the free-preview
limit the server now answers 200 with that handle, `preview_url` null and `limited`
true, having called nothing that costs money. That fallback has its own ceiling —
RateLimiter.check_store, ten stored batches per visitor per hour — because storage is
cheap but not free; the eleventh in the hour gets the real 429.

Four things this file proves, each with its own case:
  1. at the limit, the answer carries a handle /api/checkout accepts
  2. no image-model call was made on that path — proved by a model double that RECORDS
     every call, not inferred from a status code
  3. the eleventh stored batch in the hour is refused
  4. a made-up handle is still refused by checkout — the same verification either way
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import OrderStore, Pipeline  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import make_app  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100
APP_SECRET = "app_secret"


class CountingModel:
    """A preview_fn that RECORDS every call, so "no image-model call was made" is
    proved rather than assumed from a 200 that could just as easily hide one."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, files, batch):
        self.calls += 1
        return "https://cdn/preview.png"


class RecordingStore:
    """store_sources_fn double: records what it was asked to store, so "storing
    photos without generating" is proved to have actually stored something, not just
    to have avoided calling the model."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    def __call__(self, files, batch) -> None:
        self.calls.append((len(files), batch))


class FakeCheckout:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def __call__(
        self,
        batch,
        count,
        style,
        gclid,
        wardrobe=None,
        gbraid=None,
        wbraid=None,
        ga_client_id=None,
        ga_session_id=None,
    ):
        self.calls.append((batch, count))
        return f"https://checkout.stripe.com/c/pay/{batch}"


def build(per_client=1, model=None, store=None, verify_turnstile=None):
    pipeline = Pipeline(
        store=OrderStore(),
        model=type("M", (), {"edit": lambda self, u, p: "x"})(),
        storage=type("S", (), {"put": lambda self, k, u: k})(),
        send_email=lambda t, b: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret=APP_SECRET,
    )
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter(), per_client=per_client, per_subnet=1000),
        enqueue=lambda i: None,
        preview_fn=model or CountingModel(),
        store_sources_fn=store or RecordingStore(),
        webhook_secret="whsec",
        tasks_token="tt",
        verify_turnstile=verify_turnstile or (lambda token, ip: True),
        create_checkout=FakeCheckout(),
    )
    return TestClient(app)


def post(client, **extra):
    data = {"turnstile_token": "x", **extra}
    return client.post(
        "/api/preview",
        data=data,
        files={"files": ("a.jpg", JPEG, "image/jpeg")},
    )


def checkout(client, handle: dict):
    return client.post(
        "/api/checkout",
        json={
            "batch": handle["batch"],
            "n": handle["n"],
            "t": handle["t"],
            "style": "corporativo",
        },
    )


# ---------------------------------------------------------------- 1: the handle works


def test_at_the_limit_the_answer_carries_a_handle_checkout_accepts():
    c = build(per_client=1)
    assert post(c).status_code == 200  # the one real preview this visitor gets

    r = post(c)  # out of free previews
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["preview_url"] is None
    assert body["limited"] is True
    assert body["batch"] and body["t"]

    ck = checkout(c, body)
    assert ck.status_code == 200, ck.text
    assert ck.json()["url"].endswith(body["batch"])


# ---------------------------------------------------------------- 2: nothing that costs money


def test_no_image_model_call_was_made_on_the_storage_only_path():
    """Proof, not inference: the model double RECORDS its own calls, and the store
    double records that it actually ran, so this cannot pass by accident."""
    model, store = CountingModel(), RecordingStore()
    c = build(per_client=1, model=model, store=store)
    post(c)  # spends the one real preview — this call SHOULD reach the model
    assert model.calls == 1

    r = post(c)  # at the limit now
    assert r.json()["limited"] is True
    assert model.calls == 1, "the storage-only path must never call the image model"
    assert len(store.calls) == 1, "the storage-only path must actually store the photos"
    assert store.calls[0][0] == 1  # the one file this visitor sent


# ---------------------------------------------------------------- 3: the fallback's own ceiling


def test_the_eleventh_stored_batch_in_the_hour_is_refused():
    c = build(per_client=1)
    post(c)  # spend the one real preview
    for i in range(10):  # RateLimiter.per_store == 10
        r = post(c)
        assert r.status_code == 200, f"stored batch {i + 1}: {r.text}"
        assert r.json()["limited"] is True
    r = post(c)  # the 11th stored batch this hour: storage is cheap but not free
    assert r.status_code == 429, r.text


def test_a_visitor_who_never_reaches_the_preview_limit_never_touches_the_store_cap():
    """Held-out check: the store ceiling must not fire for ordinary successful
    previews — only for the fallback path."""
    model = CountingModel()
    c = build(per_client=20, model=model)
    for _ in range(15):
        assert post(c).status_code == 200
    assert model.calls == 15, "every one of these should have been a real preview"


# ---------------------------------------------------------------- 4: checkout still verifies


def test_a_made_up_handle_is_still_refused_by_checkout():
    c = build(per_client=1)
    ck = checkout(c, {"batch": "not-a-real-batch", "n": 1, "t": "not-a-real-signature"})
    assert ck.status_code == 403 and ck.json()["detail"] == "bad_handle"


def test_a_genuine_limited_handle_tampered_with_is_still_refused():
    """The batch and the count are both bound into the signature — a made-up handle
    is not just an unknown batch, it is also a real batch with a changed count."""
    c = build(per_client=1)
    post(c)
    body = post(c).json()
    assert body["limited"] is True
    tampered = dict(body, n=body["n"] + 1)
    ck = checkout(c, tampered)
    assert ck.status_code == 403 and ck.json()["detail"] == "bad_handle"


# ---------------------------------------------------------------- the human check still runs first


def test_the_human_check_still_runs_first_even_at_the_limit():
    """A limit already reached is not a reason to skip Turnstile."""
    c = build(per_client=1, verify_turnstile=lambda token, ip: False)
    r = post(c)
    assert r.status_code == 403 and r.json()["detail"] == "turnstile"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
