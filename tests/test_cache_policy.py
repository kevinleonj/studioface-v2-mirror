"""The app must say how long its responses may be reused. It said nothing at all.

Measured against production on 2026-09-18: neither the HTML document nor the
content-hashed JavaScript carried a `cache-control` header. Only `etag` and
`last-modified`, which is exactly what Starlette's StaticFiles sets and all it sets —
there is no code path in it that emits cache-control.

RFC 9111 section 4.2.2 is what makes that a defect rather than a detail:

    "a cache MAY assign a heuristic expiration time when an explicit time is not
     specified" ... "If the response has a Last-Modified header field, caches are
     encouraged to use a heuristic expiration value that is no more than some fraction
     of the interval since that time. A typical setting of this fraction might be 10%."

So any browser or intermediary was free to keep serving an old index.html without
asking us, for roughly a tenth of the document's age. That is the mechanism behind a
report of a live page missing elements the build definitely contains, and it is a
customer-facing bug: a returning visitor can be shown a page from before the deploy.

The policy:
  - HTML and anything not content-hashed -> `no-cache`. Store it, but revalidate every
    time. With an etag that costs a 304, not a re-download. MDN and web.dev both name
    `no-cache` as the directive for unversioned URLs.
  - `_next/static/**` -> `public, max-age=31536000, immutable`. Next names those files
    with a SHA of their contents, so the URL changes whenever the bytes do and the
    response never needs revalidating.
  - `/muestras/*` and the share image (`/share.jpg`) -> `public, max-age=86400`.
    Page-head unit: a crawler fetches og:image once and a search engine re-crawls the
    page on its own schedule, so a full day of caching is free bandwidth. Deliberately
    NOT immutable, unlike the hashed assets: these filenames carry no hash — replacing
    a demo pair or the share image keeps the same URL — so a correction is never more
    than a day late instead of pinned for a year.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import OrderStore, Pipeline  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import HASHED_PREFIX, IMMUTABLE, ONE_DAY, REVALIDATE, make_app  # noqa: E402


@pytest.fixture
def client(tmp_path):
    (tmp_path / "index.html").write_text("<h1>StudioFace</h1>", encoding="utf-8")
    hashed = tmp_path / "_next" / "static" / "chunks"
    hashed.mkdir(parents=True)
    (hashed / "abc123.js").write_text("console.log(1)", encoding="utf-8")
    muestras = tmp_path / "muestras"
    muestras.mkdir()
    (muestras / "mujer-40-antes.webp").write_bytes(b"RIFF0000WEBP")
    (tmp_path / "share.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    store = OrderStore()
    pipeline = Pipeline(
        store=store,
        model=type("M", (), {"edit": lambda self, u, p: "x"})(),
        storage=type("S", (), {"put": lambda self, k, u: k})(),
        send_email=lambda t, b: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret="app",
    )
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter()),
        enqueue=lambda i: None,
        preview_fn=lambda f, b: "",
        webhook_secret="whsec",
        tasks_token="tt",
        static_dir=str(tmp_path),
    )
    return TestClient(app)


def test_the_html_document_is_revalidated_every_time(client):
    """The regression. Without this a visitor can be served a pre-deploy page."""
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == REVALIDATE


def test_content_hashed_assets_are_immutable(client):
    """Their URL changes whenever their bytes do, so revalidating them is pure waste."""
    r = client.get("/_next/static/chunks/abc123.js")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == IMMUTABLE
    assert "immutable" in r.headers["cache-control"]
    assert "max-age=31536000" in r.headers["cache-control"]


def test_unhashed_assets_are_not_marked_immutable(client):
    """Held-out check, and the one that would bite. /muestras/ filenames carry no hash,
    so marking them immutable would pin a replaced demo photograph in caches for a
    year with no way to evict it."""
    r = client.get("/muestras/mujer-40-antes.webp")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == ONE_DAY
    assert "immutable" not in r.headers["cache-control"]


def test_the_share_image_gets_a_one_day_cache_too(client):
    """A crawler fetches og:image once; a full day of caching is free bandwidth, and
    the filename carries no hash so a corrected image is never pinned for a year."""
    r = client.get("/share.jpg")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == ONE_DAY


def test_every_static_response_says_something_about_caching(client):
    """Silence is the bug. A response with only etag and last-modified hands the
    decision to RFC 9111 heuristics."""
    paths = (
        "/",
        "/_next/static/chunks/abc123.js",
        "/muestras/mujer-40-antes.webp",
        "/share.jpg",
    )
    for path in paths:
        assert client.get(path).headers.get("cache-control"), f"{path} sets no cache-control"


def test_the_etag_survives_so_revalidation_stays_cheap(client):
    """no-cache means revalidate, not re-download. Without an etag it would mean both."""
    first = client.get("/")
    assert first.headers.get("etag")
    again = client.get("/", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304


def test_the_hashed_prefix_matches_what_next_actually_emits():
    """If Next ever changes its output directory this policy silently stops applying,
    and everything quietly becomes no-cache — slower, but not wrong. Pinned so the
    change is noticed rather than absorbed."""
    assert HASHED_PREFIX == "/_next/static/"
    export = Path(__file__).resolve().parents[1] / "frontend" / "out" / "_next" / "static"
    if export.is_dir():
        assert any(export.rglob("*.js")), "no hashed chunks under _next/static"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
