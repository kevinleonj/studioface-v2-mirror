"""The tripwire on the one page in the walk that nobody documents.

A4.4a warned that every selector on checkout.stripe.com is unversioned UI. The paid walk
put five fal images behind those selectors, so drift there is expensive to discover and
reads as a funnel defect when it is not one.

This test spends NOTHING. It creates a test-mode session, fills the card form, and stops
at the pay button without pressing it - pressing it would land on the local success_url
and start a real generation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_FUNNEL") != "1",
    reason="creates a real test-mode Stripe session; set RUN_FUNNEL=1",
)


def _hosted_session_url() -> str:
    """The same call the funnel harness makes, so the session shape under test is ours."""
    if not os.environ.get("STRIPE_SECRET_KEY"):
        import run_funnel

        run_funnel.load_environment()
    import stripe

    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    from tests.e2e.funnel_app import _checkout

    return _checkout("http://127.0.0.1:8099")("contract", 1, "corporativo", "", "")


def test_the_card_form_is_where_the_walk_reaches_for_it():
    from playwright.sync_api import sync_playwright

    from tests.e2e.stripe_checkout_page import SUBMIT, fill_test_card

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_context(viewport={"width": 1280, "height": 1200}).new_page()
        try:
            # NOT networkidle: the hosted page keeps connections open and never reaches
            # it. fill_test_card waits for the fields it needs.
            page.goto(_hosted_session_url(), wait_until="domcontentloaded")
            fill_test_card(page)
            assert page.get_by_test_id(SUBMIT).is_enabled(), "the pay button never became usable"
        finally:
            browser.close()
