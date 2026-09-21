"""An address without the final slash was forwarding to http:// and then back to
https://, both marked temporary.

Measured against production, 21 Sep 2026:

    GET https://studioface.app/legal/privacidad
    307 -> http://studioface.app/legal/privacidad/

Two independent causes, both fixed here.

1. Cloud Run's front end terminates TLS and forwards the request to the container
   over a plain connection, setting X-Forwarded-Proto: https. uvicorn's
   `--proxy-headers` middleware is already ON by default, but it only trusts that
   header from an address in `--forwarded-allow-ips`, which itself defaults to
   `127.0.0.1,::1`. Cloud Run's connecting address is neither, so the header was
   read and then ignored, and Starlette built its own redirect from the literal
   (plain-http) connection scheme. docs/verified.md O1/O2.

2. Even with the right scheme, Starlette's StaticFiles (serving the Next.js export,
   `CachedStatic` below) answers a bare directory path with a 307 by construction
   (starlette/staticfiles.py). A 307 is TEMPORARY: no browser or CDN may cache it,
   so every visit to `/legal/privacidad` paid for two hops forever. The address
   always means the same thing, so it is a single 308 (PERMANENT, and unlike 301
   guarantees method/body are replayed unchanged - free here since this route only
   ever serves GET/HEAD) straight to the correct scheme.

Cause 1 is fixed in the Dockerfile's CMD (uvicorn flags) and cannot be exercised by
a TestClient, which talks to the ASGI app directly and never goes through uvicorn's
CLI or its ProxyHeadersMiddleware - so it is pinned here by reading the Dockerfile's
own text. Cause 2 is exercised for real: TestClient with an https:// base_url puts
"https" in the ASGI scope exactly as a correctly-configured uvicorn would after
trusting Cloud Run's header, and the test asserts what CachedStatic answers with
that scope.
"""

import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import OrderStore, Pipeline  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import make_app  # noqa: E402

DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


def _cmd_line() -> str:
    text = DOCKERFILE.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.strip().startswith("CMD")]
    assert len(lines) == 1, "expected exactly one CMD in the Dockerfile"
    return lines[0]


def test_uvicorn_is_told_to_trust_cloud_runs_proxy():
    """--proxy-headers is already the uvicorn default, but naming it here is what
    makes --forwarded-allow-ips mean anything - and Cloud Run's front end is not
    127.0.0.1, uvicorn's own default trust list (docs/verified.md O1)."""
    cmd = _cmd_line()
    assert "--proxy-headers" in cmd
    assert "--forwarded-allow-ips" in cmd


def test_forwarded_allow_ips_is_not_left_at_the_useless_default():
    """127.0.0.1,::1 (uvicorn's default) never matches Cloud Run's connecting
    address, so leaving it unset would keep --proxy-headers a no-op. Cloud Run
    containers are reachable only through Cloud Run's own ingress (docs/verified.md
    O2), so trusting every connecting address inside the container is the documented
    shape of the fix, not a guess."""
    cmd = _cmd_line()
    match = re.search(r"--forwarded-allow-ips[= ]\"?([^\"\s]+)\"?", cmd)
    assert match, f"--forwarded-allow-ips has no value in: {cmd}"
    assert match.group(1) not in ("127.0.0.1,::1", "127.0.0.1", "::1")


@pytest.fixture
def app_with_export(tmp_path):
    legal = tmp_path / "legal" / "privacidad"
    legal.mkdir(parents=True)
    (legal / "index.html").write_text("<h1>Privacidad</h1>", encoding="utf-8")
    (tmp_path / "index.html").write_text("<h1>StudioFace</h1>", encoding="utf-8")
    store = OrderStore()
    pipeline = Pipeline(
        store=store,
        model=type("M", (), {"edit": lambda self, u, p: "x"})(),
        storage=type("S", (), {"put": lambda self, k, u: k})(),
        send_email=lambda t, b: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret="sfx",
    )
    return make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter()),
        enqueue=lambda i: None,
        preview_fn=lambda f, b: "",
        webhook_secret="whsec",
        tasks_token="tt",
        static_dir=str(tmp_path),
    )


