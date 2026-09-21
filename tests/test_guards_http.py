import hashlib
import hmac
import json
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import Order, OrderStore, Pipeline, delivery_token  # noqa: E402
from app.guards import (  # noqa: E402
    MemoryCounter,
    RateLimiter,
    build_prompt,
    sniff,
    validate_uploads,
)
from app.main import HEALTH_PATH, make_app  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 100
HEIC = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 100
TXT = b"hello world this is not an image" * 4


# ---------------------------------------------------------------- rate limiter


def make_rl(clock, **kw):
    now = lambda: clock[0]  # noqa: E731
    return RateLimiter(counter=MemoryCounter(now=now), now=now, **kw)


def test_rate_limiter_per_client_then_429():
    clock = [1_000_000.0]
    rl = make_rl(clock, per_client=3, window_s=3600, daily_global=100)
    assert [rl.check("1.2.3.4", "ua")[0] for _ in range(3)] == [True, True, True]
    assert rl.check("1.2.3.4", "ua") == (False, "client_cap")
    assert rl.check("9.9.9.9", "ua")[0] is True  # other client unaffected
    clock[0] += 3601
    assert rl.check("1.2.3.4", "ua")[0] is True  # window rolled


def test_rate_limiter_subnet_cap_defeats_ip_rotation_inside_a_block():
    clock = [1_500_000.0]
    rl = make_rl(clock, per_client=1000, per_subnet=5, daily_global=1000)
    for i in range(5):
        assert rl.check(f"203.0.113.{i}", f"ua{i}")[0]
    assert rl.check("203.0.113.99", "ua99") == (False, "subnet_cap")
    assert rl.check("198.51.100.1", "ua")[0] is True  # different block still fine


def test_rate_limiter_global_daily_cap_bounds_fal_spend():
    clock = [2_000_000.0]
    rl = make_rl(clock, per_client=1000, per_subnet=1000, daily_global=5)
    for i in range(5):
        assert rl.check(f"10.{i}.0.1", "ua")[0]
    assert rl.check("10.99.0.1", "ua") == (False, "daily_cap")


def test_rejected_client_does_not_consume_global_budget():
    clock = [2_500_000.0]
    rl = make_rl(clock, per_client=1, per_subnet=1000, daily_global=2)
    assert rl.check("1.1.1.1", "ua")[0]
    for _ in range(50):  # hammering from one client
        assert rl.check("1.1.1.1", "ua") == (False, "client_cap")
    assert rl.check("2.2.2.2", "ua")[0] is True  # global still had room


def test_rate_limiter_stores_no_raw_ip():
    rl = make_rl([3_000_000.0])
    rl.check("203.0.113.7", "ua")
    assert "203.0.113.7" not in json.dumps([str(k) for k in rl.counter.store])


# ---------------------------------------------------------------- uploads


def test_sniff_by_bytes_not_extension():
    assert sniff(JPEG) == "image/jpeg"
    assert sniff(PNG) == "image/png"
    assert sniff(WEBP) == "image/webp"
    assert sniff(HEIC) == "image/heic"
    assert sniff(TXT) is None


def test_upload_count_enforced_1_to_4():
    with pytest.raises(ValueError, match="upload_count:0"):
        validate_uploads([])
    with pytest.raises(ValueError, match="upload_count:5"):
        validate_uploads([JPEG] * 5)
    assert len(validate_uploads([JPEG]).accepted) == 1
    assert len(validate_uploads([JPEG] * 4).accepted) == 4


def test_upload_rejects_non_image_and_flags_heic():
    with pytest.raises(ValueError, match="unsupported_type:1"):
        validate_uploads([JPEG, TXT])
    v = validate_uploads([JPEG, HEIC, PNG])
    assert v.needs_heic_conversion == [1]


def test_upload_rejects_oversize():
    with pytest.raises(ValueError, match="file_too_large:0"):
        validate_uploads([JPEG + b"\x00" * (12 * 1024 * 1024)])


# ---------------------------------------------------------------- prompts


