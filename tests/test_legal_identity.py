"""The three legal pages must name a real trader, and must not ship a placeholder.

Spain requires the trader's identity on the site: Ley 34/2002 (LSSI-CE) Art. 10 for the
aviso legal, RGPD Art. 13 for the identity of the controller on the privacy page, and
Real Decreto Legislativo 1/2007 for the pre-contractual information in the terms. A
page that renders "[PENDIENTE: NIF]" to a paying customer satisfies none of them.

The values are Kevin's and are the only ones permitted here. Nothing in this repository
may invent a trading name, a tax id or an address — a wrong one is worse than a visible
gap, because a visible gap is honest about being unfinished.

Asserted against the BUILT HTML, not the .tsx, because what a customer reads is the
export. The `Pending` component is also checked for extinction: leaving it in the
bundle with no caller is an invitation to use it again.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "frontend" / "out"
LEGAL_SRC = ROOT / "frontend" / "src" / "app" / "legal"

NAME = "limeralda"
TAX_ID = "Z3714124-C"
ADDRESS = "Maria de Molina 31"

PAGES = ("aviso-legal", "privacidad", "terminos")

pytestmark = pytest.mark.skipif(
    not EXPORT.is_dir(), reason="no frontend/out — CI builds before checking"
)


def html(page: str) -> str:
    return (EXPORT / "legal" / page / "index.html").read_text(encoding="utf-8", errors="ignore")


def test_no_legal_page_ships_a_placeholder():
    for page in PAGES + ("cookies",):
        assert "PENDIENTE" not in html(page), f"/legal/{page}/ still shows a placeholder"


def test_every_page_that_must_identify_the_trader_names_it():
    for page in PAGES:
        assert NAME in html(page), f"/legal/{page}/ does not name the trader"


def test_the_tax_id_and_address_appear_where_the_law_requires_them():
    """LSSI-CE Art. 10 (aviso legal) and RGPD Art. 13 (controller identity)."""
    for page in ("aviso-legal", "privacidad"):
        page_html = html(page)
        assert TAX_ID in page_html, f"/legal/{page}/ has no tax id"
        assert ADDRESS in page_html, f"/legal/{page}/ has no address"


def test_the_placeholder_component_has_no_callers_left():
    """Held-out check. Filling the three pages while leaving <Pending> wired up means
    the next unfinished value renders as a bracket on a live page again."""
    callers = [
        p
        for p in LEGAL_SRC.rglob("*.tsx")
        if re.search(r"<Pending>", p.read_text(encoding="utf-8"))
    ]
    assert not callers, f"still rendering placeholders: {[str(p.name) for p in callers]}"


def test_nothing_invented_a_second_identity():
    """Exactly one trading name across the legal pages. Two would mean someone guessed."""
    for page in PAGES:
        body = html(page).lower()
        for invented in ("studioface s.l", "studioface sl", "s.l.u", "limeralda s.l"):
            assert invented not in body, f"/legal/{page}/ invents a legal form: {invented!r}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
