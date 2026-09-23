"""Task 95d: /sobre-nosotros/ says who runs StudioFace, with nothing invented.

Search engines and AI answers weigh who is behind a site. Every fact on this page is
already published on the legal pages (aviso legal, términos, the footer): the trading
registered as Kevin Daniel León Jouvin, NIF Z3714124-C, Calle de Diego de León 13, 7º A,
28006 Madrid (task 96a), hola@studioface.app; plus
that Kevin runs it from Madrid. No team size, no founding story, no customer counts, no
awards: none of those are true yet, or verified, and an invented one is exactly what
Google's guidance on trust warns against.

The Organization JSON-LD gains `logo` (the 180x180 apple-icon.png) on home, términos and
this page. Not on the /foto-cv/ and /foto-linkedin/ ad landing component: those pages are
frozen while the ad test runs. No `sameAs`: Kevin confirmed no public profile exists yet.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_scan import strip_comments  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend" / "src" / "app"
PAGE = APP / "sobre-nosotros" / "page.tsx"
HOME = APP / "page.tsx"
TERMINOS = APP / "legal" / "terminos" / "page.tsx"
AD_LANDING = ROOT / "frontend" / "src" / "components" / "ad-landing.tsx"
PAGE_DATES = ROOT / "frontend" / "src" / "content" / "page-dates.ts"
BUILT = ROOT / "frontend" / "out" / "sobre-nosotros" / "index.html"
LOGO = "https://studioface.app/apple-icon.png"
URL = "https://studioface.app/sobre-nosotros/"

FACTS = (
    "Kevin Daniel León Jouvin",
    "Madrid",
    "Z3714124-C",
    "Calle de Diego de León 13, 7º A, 28006 Madrid",
    "hola@studioface.app",
)
# Words that would only appear in a claim nobody has verified.
INVENTED = re.compile(
    r"\b(líder|mejor|miles|cientos|clientes satisfechos|años de experiencia|fundad[ao] en"
    r"|nuestro equipo|expertos|premiad[ao]|garantizamos|n[.º°]\s*1)\b",
    re.IGNORECASE,
)


def _code(path: Path) -> str:
    return strip_comments(path.read_text(encoding="utf-8"), language="tsx")


def test_the_page_states_every_fact_the_legal_pages_already_publish():
    code = " ".join(_code(PAGE).split())
    for fact in FACTS:
        assert fact in code, fact


def test_the_page_invents_nothing():
    """Must be refused: a claim no legal page backs."""
    assert INVENTED.findall(_code(PAGE)) == []


def test_the_invented_claim_check_can_fail():
    """Meta-test: the pattern above does catch the claims it exists for."""
    assert INVENTED.findall("Somos líderes, con miles de clientes y años de experiencia.")


def test_the_page_declares_its_canonical_and_organization_with_logo_and_no_same_as():
    code = _code(PAGE)
    assert f'canonical: "{URL}"' in code
    assert f'logo: "{LOGO}"' in code
    assert "sameAs" not in code


def test_home_and_terminos_organizations_gain_the_logo():
    for path in (HOME, TERMINOS):
        assert f'logo: "{LOGO}"' in _code(path), path


def test_the_ad_landing_component_is_untouched():
    """The /foto-cv/ and /foto-linkedin/ pages are frozen during the ad test."""
    assert "logo" not in _code(AD_LANDING) and "sobre-nosotros" not in _code(AD_LANDING)


def test_home_and_terminos_link_to_the_page():
    for path in (HOME, TERMINOS):
        assert 'href="/sobre-nosotros/"' in _code(path), path


def test_the_page_is_in_the_sitemap_config():
    assert '"/sobre-nosotros/":' in PAGE_DATES.read_text(encoding="utf-8")


@pytest.mark.skipif(not BUILT.is_file(), reason="no frontend/out; run the build")
def test_the_built_page_carries_the_facts_canonical_and_json_ld():
    html = BUILT.read_text(encoding="utf-8")
    assert f'<link rel="canonical" href="{URL}"' in html
    for fact in FACTS:
        assert fact in html, fact
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    orgs = [json.loads(b) for b in blocks if '"Organization"' in b]
    assert orgs and orgs[0]["logo"] == LOGO and "sameAs" not in orgs[0]


@pytest.mark.skipif(not BUILT.is_file(), reason="no frontend/out; run the build")
def test_the_logo_the_json_ld_names_is_in_the_export():
    assert (ROOT / "frontend" / "out" / "apple-icon.png").is_file()
