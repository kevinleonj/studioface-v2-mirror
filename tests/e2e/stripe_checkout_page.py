"""Driving Stripe's hosted Checkout page, which no vendor documents.

docs/verified.md A4.4a, 19 September: neither Stripe nor Playwright documents selectors
or a supported recipe for `ui_mode: hosted_page`. What IS documented is the test card
(4242 4242 4242 4242, any future date, any three-digit CVC). Everything else here is
unversioned Stripe UI that can change without notice.

So it lives in one named place with one tripwire on it - tests/e2e/test_stripe_hosted_page.py
- rather than inline in the paid walk, where drift costs five fal images to discover.
"""

from __future__ import annotations

CARD = "4242424242424242"
SUBMIT = "hosted-payment-submit-button"
CARD_METHOD = "card-accordion-item"


def fill_test_card(page, card: str = CARD, email: str = "walk@studioface.app") -> None:
    """Choose the card method, then fill it.

    Two things measured on the live page on 20 September, both of which the walk's
    first version got wrong (docs/audit/paid-walk-2026-09-20.txt):

    - With several payment methods enabled the page renders a COLLAPSED accordion -
      Tarjeta, Klarna, Bancontact, EPS - and no card field exists in the DOM until the
      card item is chosen. Waiting on a card placeholder waits forever.
    - The fields are addressed by `id`, not by placeholder. Placeholders are localised
      (the page came up German under a default browser locale, Spanish under es-ES), and
      Playwright cannot even compile `re.compile("MM ?/ ?[YA]")` into a placeholder
      selector: the `/` ends the attribute value and it raises InvalidSelectorError.
    """
    # Whichever arrives first: the accordion (several methods) or the bare card form
    # (card only). Counting before the page has rendered is how this silently skipped
    # the click and then waited thirty seconds for a field that was never coming.
    page.wait_for_selector(f"#cardNumber, [data-testid={CARD_METHOD}]", timeout=60_000)
    method = page.get_by_test_id(CARD_METHOD)
    if method.count():
        method.first.click()
    page.wait_for_selector("#cardNumber", timeout=30_000)

    address = page.locator("#email")
    if address.count() and not address.input_value():
        address.fill(email)
    page.locator("#cardNumber").fill(card)
    page.locator("#cardExpiry").fill("12 / 34")
    page.locator("#cardCvc").fill("123")
    name = page.locator("#billingName")
    if name.count():
        name.fill("Test Persona")


def pay(page) -> None:
    page.get_by_test_id(SUBMIT).click()