def test_prompts_are_deterministic_and_distinct_per_variant():
    a = [build_prompt("corporativo", i) for i in range(4)]
    assert a == [build_prompt("corporativo", i) for i in range(4)]
    assert len(set(a)) == 4
    for p in a:
        assert "Keep the exact same face" in p
        assert p.count("reference photos") == 2  # identity at both ends
        # Was `"No text" in p`. That pinned the exclusion phrasing Google's own docs
        # tell you not to use, so the test was holding the defect in place. The
        # affirmative replacement is asserted in tests/test_prompt_phrasing.py.
        assert "85mm" in p and "The result is a photograph" in p


def test_unknown_style_fails_loudly():
    with pytest.raises(KeyError):
        build_prompt("anime", 0)


# ---------------------------------------------------------------- HTTP layer

SECRET, TASKS = "whsec_test", "tasks_token"


def sign(payload: bytes, ts=None):
    ts = ts or int(time.time())
    return (
        f"t={ts},v1="
        + hmac.new(SECRET.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    )


class SlowModel:
    def __init__(self):
        self.calls, self.lock = 0, threading.Lock()

    def edit(self, urls, prompt):
        time.sleep(0.01)
        with self.lock:
            self.calls += 1
            return f"https://fal.media/{self.calls}.png"


class Storage:
    def put(self, key, url):
        return f"https://cdn/{key}"


def build_client():
    store, emails, queued = OrderStore(), [], []
    pipeline = Pipeline(
        store=store,
        model=SlowModel(),
        storage=Storage(),
        send_email=lambda to, b: emails.append((to, b)),
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret="app",
    )
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter(), per_client=2, per_subnet=100),
        enqueue=queued.append,
        preview_fn=lambda files, batch: "https://cdn/preview.png",
        webhook_secret=SECRET,
        tasks_token=TASKS,
        verify_turnstile=lambda token, ip: token == "good",
        # The budget push is authenticated now (U1). These tests exercise the KILL
        # SWITCH, not the auth, so they present a caller the app accepts; the auth
        # itself is tests/test_budget_auth.py.
        verify_pubsub=lambda authorization: True,
    )
    return TestClient(app), store, emails, queued, pipeline


def event(session_id):
    return json.dumps(
        {
            "id": f"evt_{session_id}",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": session_id,
                    "amount_total": 1999,
                    "customer_details": {"email": "k@example.com"},
                    "metadata": {
                        "source_urls": "https://cdn/a.jpg,https://cdn/b.jpg",
                        "style": "linkedin",
                        "gclid": "g1",
                    },
                }
            },
        }
    ).encode()


def test_webhook_enqueues_and_task_endpoint_delivers():
    c, store, emails, queued, _ = build_client()
    body = event("cs_1")
    r = c.post("/api/stripe/webhook", content=body, headers={"stripe-signature": sign(body)})
    assert r.status_code == 200 and queued == ["cs_1"]
    r = c.post("/internal/generate/cs_1", headers={"x-tasks-token": TASKS})
    assert r.json() == {"status": "delivered"}
    assert len(emails) == 1
    tok = delivery_token("cs_1", "app")
    assert len(c.get(f"/api/orders/cs_1/{tok}").json()["images"]) == 4
    assert c.get("/api/orders/cs_1/wrongtoken").status_code == 404


def test_webhook_duplicate_returns_200_but_enqueues_once():
    c, store, emails, queued, _ = build_client()
    body = event("cs_2")
    h = {"stripe-signature": sign(body)}
    assert c.post("/api/stripe/webhook", content=body, headers=h).json() == {"queued": "cs_2"}
    assert c.post("/api/stripe/webhook", content=body, headers=h).json() == {"duplicate": True}
    assert queued == ["cs_2"]


def test_webhook_bad_signature_400():
    c, *_ = build_client()
    h = {"stripe-signature": "t=1,v1=00"}
    r = c.post("/api/stripe/webhook", content=event("cs_3"), headers=h)
    assert r.status_code == 400


def test_task_endpoint_requires_token():
    c, *_ = build_client()
    assert c.post("/internal/generate/x").status_code == 403


