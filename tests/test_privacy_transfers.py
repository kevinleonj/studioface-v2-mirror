"""Task 93: the privacy page names every transfer outside the European Economic Area.

GDPR article 13(1)(f) requires telling the visitor about a transfer to a third country
and the safeguard it rests on. The page used to say only that "some" providers "may"
process data outside the EEA "with the guarantees the GDPR provides", which names
neither the country nor the safeguard. Issue #7.

Every fact below comes from the vendor's own page and is recorded in docs/verified.md
(task 93 lines, accessed 2026-09-23). Two countries are NOT confirmed on the vendor's own
pages - fal's and Cloudflare's - so for those the page says the data may leave the EEA
and that the vendor does not publish the country. It must never name a country nobody
verified; the last test here guards exactly that.

The mechanism names are the official Spanish wording from the titles of the two
Commission decisions (docs/verified.md): "cláusulas contractuales tipo" (Decisión de
Ejecución (UE) 2021/914) and "Marco de Privacidad de Datos UE-EE. UU." (Decisión de
Ejecución (UE) 2023/1795).
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_scan import strip_comments  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "frontend" / "src" / "app" / "legal" / "privacidad" / "page.tsx"

SCC = "cláusulas contractuales tipo"
DPF = "Marco de Privacidad de Datos UE-EE. UU."
US = "Estados Unidos"
# For a vendor whose own pages do not name the country (docs/verified.md: no confirmado).
NO_COUNTRY = "no publica el país"
GOOGLE_TRANSFERS = "https://business.safety.google/adsdatatransfers/"

# vendor name as written on the page -> (country phrase, mechanism, vendor document)
TRANSFERS = {
    "Resend": (US, SCC, "https://resend.com/legal/dpa"),
    "Stripe": (US, DPF, "https://stripe.com/legal/dta"),
    "fal.ai": (NO_COUNTRY, SCC, "https://fal.ai/legal/data-processing-addendum"),
    "Cloudflare": (NO_COUNTRY, SCC, "https://www.cloudflare.com/cloudflare-customer-dpa/"),
    "Google Analytics 4": (US, DPF, GOOGLE_TRANSFERS),
    "Google Ads": (US, DPF, GOOGLE_TRANSFERS),
}

# sha256 of every byte of page.tsx OUTSIDE the "Destinatarios" section. Pinned at 20fcb7e
# (task 93); re-pinned in task 95f for ONE change, the `updated` date on <LegalPage>,
# proven by recomputing the old file with only that line swapped (same hash). If you edit
# another section on purpose, re-read it as legal text, then update this value.
OUTSIDE_DESTINATARIOS_SHA256 = "fffea1c4653e6c80de236d11b977e9231e53105a37e3c439283d0c0f1a9c42fc"


def _raw() -> str:
    return PAGE.read_text(encoding="utf-8").replace("\r\n", "\n")


def _section_bounds(page: str) -> tuple[int, int]:
    start = page.index("<H2>Destinatarios</H2>")
    return start, page.index("<H2>", start + 1)


def _items(page: str) -> list[str]:
    start, end = _section_bounds(page)
    section = strip_comments(page[start:end], language="tsx")
    return [" ".join(item.split()) for item in re.findall(r"<li>(.*?)</li>", section, re.S)]


def problems(page: str) -> list[str]:
    """Every missing fact, one line each. Empty means the section is complete."""
    found = []
    items = _items(page)
    for vendor, (country, mechanism, document) in TRANSFERS.items():
        item = next((i for i in items if vendor in i), None)
        if item is None:
            found.append(f"{vendor}: not named as a recipient")
            continue
        for label, needle in (
            ("country", country),
            ("mechanism", mechanism),
            ("document", f'href="{document}"'),
        ):
            if needle not in item:
                found.append(f"{vendor}: {label} missing ({needle!r})")
    return found


def test_every_transfer_names_the_country_the_mechanism_and_the_vendor_document():
    assert problems(_raw()) == []


def test_a_page_missing_resend_is_caught():
    """Meta-test: the check above can fail. Drop Resend's item and it must say so."""
    page = _raw()
    without = re.sub(r"<li>(?:(?!</li>).)*Resend.*?</li>", "", page, flags=re.S)
    assert without != page, "fixture did not remove anything; the meta-test is vacuous"
    assert any(p.startswith("Resend:") for p in problems(without)), problems(without)


def test_google_analytics_and_google_ads_are_recipients():
    items = " ".join(_items(_raw()))
    assert "Google Analytics 4" in items and "Google Ads" in items


def test_the_mechanisms_cite_the_two_commission_decisions():
    start, end = _section_bounds(_raw())
    section = " ".join(strip_comments(_raw()[start:end], language="tsx").split())
    assert "Decisión de Ejecución (UE) 2021/914" in section, section
    assert "Decisión de Ejecución (UE) 2023/1795" in section, section


def test_every_other_section_is_byte_identical():
    page = _raw()
    start, end = _section_bounds(page)
    outside = (page[:start] + page[end:]).encode("utf-8")
    assert hashlib.sha256(outside).hexdigest() == OUTSIDE_DESTINATARIOS_SHA256


def test_the_retention_sentences_are_still_there_word_for_word():
    text = " ".join(_raw().split())
    assert "Las fotografías que subes se borran automáticamente a los 7 días." in text
    kept = "Las imágenes generadas se conservan 1 año para que puedas volver a descargarlas."
    assert kept in text


def test_no_unverified_country_is_ever_named():
    """Nobody asked for this one, and it is the likeliest way this page goes wrong: a
    later tidy-up "fixing" fal or Cloudflare to Estados Unidos. Their own pages do not say
    so (docs/verified.md), and a privacy page must not state what nobody verified."""
    for item in _items(_raw()):
        if "fal.ai" in item or "Cloudflare" in item:
            assert US not in item, item


# ------------------------------------------------ task 95f: Cloudflare's second role

TURNSTILE_ADDENDUM = "https://www.cloudflare.com/turnstile-privacy-policy/"


def _cloudflare_item() -> str:
    return next(i for i in _items(_raw()) if "Cloudflare" in i)


def test_cloudflare_names_its_controller_role_for_turnstile_signals():
    """docs/verified.md (task 95f): Cloudflare's Turnstile Privacy Addendum, verbatim,
    "Cloudflare is a data controller of Signals that we process to improve Turnstile's
    bot detection capabilities". The page says so and links the addendum."""
    item = _cloudflare_item()
    assert "responsable del tratamiento" in item, item
    assert "detección de bots" in item, item
    assert f'href="{TURNSTILE_ADDENDUM}"' in item, item


def test_the_controller_role_is_not_called_independent():
    """Nobody asked for this one. The brief said "independent controller"; Cloudflare's
    page never uses the word (0 matches in its raw HTML, 23 Sep 2026), so the page must
    not add it."""
    assert "independiente" not in _cloudflare_item()


def test_the_page_says_when_it_was_last_updated():
    assert 'updated="23 de septiembre de 2026"' in _raw()
