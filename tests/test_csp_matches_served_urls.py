"""P3: the policy and the addresses the server hands the browser, tested against each other.

The Content-Security-Policy was audited against Google's list of hosts and never against
this application's own image sources. So `img-src` was correct about analytics and wrong
about the product: `/api/preview` returned an address on fal's content delivery network,
`v3b.fal.media`, which has never been in the policy —

    $ git log --oneline -S "fal.media" -- app/main.py
    (no output)

— and the browser refused to load it. The visitor got a broken-image icon and a grey box
where their own face should have been. Every existing test passed, because no test ever
compared the two halves.

This is that test. It asks the application for the addresses it actually serves, asks the
middleware for the policy it actually emits, and checks each against the other. It uses
faked adapters, so it runs in CI with no network and no credentials, and it fails for any
new image source that nobody added to the policy — which is the whole point.
"""

import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import Order, OrderStore, Pipeline, delivery_token  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import CSP, make_app  # noqa: E402

SECRET = "app"
ORDER_ID = "cs_test_csp"

# What the real adapters produce. The gallery signs objects in the private bucket; the
# preview, before unit C1, handed back whatever fal returned.
SIGNED = "https://storage.googleapis.com/studio-face-fresh-start-out/{key}?X-Goog-Signature=abc"
FAL = "https://v3b.fal.media/files/b/0aab0e36/output.jpg"


def allows(sources: list[str], url: str) -> bool:
    """Would this `img-src` list permit the browser to load `url`?

    Scheme and host only, which is what a host-source expression matches on. A served
    `https://*.google.com` permits `https://www.google.com`; it does not permit
    `https://v3b.fal.media`.
    """
    host = urlsplit(url).netloc
    for source in sources:
        if not source.startswith("https://"):
            continue
        name = source.removeprefix("https://")
        if name == host:
            return True
        if name.startswith("*.") and host.endswith(name[1:]):
            return True
    return False


def real_preview():
    """The real `Preview`, with only its adapters faked.

    This matters more than it looks. The first version of this test passed a lambda as
    `preview_fn`, which meant it asserted against a string the test itself chose and
    could never have been turned green by fixing the application. The defect lives in
    how `Preview` assembles the address, so `Preview` has to be the thing under test.

    The fakes below stand exactly where the real adapters stand: `model.edit` answers
    with a fal address, because that is what fal answers with; `store_result` answers
    with a `gs://` uri, because that is what a bucket upload answers with; `sign` turns
    that into a storage.googleapis.com address, because that is what the signer does.
    """
    from app.preview import Preview

    return Preview(
        put_source=lambda key, data: f"gs://src/{key}",
        model=type("M", (), {"edit": lambda self, uris, prompt: FAL})(),
        store_result=lambda key, url: f"gs://out/{key}",
        sign=lambda uri: SIGNED.format(key=uri.removeprefix("gs://out/")),
    )


def build(preview_fn):
    store = OrderStore()
    pipeline = Pipeline(
        store=store,
        model=type("M", (), {"edit": lambda self, u, p: "x"})(),
        storage=type("S", (), {"put": lambda self, k, u: k})(),
        send_email=lambda t, b: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret=SECRET,
    )
    order = Order(ORDER_ID, "k@example.com", ["gs://src/a.jpg"], "corporativo", 1999)
    order.status, order.outputs = "delivered", [f"gs://out/{ORDER_ID}/{i}.jpg" for i in range(4)]
    store.put(order)
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter()),
        enqueue=lambda i: None,
        preview_fn=preview_fn,
        webhook_secret="whsec",
        tasks_token="tt",
        verify_turnstile=lambda token, ip: True,
        sign_url=lambda uri: SIGNED.format(key=uri.rsplit("/", 1)[-1]),
    )
    from fastapi.testclient import TestClient

    return TestClient(app)


def served_img_src(client) -> list[str]:
    """The `img-src` the middleware actually emits, parsed from a real response."""
    header = client.get("/health").headers["content-security-policy"]
    for part in header.split(";"):
        directive, *values = part.strip().split()
        if directive == "img-src":
            return values
    raise AssertionError("the emitted policy has no img-src at all")


