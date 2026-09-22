"""The delivery email is the moment the customer decides whether paying was wise.

It used to be the bare gallery URL as the entire plain-text body. To a person that
looks like phishing; to a spam filter a naked link with no text alternative, no sender
identity and no context looks like bulk. Both readings cost money, and it lands at the
worst possible moment.

These are pure functions, so the whole thing is testable without Resend.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import emails  # noqa: E402

LINK = "https://studioface.app/g/?o=cs_test_1&t=abc123"


def both_parts(email) -> str:
    return f"{email.html}\n{email.text}"


# ---------------------------------------------------------------- delivery


def test_delivery_carries_the_link_in_both_parts():
    """Some corporate clients render the text part and nothing else. A link that only
    exists in the HTML is, for those people, no link at all."""
    e = emails.delivery(LINK)
    assert LINK in e.html
    assert LINK in e.text


def test_delivery_is_not_just_a_url():
    """The actual regression. The whole body used to be the link."""
    e = emails.delivery(LINK)
    assert e.text.strip() != LINK
    assert len(e.text) > 200, "the text part is barely longer than the URL itself"


def test_delivery_has_a_clickable_button_and_a_copyable_fallback():
    e = emails.delivery(LINK)
    assert f'href="{LINK}"' in e.html
    assert e.html.count(LINK) >= 2, "no plain fallback for a client that eats the button"


def test_delivery_warns_that_the_download_links_expire():
    """Fifteen minutes. Someone who opens the mail on Monday needs to know the page
    still works, or they will assume the product is broken and ask for their money."""
    for part in (emails.delivery(LINK).html, emails.delivery(LINK).text):
        assert "15 minutos" in part


def test_delivery_states_the_retention_promise():
    text = emails.delivery(LINK).text
    assert "un año" in text
    assert "7 días" in text


# ---------------------------------------------------------------- refund


def test_refund_says_what_happened_and_that_nothing_is_required():
    e = emails.refund()
    assert "devolvemos el importe" in e.text
    assert "No tienes que hacer nada" in e.text or "no tienes que hacer nada" in e.text.lower()


def test_refund_does_not_pretend_the_money_is_already_back():
    """The pipeline refunds automatically and a refund can still be pending. Promising
    it has landed is the same lie the order status used to tell."""
    assert "unos días" in emails.refund().text


# ---------------------------------------------------------------- both


@pytest.mark.parametrize("make", [lambda: emails.delivery(LINK), emails.refund])
def test_every_email_identifies_the_trader(make):
    """LSSI-CE Art. 10. The same identity as /legal, not a different one."""
    both = both_parts(make())
    assert "limeralda" in both
    assert "Z3714124-C" in both


@pytest.mark.parametrize("make", [lambda: emails.delivery(LINK), emails.refund])
def test_every_email_discloses_ai_and_offers_a_way_to_reply(make):
    both = both_parts(make())
    assert "inteligencia artificial" in both
    assert emails.SUPPORT in both


@pytest.mark.parametrize("make", [lambda: emails.delivery(LINK), emails.refund])
def test_every_email_has_a_subject_that_says_something(make):
    subject = make().subject
    assert 10 < len(subject) < 80, subject
    assert "StudioFace" in subject or "importe" in subject


@pytest.mark.parametrize("make", [lambda: emails.delivery(LINK), emails.refund])
def test_styles_are_inline_because_gmail_strips_style_blocks(make):
    html = make().html
    assert "<style" not in html.lower(), "Gmail drops <style> blocks; use inline attributes"
    assert 'style="' in html


# ---------------------------------------------------------------- the sentinel


def test_the_refund_sentinel_still_routes_to_the_refund_message():
    """The pipeline's port passes a link or the literal "REFUND". Preserved so this
    change stays confined to what the customer sees; the poor contract is a follow-up."""
    assert emails.for_body(emails.REFUND_SENTINEL).subject == emails.refund().subject
    assert emails.for_body(LINK).subject == emails.delivery(LINK).subject


def test_a_link_that_merely_contains_the_word_refund_is_still_a_delivery():
    """Held-out check: sniffing a sentinel out of a body is fragile, so pin that it is
    an exact match and not a substring test."""
    sneaky = "https://studioface.app/g/?o=cs_REFUND_1&t=abc"
    assert emails.for_body(sneaky).subject == emails.delivery(sneaky).subject


@pytest.mark.parametrize("make", [lambda: emails.delivery(LINK), emails.refund])
def test_no_email_opens_with_a_tracked_allcaps_eyebrow(make):
    """Third occurrence of the same tell, in the one surface the audit cannot see.

    scripts/design_audit.py reads frontend/out. The email is Python, so the header

        font-size:11px;letter-spacing:.2em;text-transform:uppercase

    survived both rounds of killing skill cluster 5 on the page — .sf-label went, the
    page went to 0 P0, and the thing the customer actually receives after paying kept
    the exact device. Same rule as everywhere else: the wordmark is the name.
    """
    html = make().html
    assert "text-transform:uppercase" not in html, "tracked ALL-CAPS eyebrow (skill cluster 5)"
    assert "letter-spacing:.2em" not in html


def test_the_trader_line_is_not_a_middot_meta_string():
    """`a · b · c` is the same cluster: a meta string pretending to be metadata."""
    assert " · " not in emails.TRADER, "middot meta string (skill cluster 5)"


def test_no_email_contains_an_unrendered_placeholder():
    for e in (emails.delivery(LINK), emails.refund()):
        assert not re.search(r"\{[a-z_]+\}", e.html), e.html[:200]
        assert "PENDIENTE" not in both_parts(e)


# ---------------------------------------------------------------- task 44
#
# old-links-through-a-real-mail-client. Neither call site that ever hands send_email a
# real gallery link — app/core.py's Pipeline.run (the delivery email) and app/main.py's
# /api/recuperar (the recover email) — had ever had the link it builds actually run
# through this module's template. tests/test_money_path.py and tests/test_recuperar.py
# already prove each call site builds the fragment shape; nothing proved the template
# keeps it that way once rendered, rather than, say, HTML-escaping the "&" into "&amp;"
# and silently breaking the one link the customer needs. GALLERY_BASE and
# delivery_token are imported from app.core (not retyped) so a change to either real
# construction is felt here, not just in a copy of today's literal.


def _real_gallery_link(order_id: str) -> str:
    """The exact expression both app/core.py's Pipeline.run and app/main.py's
    /api/recuperar use to build the link they hand to send_email."""
    from app.core import GALLERY_BASE, delivery_token

    token = delivery_token(order_id, "task-44-fake-secret")
    return f"{GALLERY_BASE}#o={order_id}&t={token}"


def test_the_delivery_email_renders_the_fragment_shape_never_the_query_shape():
    """app/core.py's Pipeline.run hands this exact shape to send_email, which
    app/entry.py routes through emails.for_body straight into emails.delivery."""
    link = _real_gallery_link("cs_test_44_delivery_fake")
    e = emails.for_body(link)
    assert link in e.html and link in e.text
    assert "?o=" not in e.html and "?o=" not in e.text, "query shape must never appear"


def test_the_recover_email_renders_the_fragment_shape_never_the_query_shape():
    """/api/recuperar mints its own token for a resend but builds the identical
    GALLERY_BASE + '#o=...&t=...' shape and hands it to the same send_email port, so
    it reaches the same template. Proven separately from the delivery case above so a
    regression in either call site is caught on its own."""
    link = _real_gallery_link("cs_test_44_recover_fake")
    e = emails.for_body(link)
    assert link in e.html and link in e.text
    assert "?o=" not in e.html and "?o=" not in e.text, "query shape must never appear"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
