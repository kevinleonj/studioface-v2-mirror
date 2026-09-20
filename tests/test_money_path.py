"""One order, from a stranger's upload to four signed gallery links, with every
StudioFace module real and only the three network boundaries faked: fal's HTTP
call, the GCS blob, and the Firestore client.

The unit tests each prove one part. This proves the parts still fit together:
real make_app, real Pipeline on threaded_batch, real FirestoreOrderStore, real
FalModel, real Preview, real SignedUrlMaker, real RateLimiter, real image
normalisation, real Stripe signature verification.
"""

import hashlib
import hmac
import io
import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.adapters.fal import FalModel  # noqa: E402
from app.adapters.gcs import SignedUrlMaker  # noqa: E402
from app.core import Pipeline, delivery_token, threaded_batch  # noqa: E402
from app.entry import FirestoreOrderStore  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import make_app  # noqa: E402
from app.preview import Preview  # noqa: E402
from tests.fake_firestore import FakeFirestore  # noqa: E402

WEBHOOK_SECRET, TASKS_TOKEN, APP_SECRET = "whsec_test", "tasks_tok", "app_secret"
SIGNED_PREFIX = "https://storage.googleapis.com/"


def heic_selfie(size=(2400, 1800)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (90, 70, 60)).save(buf, "HEIF")
    return buf.getvalue()


class FakeFal:
    """Stands in for fal_client.subscribe. Records exactly what was sent."""

    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def __call__(self, application, arguments=None, **kw):
        self.calls.append(arguments)
        if self.fail:
            raise RuntimeError("fal 503")
        return {"images": [{"url": f"https://fal.media/{len(self.calls)}.jpg", "width": 1024}]}


class FakeBlob:
    def __init__(self, bucket, name, store):
        self.bucket, self.name, self.store = bucket, name, store

    def upload_from_string(self, data, content_type=None):
        self.store[f"{self.bucket}/{self.name}"] = (data, content_type)

    def generate_signed_url(self, **kw):
        assert kw["version"] == "v4" and kw["method"] == "GET"
        return f"{SIGNED_PREFIX}{self.bucket}/{self.name}?X-Goog-Signature=ab"


class FakeGcs:
    def __init__(self):
        self.objects = {}

    def blob_at(self, bucket, name):
        return FakeBlob(bucket, name, self.objects)

    def from_uri(self, uri):
        bucket, _, name = uri.removeprefix("gs://").partition("/")
        return self.blob_at(bucket, name)

    def put_source(self, key, data):
        self.blob_at("sf-src", key).upload_from_string(data, "image/jpeg")
        return f"gs://sf-src/{key}"


class FakeCredentials:
    valid = False
    token = None
    service_account_email = "run@sf-prod.iam.gserviceaccount.com"

    def refresh(self, request):
        self.valid, self.token = True, "ya29.token"


def build(fal=None):
    gcs, fal, db = FakeGcs(), fal or FakeFal(), FakeFirestore()
    sign = SignedUrlMaker(
        client=None,
        credentials=FakeCredentials(),
        blob_factory=gcs.from_uri,
        request_factory=lambda: None,
    )

    class OutBucket:
        """The Storage port: copies a finished fal image into BUCKET_OUT."""

        def put(self, key, url):
            gcs.blob_at("sf-out", key).upload_from_string(b"jpeg", "image/jpeg")
            return f"gs://sf-out/{key}"

    out = OutBucket()
    emails, refunds, conversions, queued = [], [], [], []
    pipeline = Pipeline(
        store=FirestoreOrderStore(db),
        model=FalModel(sign=sign, subscribe=fal),
        storage=out,
        send_email=lambda to, body: emails.append((to, body)),
        refund=lambda oid, cents: refunds.append((oid, cents)),
        track_conversion=lambda o: conversions.append(o.id),
        secret=APP_SECRET,
        run_batch=threaded_batch,
    )
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter(), per_client=3, per_subnet=50),
        enqueue=queued.append,
        preview_fn=Preview(
            put_source=gcs.put_source,
            model=FalModel(sign=sign, subscribe=fal, resolution="0.5K"),
            # C1: the preview goes into the same out bucket the gallery reads and comes
            # back signed, instead of leaving as fal's own public address.
            store_result=out.put,
            sign=sign,
        ),
        webhook_secret=WEBHOOK_SECRET,
        tasks_token=TASKS_TOKEN,
        verify_turnstile=lambda token, ip: token == "good",
        sign_url=sign,
    )
    world = dict(
        gcs=gcs, fal=fal, db=db, emails=emails, refunds=refunds, conv=conversions, queued=queued
    )
    return TestClient(app), world


def checkout_event(session_id, source_urls):
    return json.dumps(
        {
            "id": f"evt_{session_id}",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": session_id,
                    "amount_total": 1999,
                    "customer_details": {"email": "cliente@example.com"},
                    "metadata": {"source_urls": ",".join(source_urls), "style": "corporativo"},
                }
            },
        }
    ).encode()


