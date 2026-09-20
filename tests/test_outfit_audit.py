"""O12: one order previewed a navy blazer and delivered four light blue shirts.

The report says the prompt text is identical, so the model is the accused. This file
refuses to answer from the template. It captures the ARGUMENTS DICT our code actually
hands fal, once for a preview and once for each delivered photo, and diffs them.

WHY NOT LOGS. Cloud Run keeps the request line and nothing else useful:

    gcloud logging read '... jsonPayload.logger="app.adapters.fal"' --freshness=30d
    -> no entries at all

and even a full log could not settle it, because `app/adapters/fal.py` logs
`application`, `resolution`, `len(readable)` and a latency and never the prompt, the
aspect ratio, the seed or the wardrobe. A question the logs cannot answer is a gap in
the logs; it is recorded in docs/audit/outfit-2026-09-20.md, not papered over here.

WHAT IS FAKE. Only things that open a socket: fal, Stripe, Resend, Cloud Storage,
Firestore, Cloud Tasks, and the one Firestore TRANSACTION behind the rate limiter
(`FakeFirestore` does not implement transactions). The composition is the real
`app.entry.build()`, the walk is the real HTTP funnel - preview, checkout, webhook,
/internal/generate - and the photo is the real fixture face.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import sys
import time
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_entry_builds import ENV, _Credentials  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "faces" / "face.jpg"
# The garment the four delivered photographs were wearing, as reported.
CHOSEN = "camisa-azul"


class _Blob:
    def __init__(self, uri: str, objects: dict) -> None:
        self.uri, self.objects = uri, objects

    def upload_from_string(self, data, content_type=None) -> None:
        self.objects[self.uri] = data

    def generate_signed_url(self, **kwargs) -> str:
        path = self.uri.removeprefix("gs://")
        return f"https://storage.googleapis.com/{path}?X-Goog-Signature=sig"


def _storage_doubles(objects: dict):
    class Bucket:
        def __init__(self, name: str) -> None:
            self.name = name

        def blob(self, key: str) -> _Blob:
            return _Blob(f"gs://{self.name}/{key}", objects)

    class Client:
        def __init__(self, *a, **k) -> None:
            pass

        def bucket(self, name: str) -> Bucket:
            return Bucket(name)

    class Blob:
        @staticmethod
        def from_uri(uri: str, client=None) -> _Blob:
            return _Blob(uri, objects)

    return Client, Blob


class _Response:
    """Turnstile says yes, GA4 accepts, and fal's result file downloads."""

    status_code = 200
    content = b"\xff\xd8jpeg"

    def json(self) -> dict:
        return {"success": True}


def _fal_double(captured: list) -> types.ModuleType:
    module = types.ModuleType("fal_client")

    def subscribe(application, arguments=None, **kwargs):
        captured.append({"application": application, "arguments": copy.deepcopy(arguments)})
        return {"images": [{"url": f"https://v3b.fal.media/{len(captured)}.jpg"}]}

    module.subscribe = subscribe
    return module


def _stripe_double(sessions: list) -> types.ModuleType:
    stripe = types.ModuleType("stripe")
    stripe.api_key = ""
    stripe.InvalidRequestError = type("InvalidRequestError", (Exception,), {})

    def create(**kwargs):
        sessions.append(kwargs)
        return types.SimpleNamespace(url="https://checkout.stripe.com/c/pay/x")

    stripe.checkout = types.SimpleNamespace(
        Session=types.SimpleNamespace(create=create, retrieve=lambda i: None)
    )
    stripe.Refund = types.SimpleNamespace(create=lambda **k: None)
    stripe.Webhook = types.SimpleNamespace()
    return stripe


def _patch_boundaries(monkeypatch, captured: list, sessions: list) -> None:
    import google.auth
    import httpx
    from fake_firestore import FakeFirestore
    from google.cloud import firestore as real_firestore
    from google.cloud import storage as real_storage

    client_cls, blob_cls = _storage_doubles({})
    monkeypatch.setattr(google.auth, "default", lambda *a, **k: (_Credentials(), "sf"))
    monkeypatch.setattr(real_storage, "Client", client_cls)
    monkeypatch.setattr(real_storage, "Blob", blob_cls)
    db = FakeFirestore()
    monkeypatch.setattr(real_firestore, "Client", lambda *a, **k: db)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Response())
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Response())
    monkeypatch.setitem(sys.modules, "fal_client", _fal_double(captured))
    monkeypatch.setitem(sys.modules, "stripe", _stripe_double(sessions))
    resend = types.ModuleType("resend")
    resend.api_key = ""
    resend.Emails = types.SimpleNamespace(send=lambda payload: {"id": "e"})
    monkeypatch.setitem(sys.modules, "resend", resend)
    # The rate limiter's counter is a Firestore TRANSACTION, which the fake cannot do.
    monkeypatch.setattr(
        "app.adapters.firestore_counter.FirestoreCounter.increment_if_below",
        lambda self, key, limit, ttl_s: True,
    )


def _sign(body: bytes, secret: str) -> str:
    ts = str(int(time.time()))
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


