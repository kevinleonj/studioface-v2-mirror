"""O3: "Descargar" did not download.

Measured with Playwright on desktop by an external reviewer: no download event fired,
and the tab navigated away to the raw image. The customer who paid 19,99 EUR pressed the
one control that collects their photographs and lost the page they were on.

Two reasons, and the first alone is fatal:

1. The link was `<a download="studioface-1.jpg" href="https://storage.googleapis.com/...">`.
   The `download` attribute is ignored on a CROSS-ORIGIN link - the page is
   studioface.app and the image is storage.googleapis.com - so the browser treats it as
   ordinary navigation.
2. The signed address carried no `Content-Disposition`, so even following it just
   displays the JPEG.

The fix is on the server, because only the server can say what the response headers are:
`Blob.generate_signed_url` accepts `response_disposition`, so the download address is
signed with `attachment; filename="studioface-<n>.jpg"`. A browser downloads that
whatever the link attribute says, and cross-origin no longer matters.

## Two addresses per image, deliberately

The brief allows one if an `<img>` still renders an address signed with `attachment`.
It is not worth finding out: `Content-Disposition: attachment` is an instruction to save
rather than display, and hanging the gallery's four visible photographs on a browser
being lenient about it is a bet with nothing to win. Signing is local
cryptography over the blob name - no network - so the second address costs microseconds.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import Order, OrderStore, Pipeline, delivery_token  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import make_app  # noqa: E402

SECRET = "app"
ORDER = "cs_test_download"


def fake_sign(uri: str, filename: str | None = None) -> str:
    """What the real signer produces, in the two shapes the gallery needs."""
    base = f"https://storage.googleapis.com/out/{uri.rsplit('/', 1)[-1]}?X-Goog-Signature=a"
    if filename:
        return base + f"&response-content-disposition=attachment%3B+filename%3D%22{filename}%22"
    return base


def build(sign_url=fake_sign):
    store = OrderStore()
    order = Order(ORDER, "k@example.com", ["gs://src/a.jpg"], "corporativo", 1999)
    order.status = "delivered"
    order.outputs = [f"gs://out/{ORDER}/{i}.jpg" for i in range(4)]
    store.put(order)
    pipeline = Pipeline(
        store=store,
        model=type("M", (), {"edit": lambda self, u, p: "x"})(),
        storage=type("S", (), {"put": lambda self, k, u: k})(),
        send_email=lambda t, b: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret=SECRET,
    )
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter()),
        enqueue=lambda i: None,
        preview_fn=lambda f, batch: "",
        webhook_secret="whsec",
        tasks_token="tt",
        sign_url=sign_url,
    )
    from fastapi.testclient import TestClient

    return TestClient(app)


def gallery(client):
    return client.get(f"/api/orders/{ORDER}/{delivery_token(ORDER, SECRET)}").json()


def test_the_gallery_returns_a_download_address_per_image():
    body = gallery(build())
    assert len(body["images"]) == 4
    assert len(body["downloads"]) == 4, "no download addresses at all"


def test_each_download_address_asks_the_browser_to_save():
    """The whole unit. Without this header the browser displays the JPEG and the tab
    navigates away, which is exactly what the reviewer measured."""
    body = gallery(build())
    for i, url in enumerate(body["downloads"], start=1):
        assert "attachment" in url, f"download {i} is not an attachment: {url}"
        assert f"studioface-{i}.jpg" in url, f"download {i} has no filename: {url}"


def test_the_visible_addresses_are_not_attachments():
    """Held-out check, and the reason there are two addresses. An `attachment`
    disposition tells the browser to save rather than display; putting that on the four
    images the gallery shows would be trading one broken thing for another."""
    body = gallery(build())
    for url in body["images"]:
        assert "attachment" not in url, f"a visible image is signed as an attachment: {url}"


def test_the_two_addresses_point_at_the_same_four_objects():
    """A download that fetches a different object is worse than one that does nothing."""
    body = gallery(build())
    for shown, saved in zip(body["images"], body["downloads"], strict=True):
        assert shown.split("?")[0] == saved.split("?")[0], f"{shown} != {saved}"


def test_an_order_still_generating_offers_nothing_to_download():
    """The gallery polls while the images are being made. Handing out download links for
    objects that do not exist yet would produce four broken saves, so `downloads` is
    empty for exactly as long as `images` is."""
    order = Order(ORDER, "k@example.com", ["gs://src/a.jpg"], "corporativo", 1999)
    order.status = "generating"
    body = gallery(build_with(order))
    assert body["status"] == "generating"
    assert body["images"] == [] and body["downloads"] == []


def build_with(order: Order):
    """A client whose store holds exactly this order."""
    store = OrderStore()
    store.put(order)
    pipeline = Pipeline(
        store=store,
        model=type("M", (), {"edit": lambda self, u, p: "x"})(),
        storage=type("S", (), {"put": lambda self, k, u: k})(),
        send_email=lambda t, b: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret=SECRET,
    )
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter()),
        enqueue=lambda i: None,
        preview_fn=lambda f, batch: "",
        webhook_secret="whsec",
        tasks_token="tt",
        sign_url=fake_sign,
    )
    from fastapi.testclient import TestClient

    return TestClient(app)


def test_a_signer_that_ignores_the_filename_still_works():
    """Held-out: every existing test double takes one argument. The route must not crash
    on one, it must simply offer no attachment - which is today's behaviour, not worse."""
    body = gallery(build(sign_url=lambda uri: f"https://signed/{uri}"))
    assert len(body["images"]) == 4
    assert body["downloads"] == body["images"], "a one-argument signer should degrade, not crash"


def test_the_real_signer_passes_response_disposition_to_google():
    """The adapter, not the route. `response_disposition` is the documented parameter on
    `Blob.generate_signed_url`; this asserts we hand it the right thing."""
    from app.adapters.gcs import SignedUrlMaker

    seen = {}

    class Blob:
        def generate_signed_url(self, **kwargs):
            seen.update(kwargs)
            return "https://storage.googleapis.com/signed"

    class Credentials:
        valid = True
        token = "t"
        service_account_email = "run@sf.iam.gserviceaccount.com"

    signer = SignedUrlMaker(client=None, credentials=Credentials(), blob_factory=lambda uri: Blob())
    signer("gs://out/x/1.jpg")
    assert "response_disposition" not in seen or seen["response_disposition"] is None

    seen.clear()
    signer("gs://out/x/1.jpg", "studioface-1.jpg")
    assert seen.get("response_disposition") == 'attachment; filename="studioface-1.jpg"'


def test_the_filename_cannot_be_used_to_inject_a_header():
    """A quoted header value with a quote or a newline in it is a header-injection
    primitive. The route builds the name itself today, but this is the guard that keeps
    it that way."""
    from app.adapters.gcs import SignedUrlMaker

    class Blob:
        def generate_signed_url(self, **kwargs):
            return "https://storage.googleapis.com/signed"

    class Credentials:
        valid = True
        token = "t"
        service_account_email = "run@sf.iam.gserviceaccount.com"

    signer = SignedUrlMaker(client=None, credentials=Credentials(), blob_factory=lambda uri: Blob())
    with pytest.raises(ValueError, match="bad_filename"):
        signer("gs://out/x/1.jpg", 'a".jpg\r\nX-Evil: 1')


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
