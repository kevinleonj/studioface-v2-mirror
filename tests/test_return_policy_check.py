"""scripts/check.py's return_policy guard (task 52, structured-data-tells-the-truth).

Reads /legal/terminos/ and one Product page (/) from outside, the same way every other
check in this file works, and verifies what tests/test_return_policy.py already pins
against the built export: the terms page carries a MerchantReturnPolicy node nested
under Organization with the #devoluciones @id, and the Product page's offer references
that same @id.

One case that must be refused (both pages exactly as they are today, before this task's
markup exists) and one that must get through (both pages carrying the finished markup).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check  # noqa: E402

RETURN_POLICY_ID = "https://studioface.app/legal/terminos/#devoluciones"

TERMS_HTML_MISSING = "<html><body><h2>Derecho de desistimiento</h2><p>103.m</p></body></html>"

TERMS_HTML_PRESENT = (
    '<html><body><h2 id="devoluciones">Derecho de desistimiento</h2><p>103.m</p>'
    '<script type="application/ld+json">'
    '{"@context":"https://schema.org","@type":"Organization","name":"StudioFace",'
    '"hasMerchantReturnPolicy":{"@type":"MerchantReturnPolicy",'
    f'"@id":"{RETURN_POLICY_ID}","applicableCountry":"ES",'
    '"returnPolicyCategory":"https://schema.org/MerchantReturnNotPermitted",'
    f'"merchantReturnLink":"{RETURN_POLICY_ID}"'
    "}}</script></body></html>"
)

PRODUCT_HTML_MISSING = (
    '<html><body><script type="application/ld+json">'
    '{"@type":"Product","offers":{"@type":"Offer","price":"19.99"}}'
    "</script></body></html>"
)

PRODUCT_HTML_PRESENT = (
    '<html><body><script type="application/ld+json">'
    '{"@type":"Product","offers":{"@type":"Offer","price":"19.99",'
    f'"hasMerchantReturnPolicy":{{"@id":"{RETURN_POLICY_ID}"}}}}'
    "}</script></body></html>"
)


def _pages(terms_html: str, product_html: str):
    def fake_get(path: str) -> tuple[int, str]:
        if path == "/legal/terminos/":
            return 200, terms_html
        if path == "/":
            return 200, product_html
        raise AssertionError(
            f"return_policy must only read /legal/terminos/ and /, asked for {path}"
        )

    return fake_get


def test_return_policy_is_refused_when_neither_page_carries_the_markup(monkeypatch):
    """Must be refused: production exactly as it stood on 22 Sep 2026, before this
    task — the state Search Console actually flagged."""
    monkeypatch.setattr(check, "get", _pages(TERMS_HTML_MISSING, PRODUCT_HTML_MISSING))
    problems = check.return_policy()
    assert problems, "missing policy node and missing offer reference must be refused"


def test_return_policy_is_refused_when_the_offer_does_not_reference_the_node(monkeypatch):
    monkeypatch.setattr(check, "get", _pages(TERMS_HTML_PRESENT, PRODUCT_HTML_MISSING))
    problems = check.return_policy()
    assert problems, "an offer with no hasMerchantReturnPolicy reference must be refused"


def test_return_policy_is_refused_when_the_referenced_id_is_never_declared(monkeypatch):
    monkeypatch.setattr(check, "get", _pages(TERMS_HTML_MISSING, PRODUCT_HTML_PRESENT))
    problems = check.return_policy()
    assert problems, "an @id reference to a policy node that does not exist must be refused"


def test_return_policy_gets_through_when_both_pages_carry_the_finished_markup(monkeypatch):
    """Must get through: the one state this task ships — real policy node, real
    reference, real anchor."""
    monkeypatch.setattr(check, "get", _pages(TERMS_HTML_PRESENT, PRODUCT_HTML_PRESENT))
    assert check.return_policy() == []


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