@pytest.fixture
def walk(monkeypatch):
    """Run the real funnel end to end and hand back every fal request it made."""
    from fastapi.testclient import TestClient

    captured: list = []
    sessions: list = []
    monkeypatch.delenv("GCP_PROJECT", raising=False)
    monkeypatch.delitem(sys.modules, "app.entry", raising=False)
    _patch_boundaries(monkeypatch, captured, sessions)

    from app import entry

    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(entry, "_enqueue_factory", lambda s: lambda order_id: None)
    client = TestClient(entry.build())

    def run(wardrobe: str | None, order_id: str) -> tuple[dict, list[dict]]:
        captured.clear()
        handle = client.post(
            "/api/preview",
            data={"turnstile_token": "t"},
            files={"files": ("face.jpg", FIXTURE.read_bytes(), "image/jpeg")},
        ).json()
        assert "batch" in handle, handle
        client.post(
            "/api/checkout",
            json={**handle, "style": "corporativo", "wardrobe": wardrobe},
        )
        _fulfil(client, sessions[-1]["metadata"], order_id)
        return captured[0], captured[1:]

    return run


def _fulfil(client, metadata: dict, order_id: str) -> None:
    """What Stripe and Cloud Tasks do next, through the real routes."""
    session = {
        "id": order_id,
        "metadata": metadata,
        "customer_details": {"email": "cliente@example.es"},
        "amount_total": 1900,
        "payment_status": "paid",
    }
    body = json.dumps(
        {"id": f"evt_{order_id}", "type": "checkout.session.completed", "data": {"object": session}}
    ).encode()
    posted = client.post(
        "/api/stripe/webhook",
        content=body,
        headers={"Stripe-Signature": _sign(body, ENV["STRIPE_WEBHOOK_SECRET"])},
    )
    assert posted.status_code == 200, posted.text
    done = client.post(
        f"/internal/generate/{order_id}", headers={"X-Tasks-Token": ENV["TASKS_TOKEN"]}
    )
    assert done.json() == {"status": "delivered"}, done.text


SAME_FIELDS = ("image_urls", "aspect_ratio", "output_format")


def test_the_walk_asks_fal_once_for_the_preview_and_four_times_for_the_delivery(walk):
    preview, delivered = walk(CHOSEN, "cs_test_audit_chosen")
    assert preview and len(delivered) == 4


def test_the_model_id_is_the_same_in_both_requests(walk):
    preview, delivered = walk(CHOSEN, "cs_test_audit_chosen")
    assert {r["application"] for r in [preview, *delivered]} == {"fal-ai/nano-banana-2/edit"}


def test_the_reference_photos_aspect_and_format_are_the_same(walk):
    """Same objects, same order, same frame shape. None of these can change an outfit."""
    preview, delivered = walk(CHOSEN, "cs_test_audit_chosen")
    for request in delivered:
        for field in SAME_FIELDS:
            assert request["arguments"][field] == preview["arguments"][field], field


def test_neither_request_pins_a_seed_or_asks_for_more_than_one_image(walk):
    """Absent from both: a preview can never be the same photograph twice over."""
    preview, delivered = walk(CHOSEN, "cs_test_audit_chosen")
    for request in [preview, *delivered]:
        assert "seed" not in request["arguments"]
        assert "num_images" not in request["arguments"]


def test_the_resolution_is_the_only_deliberate_difference(walk):
    preview, delivered = walk(CHOSEN, "cs_test_audit_chosen")
    assert preview["arguments"]["resolution"] == "0.5K"
    assert {r["arguments"]["resolution"] for r in delivered} == {"1K"}


def test_a_chosen_garment_is_the_whole_of_the_prompt_difference(walk):
    """The accusation is "identical prompt". It is not identical, and this names the
    words that differ: the clothing clause, which the customer picked."""
    from app.guards import STYLES, WARDROBES

    preview, delivered = walk(CHOSEN, "cs_test_audit_chosen")
    assert STYLES["corporativo"]["wardrobe"] in preview["arguments"]["prompt"]
    for request in delivered:
        assert WARDROBES[CHOSEN]["prompt"] in request["arguments"]["prompt"]
        assert STYLES["corporativo"]["wardrobe"] not in request["arguments"]["prompt"]


def test_with_the_selector_untouched_the_preview_prompt_is_the_delivered_prompt(walk):
    """The invariant that matters. If a customer changes nothing, what they were shown
    and what they are sold must be the same request but for resolution and framing."""
    preview, delivered = walk(None, "cs_test_audit_default")
    clause = "The person is wearing a dark navy blazer over a plain white shirt,"
    assert clause in preview["arguments"]["prompt"]
    for request in delivered:
        assert clause in request["arguments"]["prompt"]


def test_the_two_requests_print_side_by_side(walk, capsys):
    """The audit's evidence. `pytest tests/test_outfit_audit.py -s` pastes both bodies
    into docs/audit/outfit-2026-09-20.md."""
    preview, delivered = walk(CHOSEN, "cs_test_audit_chosen")
    with capsys.disabled():
        print("\n--- PREVIEW REQUEST ---")
        print(json.dumps(preview, indent=2, ensure_ascii=False))
        print("--- DELIVERED PHOTO 1 OF 4 ---")
        print(json.dumps(delivered[0], indent=2, ensure_ascii=False))
    assert preview["arguments"]["prompt"] != delivered[0]["arguments"]["prompt"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
