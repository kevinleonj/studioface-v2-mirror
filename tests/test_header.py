"""The page had no <header> at all, and no route to the recovery page from the top.

Measured in the build before this existed: zero `<header>` elements across ten pages.
The wordmark existed only in the footer, "Recuperar mis fotos" only in the footer, and
there was no anchor to how it works. A buyer who has lost their gallery link is exactly
the person who will not scroll to the end of a page to look for it.

What this deliberately is not is a navigation bar. One product, one price; five links
across the top would be a page pretending to be an application, which is its own tell.

It is also NOT sticky. The skill forbids anything fixed covering content at scroll 0,
the consent banner already owns 129px at the bottom, and a sticky header would spend
56px of an 844px phone viewport on chrome for a page you scroll once.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "frontend" / "out"
HEADER = ROOT / "frontend" / "src" / "components" / "site-header.tsx"

pytestmark = pytest.mark.skipif(not EXPORT.is_dir(), reason="no build; CI builds first")


def pages() -> list[Path]:
    return sorted(EXPORT.rglob("*.html"))


def test_every_page_has_a_header_element():
    missing = [
        p.relative_to(EXPORT).as_posix()
        for p in pages()
        if "<header" not in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not missing, f"pages with no <header>: {missing}"


def test_the_header_carries_the_four_things_a_buyer_looks_for():
    html = (EXPORT / "index.html").read_text(encoding="utf-8", errors="ignore")
    head = html[html.index("<header") : html.index("</header>")]
    assert "StudioFace" in head, "no wordmark"
    assert 'href="/"' in head, "the wordmark does not go home"
    assert "#como-funciona" in head, "no anchor to how it works"
    assert "/recuperar/" in head, "recovery is still only reachable from the footer"
    assert "19,99" in head, "no price"


def test_the_header_price_says_what_the_price_includes():
    """The hero rework pushed the price block below the visible slot on a phone: with
    the consent banner up the slot is 691px and "19,99 € / IVA incluido, pago único"
    renders at y=819. The header is therefore the only price a first visit sees, and a
    bare figure with no tax basis is not a price to a Spanish consumer."""
    html = (EXPORT / "index.html").read_text(encoding="utf-8", errors="ignore")
    head = html[html.index("<header") : html.index("</header>")]
    assert "IVA" in head, "the header shows a bare figure with no tax basis"


def test_the_header_is_not_a_navigation_bar():
    """Held-out check. The failure mode here is scope creep into a SaaS nav: the moment
    it holds six links it stops orienting and starts pretending."""
    html = (EXPORT / "index.html").read_text(encoding="utf-8", errors="ignore")
    head = html[html.index("<header") : html.index("</header>")]
    assert len(re.findall(r"<a\b", head)) <= 4, "the header has grown into a nav bar"
    assert "hamburger" not in head.lower()
    assert "<button" not in head, "a menu button hiding two links is worse than two links"


def test_the_header_is_not_fixed_or_sticky():
    """Nothing may cover content at scroll 0, and a sticky header on a phone spends the
    first viewport on chrome.

    Checked against the className strings, not the whole file: the words "fixed" and
    "sticky" both appear in the comment explaining why it is neither, and a test that
    greps its own rationale proves nothing. Self-heal caught me doing exactly this with
    core.hooksPath a few commits ago."""
    classes = " ".join(re.findall(r'className="([^"]*)"', HEADER.read_text(encoding="utf-8")))
    assert "sticky" not in classes, "a sticky header covers content at scroll 0"
    assert "fixed" not in classes


def test_the_recovery_link_is_now_reachable_from_the_top_of_every_page():
    """The whole reason the header exists. Footer-only was reachable from nowhere a
    lost buyer would look."""
    for page in pages():
        html = page.read_text(encoding="utf-8", errors="ignore")
        head = html[html.index("<header") : html.index("</header>")]
        assert "/recuperar/" in head, f"{page.relative_to(EXPORT)} header has no recovery link"


def test_the_trader_is_identified_on_every_page_not_only_in_legal():
    """LSSI-CE Art. 10, and the cheapest trust signal a stranger can read. It appeared
    zero times on the landing page before this."""
    for page in pages():
        html = page.read_text(encoding="utf-8", errors="ignore")
        assert "limeralda" in html, f"{page.relative_to(EXPORT)} does not name the trader"
        assert "Z3714124-C" in html, f"{page.relative_to(EXPORT)} has no NIF"


def test_the_page_is_honest_about_what_payment_it_accepts():
    """Bizum is not enabled yet (GO-LIVE blocks it on refund reconciliation), so the
    page must not imply it. Saying 'tarjeta' is the honest claim today."""
    html = (EXPORT / "index.html").read_text(encoding="utf-8", errors="ignore")
    assert "tarjeta" in html.lower(), "no payment expectation near the CTA"
    assert "Bizum" not in html, "Bizum is not accepted yet; claiming it would be a lie"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