def test_the_no_slash_address_answers_a_single_permanent_redirect_straight_to_https(
    app_with_export,
):
    """The regression. Measured on production: 307 to http://, then a second hop back
    to https://. With the scope's scheme already https (what a correctly configured
    uvicorn hands the app, per the Dockerfile fix), this must be the ONE answer: a
    permanent redirect to the https address, with no detour through http anywhere."""
    client = TestClient(app_with_export, base_url="https://testserver")
    r = client.get("/legal/privacidad", follow_redirects=False)
    assert r.status_code in (301, 308), f"got {r.status_code}, wanted 301 or 308"
    assert r.headers["location"] == "https://testserver/legal/privacidad/"


def test_the_redirect_is_not_the_307_temporary_default(app_with_export):
    """Held out separately from the status-code assertion above: a test that only
    checks `in (301, 308)` would keep passing if a future edit reintroduced Starlette's
    stock 307 alongside some unrelated permanent redirect elsewhere. This fails on
    exactly the temporary code, which is the actual defect."""
    client = TestClient(app_with_export, base_url="https://testserver")
    r = client.get("/legal/privacidad", follow_redirects=False)
    assert r.status_code != 307


def build_preview_client(**limiter_kwargs):
    store = OrderStore()
    pipeline = Pipeline(
        store=store,
        model=type("M", (), {"edit": lambda self, u, p: "x"})(),
        storage=type("S", (), {"put": lambda self, k, u: k})(),
        send_email=lambda t, b: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret="sfx",
    )
    limiter = RateLimiter(
        counter=MemoryCounter(), per_subnet=1000, daily_global=1000, **limiter_kwargs
    )
    app = make_app(
        pipeline,
        limiter,
        enqueue=lambda i: None,
        preview_fn=lambda files, batch: "https://storage.googleapis.com/x",
        webhook_secret="whsec",
        tasks_token="tt",
    )
    return TestClient(app)


JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100


def _preview(client, forwarded_for):
    files = [("files", ("a.jpg", JPEG, "image/jpeg"))]
    return client.post(
        "/api/preview",
        files=files,
        data={"turnstile_token": "good"},
        headers={"x-forwarded-for": forwarded_for},
    )


def test_preview_rate_limit_keys_on_the_trailing_forwarded_for_entry():
    """Superseded by task 14 (tests/test_visitor_address.py), which found the
    opposite of what this test used to assert: the LEFTMOST entry is whatever the
    connecting client put in its own request, so a script could rotate it and dodge
    this very cap. Google Front End is the single hop between the internet and this
    container (docs/verified.md 13c) and appends the address it actually observed,
    so that TRAILING entry - not the visitor-supplied leading one - is what the
    ceiling must count against."""
    client = build_preview_client(per_client=1)
    same_visitor_new_leading_entry = _preview(client, "1.2.3.4, 10.0.0.5")
    assert same_visitor_new_leading_entry.status_code == 200
    same_visitor_spoofed_leading_entry = _preview(client, "9.9.9.9, 10.0.0.5")
    # Task 29: being capped no longer means a 429 — /api/preview stores the photos
    # and signs a handle instead (`limited: true`). That field can only be true if
    # RateLimiter.check keyed this second request the same as the first, so it is
    # still the proof this test is named for.
    assert same_visitor_spoofed_leading_entry.status_code == 200
    assert same_visitor_spoofed_leading_entry.json()["limited"] is True, (
        "the same visitor spoofing a new leading entry must still be capped"
    )


def test_preview_rate_limit_does_not_key_on_a_shared_leading_entry():
    """The mirror: two different visitors who happen to share a leading entry (one
    of them copied it, or both went through the same declared but unverifiable
    upstream) must be counted separately, which is only true if the key is the
    trailing, GFE-appended entry - never the visitor-controlled leading one."""
    client = build_preview_client(per_client=1)
    first_visitor = _preview(client, "1.2.3.4, 10.0.0.5")
    assert first_visitor.status_code == 200
    second_visitor_same_leading_entry = _preview(client, "1.2.3.4, 10.0.0.9")
    assert second_visitor_same_leading_entry.status_code == 200, (
        "a different visitor (different trailing entry) must not inherit another "
        "visitor's cap just because they share a leading entry"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
