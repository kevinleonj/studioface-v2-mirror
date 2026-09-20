"""robots.txt and sitemap.xml must exist in the static export and the API must serve
both at 200.

`scripts/check.py robots` and `scripts/check.py sitemap` measured production red on
2026-09-20: no /robots.txt, no /sitemap.xml. Both are Next.js file conventions
(app/robots.ts, app/sitemap.ts) that the static export turns into real files at the
export root, served by the same StaticFiles mount as everything else.

It asserts against frontend/out, so it only means anything when the export is fresh —
same convention as tests/test_footer_links.py.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "frontend" / "out"

sys.path.insert(0, str(ROOT))
from app.core import OrderStore, Pipeline  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import make_app  # noqa: E402

REQUIRED_DISALLOWS = ("/g/", "/api/", "/internal/", "/recuperar/")
LEGAL_PAGES = (
    "/legal/aviso-legal/",
    "/legal/privacidad/",
    "/legal/terminos/",
    "/legal/cookies/",
)

pytestmark = pytest.mark.skipif(
    not EXPORT.is_dir(),
    reason="no frontend/out — run `npm run build` in frontend/. CI builds before auditing.",
)


@pytest.fixture
def client():
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
        static_dir=str(EXPORT),
    )
    return TestClient(app)


def test_robots_txt_is_in_the_export():
    path = EXPORT / "robots.txt"
    assert path.is_file(), f"{path} does not exist — add frontend/src/app/robots.ts"


def test_sitemap_xml_is_in_the_export():
    path = EXPORT / "sitemap.xml"
    assert path.is_file(), f"{path} does not exist — add frontend/src/app/sitemap.ts"


def test_robots_txt_allows_the_site_and_disallows_the_private_paths():
    body = (EXPORT / "robots.txt").read_text(encoding="utf-8")
    assert "Allow: /" in body
    for path in REQUIRED_DISALLOWS:
        assert f"Disallow: {path}" in body, f"robots.txt does not disallow {path}"
    assert "Sitemap: https://studioface.app/sitemap.xml" in body


def test_sitemap_xml_lists_home_and_the_four_legal_pages():
    body = (EXPORT / "sitemap.xml").read_text(encoding="utf-8")
    assert "https://studioface.app/</loc>" in body, "sitemap.xml lacks the home address"
    for page in LEGAL_PAGES:
        assert f"https://studioface.app{page}</loc>" in body, f"sitemap.xml lacks {page}"


def test_the_api_serves_robots_txt_at_200(client):
    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert "Disallow: /api/" in r.text


def test_the_api_serves_sitemap_xml_at_200(client):
    r = client.get("/sitemap.xml")
    assert r.status_code == 200
    assert "studioface.app" in r.text


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