def gallery_urls(client) -> list[str]:
    token = delivery_token(ORDER_ID, SECRET)
    body = client.get(f"/api/orders/{ORDER_ID}/{token}").json()
    assert body["status"] == "delivered", body
    assert body["images"], "the gallery returned no images to check"
    return body["images"]


def preview_url(client) -> str:
    response = client.post(
        "/api/preview",
        data={"turnstile_token": "x"},
        files={"files": ("a.jpg", _jpeg(), "image/jpeg")},
    )
    assert response.status_code == 200, response.text
    return response.json()["preview_url"]


def _jpeg() -> bytes:
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (600, 600), (128, 110, 100)).save(buffer, "JPEG")
    return buffer.getvalue()


def test_every_gallery_image_is_allowed_by_the_policy():
    """The half that has always been true, asserted so it stays true."""
    client = build(real_preview())
    sources = served_img_src(client)
    for url in gallery_urls(client):
        assert allows(sources, url), f"img-src refuses a gallery image: {url}"


def test_the_preview_image_is_allowed_by_the_policy():
    """I1, in one line. Red until unit C1 routes the preview through the private bucket.

    This is the assertion no test made: the preview address was checked for being a
    string and never for being loadable under the policy the same server sends.
    """
    client = build(real_preview())
    sources = served_img_src(client)
    url = preview_url(client)
    assert allows(sources, url), (
        f"img-src refuses the preview image the server just returned: {url}\n"
        f"img-src is: {' '.join(sources)}"
    )


def test_the_check_can_fail(tmp_path):
    """P3's twin. A comparison that cannot go red is decoration.

    `allows` is the whole judgement, so it is exercised directly on a host the policy
    does not list. If this ever passes, the test above is worthless.
    """
    sources = CSP["img-src"]
    assert not allows(sources, FAL), "a fal.media address was accepted by the policy"
    assert not allows(sources, "https://evil.example.com/a.jpg")
    assert allows(sources, SIGNED.format(key="a.jpg")), "storage.googleapis.com is listed"


def test_the_wildcard_rule_does_not_over_match():
    """`*.google.com` must not be read as "any host ending in google.com anywhere", which
    is how a lenient matcher would let `notgoogle.com` through."""
    sources = ["https://*.google.com"]
    assert allows(sources, "https://www.google.com/a.png")
    assert not allows(sources, "https://wwwXgoogle.com/a.png")
    assert not allows(sources, "https://evil-google.com/a.png")


def test_the_policy_names_no_image_host_the_server_never_serves():
    """The other direction, kept deliberately narrow: fal must not be in the policy.

    C1's instruction is explicit - do not add fal.media to the policy, because a
    customer's face should not be referenced from a public third-party address in the
    page. This is the test that stops someone taking the one-line way out.
    """
    sources = " ".join(CSP["img-src"])
    assert "fal.media" not in sources, (
        "fal.media was added to img-src. C1 says route the preview through the private "
        "bucket instead: a customer's face must not be served from a public third-party "
        "address."
    )
    assert not re.search(r"\bhttps:(\s|$)", sources), "img-src allows every https host"
    assert "*" not in CSP["img-src"], "img-src allows everything"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


def test_the_served_policy_allows_the_upload_thumbnails():
    """The browser walk caught this after it shipped: four `img-src blob` violations on
    a page that had just rendered four thumbnails.

    `URL.createObjectURL` makes a `blob:` URL, and the emitted policy named `'self'` and
    `data:` but not `blob:`, so the visitor picked four photos and saw four empty
    squares. Asserted against the header a real response carries, not the constant,
    because the header is the only thing the browser obeys.
    """
    sources = served_img_src(build(real_preview()))
    assert "blob:" in sources, (
        "the served img-src refuses blob:, so every upload thumbnail is blocked. "
        f"img-src is: {' '.join(sources)}"
    )