def test_two_orders_at_the_same_time_do_not_interfere():
    c, store, emails, queued, pipeline = build_client()
    for sid in ("cs_a", "cs_b"):
        body = event(sid)
        c.post("/api/stripe/webhook", content=body, headers={"stripe-signature": sign(body)})
    results = {}

    def run(sid):
        results[sid] = c.post(f"/internal/generate/{sid}", headers={"x-tasks-token": TASKS}).json()

    threads = [threading.Thread(target=run, args=(sid,)) for sid in ("cs_a", "cs_b")]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert results == {"cs_a": {"status": "delivered"}, "cs_b": {"status": "delivered"}}
    assert len(store.get("cs_a").outputs) == 4 and len(store.get("cs_b").outputs) == 4
    assert pipeline.model.calls == 8
    assert sorted(e[0] for e in emails) == ["k@example.com", "k@example.com"]


def test_preview_requires_turnstile_then_rate_limits_then_validates():
    c, store, *_ = build_client()
    files = [("files", ("a.jpg", JPEG, "image/jpeg"))]
    ok = {"turnstile_token": "good"}
    assert c.post("/api/preview", files=files).status_code == 403  # no token
    assert c.post("/api/preview", files=files, data={"turnstile_token": "x"}).status_code == 403
    assert c.post("/api/preview", files=files, data=ok).status_code == 200
    assert c.post("/api/preview", files=files, data=ok).status_code == 200
    # Task 29: per_client=2 no longer means a 429 here. The shop still sells —
    # /api/preview stores the photos and signs a handle instead, `limited: true`.
    r = c.post("/api/preview", files=files, data=ok)
    assert r.status_code == 200 and r.json()["limited"] is True
    bad = [("files", ("a.jpg", TXT, "image/jpeg"))]  # lies in header
    r = c.post("/api/preview", files=bad, data=ok, headers={"x-forwarded-for": "5.5.5.5"})
    assert r.status_code == 422 and "unsupported_type" in r.text


def test_budget_push_flips_killswitch_and_preview_returns_503():
    import base64

    c, store, *_ = build_client()
    note = json.dumps({"costAmount": 41.2, "budgetAmount": 40.0, "alertThresholdExceeded": 1.0})
    msg = {"message": {"data": base64.b64encode(note.encode()).decode()}}
    assert c.post("/internal/budget", json=msg).json() == {"killswitch": True}
    files = [("files", ("a.jpg", JPEG, "image/jpeg"))]
    r = c.post("/api/preview", files=files, data={"turnstile_token": "good"})
    assert r.status_code == 503


def test_budget_push_below_100_percent_does_not_flip():
    import base64

    c, store, *_ = build_client()
    note = json.dumps({"alertThresholdExceeded": 0.9})
    msg = {"message": {"data": base64.b64encode(note.encode()).decode()}}
    assert c.post("/internal/budget", json=msg).json() == {"killswitch": False}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


def test_static_frontend_served_after_api_routes(tmp_path):
    (tmp_path / "index.html").write_text("<h1>StudioFace</h1>")
    (tmp_path / "g").mkdir()
    (tmp_path / "g" / "index.html").write_text("<h1>gallery</h1>")
    store = OrderStore()
    pipeline = Pipeline(
        store=store,
        model=SlowModel(),
        storage=Storage(),
        send_email=lambda t, b: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret="app",
    )
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter()),
        enqueue=lambda i: None,
        preview_fn=lambda f, batch: "",
        webhook_secret=SECRET,
        tasks_token=TASKS,
        static_dir=str(tmp_path),
    )
    c = TestClient(app)
    assert c.get("/").text == "<h1>StudioFace</h1>"
    assert c.get("/g/?o=x&t=y").text == "<h1>gallery</h1>"
    assert c.get(HEALTH_PATH).json()["ok"] is True  # API still wins over the static mount


def test_gallery_link_uses_fragment_form():
    store = OrderStore()
    emails = []
    p = Pipeline(
        store=store,
        model=SlowModel(),
        storage=Storage(),
        send_email=lambda t, b: emails.append(b),
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret="app",
    )
    store.put(
        Order(id="o9", email="k@x", source_image_urls=["u"], style="corporativo", amount_cents=1)
    )
    p.run("o9")
    # Task 31: a fragment, never a query — a fragment is never sent to any server.
    assert emails[0].startswith("https://studioface.app/g/#o=o9&t=")
    assert "?" not in emails[0]


