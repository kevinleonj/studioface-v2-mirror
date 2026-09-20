"""Every built page must link the four legal pages AND the recovery page.

The recovery path shipped with nothing anywhere linking to it: a buyer who closed the
gallery tab and lost the delivery email had no route back into a product they had paid
for. Fixed in 1ec5e9b by adding it to the shared footer.

This test exists because "it is in the shared footer" is a claim about a component,
and what ships is HTML. Next renders that footer into ten separate static files; a
route that opted out of the layout, or a page built before the change, would be
invisible to any test that reads the .tsx.

It asserts against frontend/out, so it only means anything when the export is fresh —
which scripts/ci.py now enforces separately (tests/test_export_freshness.py).
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "frontend" / "out"

REQUIRED_LINKS = (
    "/legal/aviso-legal/",
    "/legal/privacidad/",
    "/legal/terminos/",
    "/legal/cookies/",
    "/recuperar/",
)

pytestmark = pytest.mark.skipif(
    not EXPORT.is_dir(),
    reason="no frontend/out — run `npm run build` in frontend/. CI builds before auditing.",
)


def pages() -> list[Path]:
    return sorted(EXPORT.rglob("*.html"))


def test_the_export_has_pages_to_check():
    assert pages(), f"no HTML under {EXPORT}"


def test_every_page_links_every_required_page():
    """Including the 404: someone who mistypes a gallery link lands there, and that is
    precisely the person who needs the recovery link."""
    missing: list[str] = []
    for page in pages():
        html = page.read_text(encoding="utf-8", errors="ignore")
        for href in REQUIRED_LINKS:
            if f'href="{href}"' not in html:
                missing.append(f"{page.relative_to(EXPORT)} -> {href}")
    assert not missing, "pages missing a required footer link:\n" + "\n".join(missing)


def test_the_recovery_link_is_not_only_on_the_landing_page():
    """Held-out check. The landing page is the one anybody would spot-check by eye, so
    it is the one place a regression would hide."""
    others = [p for p in pages() if p.relative_to(EXPORT).as_posix() != "index.html"]
    assert others, "expected more than one built page"
    for page in others:
        html = page.read_text(encoding="utf-8", errors="ignore")
        assert 'href="/recuperar/"' in html, f"{page.relative_to(EXPORT)} has no recovery link"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