def sign_webhook(body):
    ts = int(time.time())
    v1 = hmac.new(WEBHOOK_SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={v1}"


def pay(client, session_id, sources):
    body = checkout_event(session_id, sources)
    return client.post(
        "/api/stripe/webhook", content=body, headers={"stripe-signature": sign_webhook(body)}
    )


def test_one_order_from_heic_upload_to_four_signed_gallery_links():
    c, w = build()

    # 1. a stranger uploads an iPhone photo and gets a free preview
    r = c.post(
        "/api/preview",
        files=[("files", ("IMG_0042.HEIC", heic_selfie(), "image/heic"))],
        data={"turnstile_token": "good"},
    )
    assert r.status_code == 200, r.text
    # Unit C1. This line used to read `== "https://fal.media/1.jpg"`, which is the defect
    # written down as an expectation: the money path asserted that the free preview is
    # handed to the browser as fal's own public address. img-src has never allowed a fal
    # host, so the browser refused it and the visitor got a broken-image icon where their
    # face should have been. The preview now comes back signed, out of the same bucket
    # and through the same signer as the gallery.
    preview_url = r.json()["preview_url"]
    assert preview_url.startswith("https://storage.googleapis.com/sf-out/previews/"), preview_url
    assert "fal.media" not in preview_url

    stored = [k for k in w["gcs"].objects if k.startswith("sf-src/")]
    assert len(stored) == 1
    data, content_type = w["gcs"].objects[stored[0]]
    assert data[:3] == b"\xff\xd8\xff" and content_type == "image/jpeg"  # converted from HEIC
    assert max(Image.open(io.BytesIO(data)).size) == 1536  # and shrunk
    assert w["fal"].calls[0]["resolution"] == "0.5K"  # the free one is the cheap one
    # fal was handed a signed https URL, never the private gs:// key
    assert w["fal"].calls[0]["image_urls"][0].startswith(SIGNED_PREFIX + "sf-src/")

    # 2. they pay; Stripe posts a signed webhook
    sources = ["gs://" + stored[0]]
    assert pay(c, "cs_live_1", sources).json() == {"queued": "cs_live_1"}
    assert w["queued"] == ["cs_live_1"]
    assert w["db"].docs["orders/cs_live_1"]["status"] == "paid"  # persisted, not in memory

    # 3. Cloud Tasks calls the internal endpoint
    r = c.post("/internal/generate/cs_live_1", headers={"x-tasks-token": TASKS_TOKEN})
    assert r.json() == {"status": "delivered"}

    paid_calls = w["fal"].calls[1:]
    assert len(paid_calls) == 4
    assert all(a["resolution"] == "1K" for a in paid_calls)
    assert len({a["prompt"] for a in paid_calls}) == 4  # four different photos, not one four times
    assert len([k for k in w["gcs"].objects if k.startswith("sf-out/cs_live_1/")]) == 4

    # 4. the customer gets exactly one email, carrying the HMAC gallery link
    token = delivery_token("cs_live_1", APP_SECRET)
    link = f"https://studioface.app/g/?o=cs_live_1&t={token}"
    assert w["emails"] == [("cliente@example.com", link)]
    assert w["conv"] == ["cs_live_1"]
    assert w["refunds"] == []

    # 5. the gallery hands back short-lived signed links, never a public object
    body = c.get(f"/api/orders/cs_live_1/{token}").json()
    assert body["status"] == "delivered" and len(body["images"]) == 4
    assert all(u.startswith(SIGNED_PREFIX + "sf-out/") for u in body["images"])
    assert all("X-Goog-Signature" in u for u in body["images"])
    assert c.get("/api/orders/cs_live_1/wrong-token").status_code == 404


def test_the_whole_path_is_safe_to_replay():
    """Stripe retries webhooks and Cloud Tasks retries tasks. Neither may generate
    twice, email twice, or report the conversion twice."""
    c, w = build()
    assert pay(c, "cs_live_2", ["gs://sf-src/x/0.jpg"]).json() == {"queued": "cs_live_2"}
    assert pay(c, "cs_live_2", ["gs://sf-src/x/0.jpg"]).json() == {"duplicate": True}
    assert w["queued"] == ["cs_live_2"]

    for _ in range(3):
        r = c.post("/internal/generate/cs_live_2", headers={"x-tasks-token": TASKS_TOKEN})
        assert r.json() == {"status": "delivered"}
    assert len(w["fal"].calls) == 4  # not 12
    assert len(w["emails"]) == 1
    assert len(w["conv"]) == 1


def test_a_dead_fal_refunds_the_customer_and_never_delivers():
    c, w = build(fal=FakeFal(fail=True))
    pay(c, "cs_live_3", ["gs://sf-src/x/0.jpg"])
    r = c.post("/internal/generate/cs_live_3", headers={"x-tasks-token": TASKS_TOKEN})
    assert r.json() == {"status": "failed_refunded"}
    assert w["refunds"] == [("cs_live_3", 1999)]
    assert w["conv"] == []  # nothing reported to Google Ads
    assert w["emails"] == [("cliente@example.com", "REFUND")]
    assert len(w["fal"].calls) == 8  # the retry budget, and not one call more
    assert w["db"].docs["orders/cs_live_3"]["status"] == "failed_refunded"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
