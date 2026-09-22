"""structured-data-tells-the-truth (task 52).

Google Search Console flagged two non-critical merchant-listings issues on 22 Sep 2026:
missing hasMerchantReturnPolicy and missing shippingDetails in offers. Decision, taken
from Google's own pages and recorded in docs/DECISIONS.md and docs/verified.md, not
re-argued here:

- StudioFace sells generated images delivered by email, not a tangible product
  (support.google.com/merchants/answer/12077589 excludes "Services: labor, time,
  effort, expertise, or actions, which do not result in ownership of a tangible
  product"), so it can never appear as a merchant listing whatever the markup says.
  The Product markup stays because it earns the ordinary product snippet with the
  price (Google's product-snippet page allows that).
- shippingDetails is NOT added: there is no shipping, and a zero-cost zero-day
  shipping block would be a false statement about a service.
- hasMerchantReturnPolicy IS added, nested under Organization on /legal/terminos/ (the
  page Google's merchant-listing page recommends nesting it on), with the policy
  stated truthfully from the terms text: custom digital content, the right of
  withdrawal lost once delivered under artículo 103.m of Real Decreto Legislativo
  1/2007 (no returnable window is invented — returnPolicyCategory is
  MerchantReturnNotPermitted), applicableCountry ES, and merchantReturnLink pointing
  at a real anchor on that page, https://studioface.app/legal/terminos/#devoluciones.
  Every Product's offers references that policy node by "@id" instead of repeating it.

Asserted against the BUILT export, same convention as test_page_head.py and
test_legal_identity.py. Skipped without a fresh export.
"""

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "frontend" / "out"

pytestmark = pytest.mark.skipif(
    not (EXPORT / "index.html").is_file(),
    reason="no frontend/out — run `npm run build` in frontend/. CI builds before auditing.",
)

RETURN_POLICY_ID = "https://studioface.app/legal/terminos/#devoluciones"
LD_JSON_RE = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL)

# Every page whose Product markup carries an offer that must reference the policy.
PRODUCT_PAGES = ("index", "foto-cv/index", "foto-linkedin/index")


def html(relative: str) -> str:
    return (EXPORT / f"{relative}.html").read_text(encoding="utf-8", errors="ignore")


def ld_nodes(page_html: str) -> list[dict]:
    nodes = []
    for block in LD_JSON_RE.findall(page_html):
        parsed = json.loads(block)
        nodes.extend(parsed.get("@graph", [parsed]))
    return nodes


@pytest.mark.parametrize("page", PRODUCT_PAGES)
def test_every_products_offer_references_the_return_policy_by_id(page):
    nodes = ld_nodes(html(page))
    products = [n for n in nodes if n.get("@type") == "Product"]
    assert products, f"{page}: no Product node"
    offer = products[0]["offers"]
    assert offer.get("hasMerchantReturnPolicy") == {"@id": RETURN_POLICY_ID}, (
        f"{page}: offer must reference the policy by @id, not repeat or invent one"
    )


@pytest.mark.parametrize("page", PRODUCT_PAGES)
def test_no_product_page_invents_shippingDetails(page):
    """There is no shipping. A zero-cost zero-day shippingDetails block would be a
    false statement about a service that is delivered by email."""
    nodes = ld_nodes(html(page))
    for node in nodes:
        assert "shippingDetails" not in node


def test_the_terms_page_carries_the_policy_node_nested_under_organization():
    nodes = ld_nodes(html("legal/terminos/index"))
    organizations = [n for n in nodes if n.get("@type") == "Organization"]
    assert organizations, "terms page: no Organization node"
    policies = [
        n.get("hasMerchantReturnPolicy") for n in organizations if n.get("hasMerchantReturnPolicy")
    ]
    assert policies, "terms page: Organization node carries no hasMerchantReturnPolicy"
    policy = policies[0]
    assert policy["@type"] == "MerchantReturnPolicy"
    assert policy["@id"] == RETURN_POLICY_ID
    assert policy["applicableCountry"] == "ES"


def test_the_policy_states_no_returnable_window_is_invented():
    """Google's category for "no returns accepted" — the only category that matches
    custom digital content whose withdrawal right is already lost on delivery."""
    nodes = ld_nodes(html("legal/terminos/index"))
    policy = next(n["hasMerchantReturnPolicy"] for n in nodes if n.get("hasMerchantReturnPolicy"))
    assert policy["returnPolicyCategory"] == "https://schema.org/MerchantReturnNotPermitted"
    assert "returnPolicyDays" not in policy, "no returnable window exists — none may be invented"


def test_the_merchant_return_link_points_at_a_real_anchor_on_the_page():
    """The @id doubles as merchantReturnLink here (both are the same fragment URL) —
    this proves the fragment is not a dead link: the page itself carries an element
    with that id, so a visitor who follows it actually lands on the returns text."""
    page_html = html("legal/terminos/index")
    nodes = ld_nodes(page_html)
    policy = next(n["hasMerchantReturnPolicy"] for n in nodes if n.get("hasMerchantReturnPolicy"))
    assert policy["merchantReturnLink"] == RETURN_POLICY_ID
    assert 'id="devoluciones"' in page_html, (
        "the #devoluciones fragment has no matching element on the page"
    )


def test_the_policy_text_matches_the_terms_the_page_actually_states():
    """The markup must not invent anything the terms page does not say: custom
    digital content, withdrawal lost on delivery under artículo 103.m of Real
    Decreto Legislativo 1/2007, and a separate automatic full refund when the four
    images cannot be produced."""
    page_html = html("legal/terminos/index")
    assert "103.m" in page_html
    assert "Real Decreto Legislativo" in page_html
    assert "se devuelve el importe" in page_html or "reembolso" in page_html.lower()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
