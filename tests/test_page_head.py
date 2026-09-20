"""Unit page-head: the home page's <head> as production search engines and share
cards read it.

`scripts/check.py head` measured production red on 2026-09-20: no canonical link, no
og:image, no JSON-LD carrying the price. This file pins the same three facts against
the BUILT export, plus what the brief also asked for and the check script does not
verify byte-for-byte: the exact title, a description under 155 characters that still
names the price and the free preview, a Twitter card, an Organization block, the price
coming from the single existing constant (frontend/src/lib/config.ts PRICE_EUR) rather
than a second hard-coded "19.99", and the two things explicitly OUT of scope — no
ratings, no FAQ structured data — so a future edit does not add either back believing
it is "just more SEO".

Skipped without a fresh export, same convention as tests/test_seo.py.
"""

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_scan import strip_comments  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "frontend" / "out"
CONFIG = ROOT / "frontend" / "src" / "lib" / "config.ts"

pytestmark = pytest.mark.skipif(
    not (EXPORT / "index.html").is_file(),
    reason="no frontend/out — run `npm run build` in frontend/. CI builds before auditing.",
)

TITLE = "Foto de perfil profesional con IA para LinkedIn y CV | StudioFace"
LD_JSON_RE = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL)


@pytest.fixture
def html() -> str:
    return (EXPORT / "index.html").read_text(encoding="utf-8")


@pytest.fixture
def ld_blocks(html: str) -> list[dict]:
    return [json.loads(m) for m in LD_JSON_RE.findall(html)]


@pytest.fixture
def price_constant() -> str:
    # Comments stripped first (tests/test_source_scanners.py): a commented-out
    # "PRICE_EUR = ..." line must not be read as the live constant.
    text = strip_comments(CONFIG.read_text(encoding="utf-8"), language="ts")
    match = re.search(r"PRICE_EUR\s*=\s*([\d.]+)", text)
    assert match, "PRICE_EUR is missing from frontend/src/lib/config.ts"
    return f"{float(match.group(1)):.2f}"


def test_the_title_is_exact(html):
    assert f"<title>{TITLE}</title>" in html


def test_the_description_is_under_155_chars_and_names_price_and_preview(html):
    match = re.search(r'<meta name="description" content="([^"]*)"', html)
    assert match, "no meta description"
    description = match.group(1)
    assert len(description) < 155, f"{len(description)} chars: {description!r}"
    assert "19,99" in description
    assert "gratis" in description.lower()


def test_metadata_base_makes_the_canonical_and_og_urls_absolute(html):
    assert 'rel="canonical" href="https://studioface.app/"' in html


def test_og_image_is_the_static_share_jpeg(html):
    assert 'property="og:image" content="https://studioface.app/share.jpg"' in html
    assert 'property="og:image:width" content="1200"' in html
    assert 'property="og:image:height" content="630"' in html


def test_twitter_card_is_present_with_the_same_image(html):
    assert 'name="twitter:card" content="summary_large_image"' in html
    assert 'name="twitter:image" content="https://studioface.app/share.jpg"' in html


def test_json_ld_has_a_product_with_the_price_from_the_constant(ld_blocks, price_constant):
    assert price_constant == "19.99", "price_constant fixture disagrees with the brief"
    graph = _flatten(ld_blocks)
    products = [n for n in graph if n.get("@type") == "Product"]
    assert products, "no Product node in any application/ld+json block"
    offer = products[0]["offers"]
    assert offer["price"] == price_constant
    assert offer["priceCurrency"] == "EUR"


def test_json_ld_has_an_organization(ld_blocks):
    graph = _flatten(ld_blocks)
    assert any(n.get("@type") == "Organization" for n in graph)


def test_json_ld_carries_no_ratings_and_no_faq(ld_blocks):
    graph = _flatten(ld_blocks)
    assert not any(n.get("@type") == "FAQPage" for n in graph)
    for node in graph:
        assert "aggregateRating" not in node
        assert "review" not in node


def test_the_exact_check_script_regex_is_satisfied(html):
    """scripts/check.py head(), reproduced so a change to this page and a change to
    that script are never verified separately."""
    assert re.search(r'rel="canonical"', html)
    assert re.search(r'property="og:image"', html)
    assert re.search(r'application/ld\+json[^<]*>[^<]*"price"\s*:\s*"19\.99"', html)


def _flatten(blocks: list[dict]) -> list[dict]:
    nodes = []
    for block in blocks:
        nodes.extend(block.get("@graph", [block]))
    return nodes


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
