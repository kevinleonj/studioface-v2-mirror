"""Would the outside-in check have caught the three outages? Answered, not asserted.

Each fixture in tests/fixtures/production/ reproduces one of them as it actually
appeared, and the check is pointed at it. A verifier that has never been shown a broken
page is a verifier nobody has tested — which is precisely the position the whole test
suite was in when three outages went out.

The third outage is covered by the pure-HTTP half too: `check_preflight_is_not_needed`
reports what a preflight does, so the report says which world it is in rather than
assuming.
"""

import http.server
import os
import socketserver
import sys
import threading
from functools import partial
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify_production import (  # noqa: E402
    BLOCKED,
    FAIL,
    OK,
    Check,
    Result,
    _same_origin,
    _turnstile,
    check_preview,
)

FIXTURES = Path(__file__).parent / "fixtures" / "production"
playwright = pytest.importorskip("playwright.sync_api", reason="playwright not installed here")


@pytest.fixture(scope="module", autouse=True)
def browser_available():
    """Skipping locally is fine. Skipping on CI is not.

    pip installs the playwright PACKAGE; the browser binary is a separate download, and
    the first CI run of this file went red with "Executable doesn't exist". The obvious
    repair is to skip when the browser is missing — which would have turned the only
    tests that can see the last two outages into a silent no-op on the one machine that
    matters. So: a skip on a laptop, a FAILURE on CI, where the workflow installs it."""
    try:
        with playwright.sync_playwright() as pw:
            pw.chromium.launch().close()
    except Exception as exc:  # noqa: BLE001 - any launch failure means no browser
        message = f"chromium will not launch: {exc}"
        if os.environ.get("CI") == "true":
            hint = "run: python -m playwright install --with-deps chromium"
            pytest.fail(f"{message} | {hint}")
        pytest.skip(message)


@pytest.fixture(scope="module")
def served():
    """A real HTTP server on a real socket. Serving the fixtures from disk rather than
    with a stubbed fetch, because the point of this layer is that nothing is stubbed."""
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(FIXTURES))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
        httpd.shutdown()


def visit(served: str, page_name: str):
    """Load a fixture in a real browser and hand back the page plus what it requested."""
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        requests: list[str] = []
        page.on("request", lambda r: requests.append(r.url))
        page.goto(f"{served}/{page_name}", wait_until="load")
        page.wait_for_timeout(700)
        yield page, requests
        browser.close()


def test_it_catches_the_turnstile_widget_that_never_mounted(served):
    """Outage 2. The container is in the document and empty, which is exactly what
    production served: `widget children=0, token fields=0` at every time point for ten
    seconds. A check that only asked "is the div there" would have passed."""
    for page, _ in visit(served, "broken-turnstile.html"):
        link, status, evidence = _turnstile(page)
        assert link == "turnstile widget"
        assert status == FAIL, f"the check passed a page with no widget: {evidence}"
        assert "never mounted" in evidence
        assert "403" in evidence, "the evidence does not say what it costs the customer"


def test_it_catches_the_cross_origin_api_call(served):
    """Outage 3. The page calls /api on another hostname; the preflight 405s and the
    customer is told "No hemos podido conectar."."""
    for _, requests in visit(served, "cross-origin.html"):
        link, status, evidence = _same_origin(served, requests)
        assert link == "same-origin api calls"
        assert status == FAIL, f"the check passed a cross-origin page: {evidence}"
        assert "api.studioface.test" in evidence


def test_it_does_not_fire_on_the_third_party_scripts_a_healthy_page_loads():
    """The check's own first version failed on `brunhild.challenges.cloudflare.com` and
    `region1.google-analytics.com`, which are how Turnstile and GA4 shard. A check that
    fires on a healthy page teaches people to ignore it, which is worse than no check."""
    healthy = [
        "https://studioface.app/",
        "https://studioface.app/api/preview",
        "https://brunhild.challenges.cloudflare.com/cdn-cgi/challenge-platform/x",
        "https://region1.google-analytics.com/g/collect?v=2",
        "https://fonts.gstatic.com/s/newsreader/x.woff2",
    ]
    link, status, evidence = _same_origin("https://studioface.app", healthy)
    assert status == OK, f"fired on a healthy page: {evidence}"


def test_an_undeclared_third_party_origin_is_still_a_failure():
    """Held-out check. Loosening the rule to fix the false positive must not loosen it
    into accepting anything: a script from an origin nobody declared is a finding."""
    _, status, evidence = _same_origin(
        "https://studioface.app", ["https://tracker.example.test/pixel.gif"]
    )
    assert status == FAIL
    assert "tracker.example.test" in evidence


def test_the_preview_link_is_reported_blocked_rather_than_faked():
    """The rule for a link an anti-automation control makes unreachable: say which, do
    not fake it, and name the human step. A verifier that quietly skips a step is how a
    green report and a dead funnel coexist."""
    status, evidence = check_preview("https://studioface.app", None)
    assert status == BLOCKED
    assert "human step: phone preview test" in evidence
    assert "interactive challenge" in evidence


def test_the_blocked_line_does_not_point_at_a_closed_issue():
    """Task 95h. It named issue #4 as the human step; #4 was closed on 22 September, so
    every deploy log sent the reader to a finished ticket."""
    _, evidence = check_preview("https://studioface.app", None)
    assert "issue #4" not in evidence and "#4" not in evidence


def test_a_failure_is_reported_with_the_link_that_broke():
    """The report has to name the link, not just fail. "Production is down" sends
    somebody looking; "turnstile widget never mounted" sends them to the line."""
    result = Result()
    result.add(Check("health", OK, "fine"))
    result.add(Check("turnstile widget", FAIL, "never mounted"))
    result.add(Check("free preview", BLOCKED, "needs a token"))
    assert [c.link for c in result.broken] == ["turnstile widget"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
