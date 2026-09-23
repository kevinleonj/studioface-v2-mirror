"""Task 95a: every <lastmod> in sitemap.xml is a content date, never the build time.

sitemap.ts used to stamp every URL with `new Date()`, so each deploy told search engines
that every page had just changed. Crawlers learn to ignore a lastmod that always moves;
IndexNow (task 95b) submits exactly the URLs whose lastmod changed, so a moving lastmod
would resubmit the whole site on every deploy.

The dates live in one file, frontend/src/content/page-dates.ts, seeded from each page's
last content commit (`git log -1 --format=%cs`, 23 September 2026) and edited by hand when
a page's content changes.

The literal requirement - two builds 60 s apart give byte-identical sitemap.xml - costs
about two and a half minutes of builds, so it runs only with SITEMAP_TWO_BUILDS=1 (and
did, for this task). What runs everywhere is the reason it holds: sitemap.ts reads no
clock and takes every date from the config.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_scan import strip_comments  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
SITEMAP_TS = FRONTEND / "src" / "app" / "sitemap.ts"
PAGE_DATES = FRONTEND / "src" / "content" / "page-dates.ts"
BUILT = FRONTEND / "out" / "sitemap.xml"
SITE = "https://studioface.app"
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
CLOCK = re.compile(r"\bnew\s+Date\s*\(|\bDate\.now\s*\(|performance\.now\s*\(")


def clock_calls(source: str) -> list[str]:
    """Every call that reads the clock, in code (comments stripped)."""
    return CLOCK.findall(strip_comments(source, language="ts"))


def config_dates() -> dict[str, str]:
    text = strip_comments(PAGE_DATES.read_text(encoding="utf-8"), language="ts")
    return dict(re.findall(r'"(/[^"]*)"\s*:\s*"(\d{4}-\d{2}-\d{2})"', text))


def test_sitemap_source_reads_no_clock():
    assert clock_calls(SITEMAP_TS.read_text(encoding="utf-8")) == []


def test_the_clock_check_catches_new_date():
    """Meta-test: a fixture that stamps build time must fail the check above."""
    fixture = 'export default function s() { return [{ url: "x", lastModified: new Date() }]; }'
    assert clock_calls(fixture) != []
    assert clock_calls("const t = Date.now();") != []
    assert clock_calls("// new Date() in a comment is not a call\nconst x = 1;") == []


def test_sitemap_takes_its_dates_from_the_config_file():
    code = strip_comments(SITEMAP_TS.read_text(encoding="utf-8"), language="ts")
    assert "PAGE_DATES" in code and "page-dates" in code


def test_every_config_date_is_a_real_iso_date_not_in_the_future():
    dates = config_dates()
    assert dates, "no dates parsed from page-dates.ts"
    for path, day in dates.items():
        assert path.startswith("/") and path.endswith("/"), path
        assert "2026-09-01" <= day <= time.strftime("%Y-%m-%d", time.gmtime()), (path, day)


def _built_lastmods(xml_bytes: bytes) -> dict[str, str]:
    root = ET.fromstring(xml_bytes)
    found = {}
    for url in root.findall("s:url", NS):
        path = url.findtext("s:loc", namespaces=NS).removeprefix(SITE)
        found[path] = url.findtext("s:lastmod", namespaces=NS)
    return found


@pytest.mark.skipif(not BUILT.is_file(), reason="no frontend/out - run `npm run build`")
def test_every_built_lastmod_equals_the_config_date():
    assert _built_lastmods(BUILT.read_bytes()) == config_dates()


def _build_sitemap(frontend: Path) -> bytes:
    npm = shutil.which("npm") or "npm"
    subprocess.run(
        [npm, "run", "build"], cwd=frontend, check=True, capture_output=True, timeout=600
    )
    return (frontend / "out" / "sitemap.xml").read_bytes()


def _two_builds(frontend: Path) -> tuple[bytes, bytes]:
    first = _build_sitemap(frontend)
    time.sleep(61)
    return first, _build_sitemap(frontend)


CLOCK_SITEMAP = """import type { MetadataRoute } from "next";
export const dynamic = "force-static";
export default function sitemap(): MetadataRoute.Sitemap {
  return [{ url: "https://studioface.app/", lastModified: new Date() }];
}
"""

TWO_BUILDS = pytest.mark.skipif(
    os.environ.get("SITEMAP_TWO_BUILDS") != "1",
    reason="two full builds 60 s apart (~2.5 min); set SITEMAP_TWO_BUILDS=1",
)


@TWO_BUILDS
def test_two_builds_sixty_seconds_apart_give_identical_sitemaps():
    first, second = _two_builds(FRONTEND)
    assert first == second


@TWO_BUILDS
def test_two_builds_with_a_clock_in_the_sitemap_differ():
    """Meta-test of the one above: put `new Date()` back and the two builds must differ,
    or the byte comparison proves nothing. Done in place, not on a copy - copying
    node_modules costs more than the builds - and the real sitemap.ts is restored in
    `finally` and checked byte for byte afterwards."""
    original = SITEMAP_TS.read_bytes()
    SITEMAP_TS.write_text(CLOCK_SITEMAP, encoding="utf-8")
    try:
        first, second = _two_builds(FRONTEND)
    finally:
        SITEMAP_TS.write_bytes(original)
    assert SITEMAP_TS.read_bytes() == original
    assert first != second
