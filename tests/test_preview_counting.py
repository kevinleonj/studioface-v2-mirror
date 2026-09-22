"""Task 28: a visitor's hourly tries must be spent only on previews the image model
actually produced.

WHY THIS EXISTS, measured in Kevin's own browser, 21 September: a reviewer uploaded
one empty file, the server refused it, then a good photo — and the shop answered "you
have used your free tries". The order was human check, THEN count, THEN validate: an
upload the server was always going to refuse still spent one of the visitor's two
hourly tries before it ever reached `validate_uploads`.

Fixed order (app/main.py `_register_preview`): human check, validate the files, and
ONLY THEN count. Counting itself is `RateLimiter.check` — unchanged, still the single
atomic check-and-increment it always was, called BEFORE the model runs. If the model
then refuses or fails, `RateLimiter.refund` (app/guards.py) gives the try back. That
design, and why "count only after success" was not chosen instead (it needs a
non-atomic peek before the model runs, which reopens the exact race two requests both
seeing "2 used" and both proceeding, at real fal cost), is argued in guards.py's
`refund` docstring and HANDOFF.md, task 28.

The twin every one of these needs: the third successful preview inside the hour must
still get the limit answer, proving the fix does not simply stop counting altogether.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import ModelRefused, OrderStore, Pipeline  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import make_app  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100
EMPTY = b""


class ScriptedModel:
    """A preview_fn that plays back one outcome per call, so a test can make the
    SAME client succeed on one attempt and be refused on the next — exactly the
    sequence a refund has to survive."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, files, batch):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def build(preview_fn, per_client=2):
    pipeline = Pipeline(
        store=OrderStore(),
        model=type("M", (), {"edit": lambda self, u, p: "x"})(),
        storage=type("S", (), {"put": lambda self, k, u: k})(),
        send_email=lambda t, b: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret="app",
    )
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter(), per_client=per_client, per_subnet=1000),
        enqueue=lambda i: None,
        preview_fn=preview_fn,
        webhook_secret="whsec",
        tasks_token="tt",
        verify_turnstile=lambda token, ip: True,
    )
    return TestClient(app)


def post(client, data=JPEG):
    return client.post(
        "/api/preview",
        data={"turnstile_token": "x"},
        files={"files": ("a.jpg", data, "image/jpeg")},
    )


def test_an_invalid_file_does_not_reduce_the_remaining_tries():
    """The bug itself: an upload the server refuses must not spend a try. Refusing an
    empty file three times over, with only one try in the whole hour, must still leave
    that one try to spend on a real, valid photo."""
    c = build(ScriptedModel("https://cdn/preview.png"), per_client=1)
    for _ in range(3):
        r = post(c, data=EMPTY)
        assert r.status_code == 422, r.text
        assert "unsupported_type" in r.text
    r = post(c, data=JPEG)  # the one try must still be there
    assert r.status_code == 200, r.text


def test_a_model_refusal_does_not_reduce_the_remaining_tries():
    """fal saying no to a real, valid photo is not the visitor spending a try either —
    only a preview the model actually produced counts."""
    c = build(
        ScriptedModel(ModelRefused("content_policy"), "https://cdn/preview.png"),
        per_client=1,
    )
    r = post(c)
    assert r.status_code == 422 and r.json()["detail"] == "content_policy"
    r = post(c)  # the refund must have given the one try back
    assert r.status_code == 200, r.text


def test_a_successful_preview_does_reduce_the_remaining_tries():
    """Task 29: a spent try no longer means a 429. /api/preview stores the photos
    and signs a handle instead of calling the model again — the shop still sells.
    tests/test_buy_at_limit.py is the dedicated proof of that path; this test's own
    job is still what its name says: the try was in fact spent."""
    c = build(ScriptedModel("https://cdn/preview.png"), per_client=1)
    assert post(c).status_code == 200
    r = post(c)  # no tries left — this one was a real, billed generation
    assert r.status_code == 200, r.text
    assert r.json()["limited"] is True and r.json()["preview_url"] is None


def test_the_third_successful_preview_inside_the_hour_is_refused():
    """The twin. Two successes must still leave the cap standing, not just the
    accounting: a third attempt must never reach the model at all — task 29 answers
    it from the storage-only path instead, never a third `model.edit` call."""
    model = ScriptedModel(*(["https://cdn/preview.png"] * 2))
    c = build(model, per_client=2)
    for _ in range(2):
        assert post(c).status_code == 200
    r = post(c)
    assert r.status_code == 200, r.text
    assert r.json()["limited"] is True and r.json()["preview_url"] is None
    assert model.calls == 2, "the third attempt must never have reached the model"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