# ---------------------------------------------------------------- gallery signing


class GsStorage:
    """Production-shaped storage: it returns gs:// keys, never public URLs."""

    def put(self, key, url):
        return f"gs://sf-out/{key}"


def build_gallery_client(sign_url=None):
    store = OrderStore()
    pipeline = Pipeline(
        store=store,
        model=SlowModel(),
        storage=GsStorage(),
        send_email=lambda t, b: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret="app",
    )
    kw = {} if sign_url is None else {"sign_url": sign_url}
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter()),
        enqueue=lambda i: None,
        preview_fn=lambda f, batch: "",
        webhook_secret=SECRET,
        tasks_token=TASKS,
        **kw,
    )
    store.put(
        Order(id="o1", email="k@x", source_image_urls=["u"], style="corporativo", amount_cents=1)
    )
    return TestClient(app), store, pipeline


def test_gallery_never_returns_a_raw_gs_key_to_the_browser():
    """A gs:// URI is useless to an <img> tag and a public object would be a leak."""
    signed = []

    def sign(uri):
        signed.append(uri)
        return f"https://storage.googleapis.com/{uri.removeprefix('gs://')}?X-Goog-Signature=ab"

    c, store, p = build_gallery_client(sign_url=sign)
    p.run("o1")
    body = c.get(f"/api/orders/o1/{delivery_token('o1', 'app')}").json()
    assert body["status"] == "delivered"
    assert len(body["images"]) == 4
    assert all(u.startswith("https://storage.googleapis.com/") for u in body["images"])
    assert all("X-Goog-Signature" in u for u in body["images"])
    # F3 signs each object TWICE: once to display and once, with an attachment
    # disposition, to download. Both must name the same four objects.
    wanted = [f"gs://sf-out/o1/{i}.jpg" for i in range(4)]
    assert sorted(set(signed)) == sorted(wanted)
    assert len(signed) == 8, f"expected a display and a download signature each: {signed}"


def test_gallery_signs_nothing_until_the_order_is_delivered():
    """Held-out check: signing while still generating would hand out URLs for objects
    that do not exist yet, and the page polls this endpoint every 3 seconds."""
    signed = []
    c, store, p = build_gallery_client(sign_url=lambda u: signed.append(u) or "x")
    body = c.get(f"/api/orders/o1/{delivery_token('o1', 'app')}").json()
    # F3 added `downloads`, which must be empty for exactly as long as `images` is:
    # a download link for an object that does not exist yet is four broken saves.
    assert body == {"status": "paid", "images": [], "downloads": []}
    assert signed == []


def test_gallery_defaults_to_passing_urls_through_untouched():
    c, store, p = build_gallery_client()
    p.run("o1")
    body = c.get(f"/api/orders/o1/{delivery_token('o1', 'app')}").json()
    assert body["images"] == [f"gs://sf-out/o1/{i}.jpg" for i in range(4)]


# ---------------------------------------------------------------- compression


def test_static_assets_are_served_compressed(tmp_path):
    """Lighthouse measured 2.1 s of savings from text compression against the real
    app: neither Cloud Run nor StaticFiles compresses anything on its own, so the
    JS and CSS of the export went over the wire raw. That is mobile LCP."""
    (tmp_path / "index.html").write_text("<h1>StudioFace</h1>" + "<p>relleno</p>" * 200)
    store = OrderStore()
    pipeline = Pipeline(
        store=store,
        model=SlowModel(),
        storage=Storage(),
        send_email=lambda t, b: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret="app",
    )
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter()),
        enqueue=lambda i: None,
        preview_fn=lambda f, batch: "",
        webhook_secret=SECRET,
        tasks_token=TASKS,
        static_dir=str(tmp_path),
    )
    c = TestClient(app)
    r = c.get("/", headers={"accept-encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"


def test_a_client_that_cannot_decompress_still_gets_the_page():
    """Held-out check: Cloud Tasks and Stripe do not send accept-encoding. Forcing
    gzip on them would break the webhook."""
    c, *_ = build_client()
    r = c.post("/internal/generate/nope", headers={"accept-encoding": "identity"})
    assert r.headers.get("content-encoding") != "gzip"
