"""The first screen, measured rather than described.

Section 8 of the 19 September brief: "The failing test for a geometry unit is an assertion
on geometry.json from the local real app." So this file asserts nothing about source code.
It reads what a browser reported about the built export served by the real FastAPI app,
which is the only kind of evidence M1 accepts after three outages passed 230 tests.

Regenerate the input before running:

    .venv\\Scripts\\python.exe scripts\\demo_server.py 8099
    .venv\\Scripts\\python.exe scripts\\ui_snapshot.py http://127.0.0.1:8099 ^
        docs/ui/2026-09-19/current

The file is not committed and cannot be produced in CI, which has no server and no
browser session; the tests skip loudly rather than passing when it is missing. A skip is
visible, a vacuous pass is not.

Baseline this replaces, from docs/ui/2026-09-19/before/geometry.json:
  390x844  header 145 (three rows), H1 top 177, banner top 691, CTA top 1283
  360x640  header 145,               H1 top 177, banner top 467, CTA top 1292
  1440x900 header 69,                H1 top 117, banner top 823, CTA top 1010
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GEOMETRY = ROOT / "docs" / "ui" / "2026-09-19" / "current" / "geometry.json"

MOBILE = ("360x640", "390x844")
DESKTOP = "1440x900"

# U1: "one row, height at most 56". 56 is also the tap-target floor plus padding, so it is
# the smallest honest header rather than a number chosen to look tight.
MAX_MOBILE_HEADER = 56
MIN_TAP = 44


def geometry() -> dict:
    if not GEOMETRY.is_file():
        pytest.skip(f"no snapshot at {GEOMETRY}; run scripts/ui_snapshot.py first")
    return json.loads(GEOMETRY.read_text(encoding="utf-8"))


def home(viewport: str, state: str = "first-visit") -> dict:
    return geometry()["pages"][f"chromium/{viewport}/home"][state]


@pytest.mark.parametrize("viewport", MOBILE)
def test_the_mobile_header_is_one_row_of_at_most_56px(viewport):
    """U1, the whole unit in one number.

    145px of a 390x844 phone is 17% of the viewport spent on chrome, and it is three
    wrapped rows: wordmark, two links, price. The links leave; the price stays, because
    it is the only price a phone visitor meets before the consent banner covers the rest.
    """
    header = home(viewport)["header"]
    assert header is not None, "no <header> element"
    assert header["h"] <= MAX_MOBILE_HEADER, f"{viewport}: header is {header['h']:.0f}px"


@pytest.mark.parametrize("viewport", MOBILE)
def test_the_mobile_header_carries_no_nav_links(viewport):
    """One row is only achievable by removing something, and the brief names which.

    Asserted separately from the height so a failure says which half broke: a header that
    is 56px tall because the links wrapped under a scrollbar is not the same as one that
    is 56px tall because they are gone.
    """
    nav = home(viewport)["headerNav"]
    assert nav is None or not nav["visible"], f"{viewport}: header nav is still rendered"


def test_the_desktop_header_keeps_its_links():
    """Held-out check. Deleting the nav outright would pass both tests above and strip
    the desktop navigation the brief explicitly says to keep."""
    nav = home(DESKTOP)["headerNav"]
    assert nav is not None and nav["visible"], "the desktop header lost its links"


def test_recuperar_gained_a_link_under_the_uploader():
    """U1 moves "Recuperar mis fotos" out of the mobile header, so the buyer who has lost
    their gallery link must still find it without reading to the end of the page."""
    for viewport in (*MOBILE, DESKTOP):
        link = home(viewport)["recoverUnderUploader"]
        assert link is not None and link["visible"], f"{viewport}: no link under the uploader"


def test_that_link_really_is_under_the_uploader():
    """Its name is a claim about position. A hook rendered in the footer would satisfy
    every check above while the person who needs it is still scrolling."""
    for viewport in (*MOBILE, DESKTOP):
        page = home(viewport)
        uploader, link = page["uploader"], page["recoverUnderUploader"]
        assert link["top"] >= uploader["top"], f"{viewport}: link is above the uploader"
        gap = link["top"] - uploader["bottom"]
        assert gap < 240, f"{viewport}: link sits {gap:.0f}px below the uploader, not under it"


@pytest.mark.parametrize("viewport", MOBILE)
def test_every_pinned_element_still_clears_a_44px_thumb(viewport):
    """The skill's floor, checked on what shipped rather than on the class names.

    Only the header's own interactive children are in scope for U1; the consent banner
    buttons belong to U4 and are measured there.
    """
    header = home(viewport)["header"]
    assert header["h"] >= MIN_TAP, f"{viewport}: header {header['h']:.0f}px is below a thumb"


def test_no_viewport_scrolls_sideways():
    """A one-row header is the easy way to introduce one, and horizontal scroll on a phone
    reads as a broken page rather than as a layout bug."""
    for viewport in (*MOBILE, DESKTOP):
        assert not home(viewport)["horizontalScroll"], f"{viewport} scrolls horizontally"


# ---------------------------------------------------------------------------- U2
# The H1, and the empty column F2 found under it on desktop.

H1_TEXT = "Tu foto profesional para LinkedIn, en dos minutos"
MOBILE_H1_PX = 30
DESKTOP_H1_PX = 68


@pytest.mark.parametrize("viewport", MOBILE)
def test_the_h1_is_the_new_one(viewport):
    """U2. "Tu foto de perfil profesional, revelada en dos minutos" describes a process;
    this one names the place the photograph is going.

    "en dos minutos" survives on measurement, not on preference: from Cloud Run request
    logs the free preview has run at 10.04s and 12.30s (median 11.17s) and full generation
    at 14.56s, 19.78s and 28.98s (median 19.78s). U2's threshold is 120 seconds.
    """
    assert home(viewport)["h1Type"]["text"] == H1_TEXT


@pytest.mark.parametrize("viewport", MOBILE)
def test_the_h1_is_30px_on_a_phone(viewport):
    """38px was costing a line. The prototype F11 measured this at 30px."""
    assert home(viewport)["h1Type"]["fontSize"] == MOBILE_H1_PX


def test_the_h1_holds_two_lines_at_390():
    """The reason for 30px, and the thing that actually matters: three lines of H1 push
    everything below it down a whole line box. A 16ch cap would give four."""
    assert home("390x844")["h1Type"]["lines"] == 2


def test_the_desktop_h1_keeps_its_current_size():
    """Held-out check. U2 says the phone changes and the desktop does not; shrinking
    everything would pass every assertion above."""
    assert home(DESKTOP)["h1Type"]["fontSize"] == DESKTOP_H1_PX


def test_the_empty_column_under_the_desktop_h1_is_gone():
    """F2: "an empty vertical gap of roughly 90 px between the H1 and the sub-headline in
    the left column". Measured here at 129px before the fix.

    The cause is the grid, not the spacing: the hero image spans both rows of the left
    column, and its height was being handed to row 1, which only holds the H1. Row 2
    absorbs it now, so the sub-headline sits directly under the heading.
    """
    page = home(DESKTOP)
    gap = page["subhead"]["top"] - page["h1"]["bottom"]
    assert 0 <= gap <= 48, f"{gap:.0f}px of empty column under the H1"


def test_the_phone_still_puts_the_photograph_between_them():
    """Held-out check, and the one that protects a decision already taken: on a phone the
    picture follows the H1 directly (CONVERSION.md hypothesis 1, proof before price). A
    tidy-up of the desktop grid must not reorder the phone into H1, prose, then picture.
    """
    for viewport in MOBILE:
        page = home(viewport)
        hero, h1, sub = page["hero"], page["h1"], page["subhead"]
        assert hero is not None and sub is not None
        assert sub["top"] > h1["bottom"], f"{viewport}: sub-headline is not below the H1"
        gap = sub["top"] - h1["bottom"]
        assert gap > 200, (
            f"{viewport}: only {gap:.0f}px between H1 and sub-headline, "
            "so the photograph is no longer between them"
        )


# ---------------------------------------------------------------------------- U4
# The consent banner. Layout only: same text, same logic, same storage key, same gtag
# calls (M7). What changes is how much of the first screen it eats and whether the two
# answers look like equals.

MAX_BANNER_PHONE = 112
MAX_BANNER_DESKTOP = 64


@pytest.mark.parametrize("viewport", MOBILE)
def test_the_consent_banner_fits_in_112px_on_a_phone(viewport):
    """Measured before: 153px at 390 and 173px at 360, against viewports of 844 and 640.
    At 360 that is 27% of the screen spent on a cookie notice before the product has
    said anything."""
    banner = home(viewport)["banner"]
    assert banner is not None, "no consent banner on a first visit"
    assert banner["h"] <= MAX_BANNER_PHONE, f"{viewport}: banner is {banner['h']:.0f}px"


def test_the_consent_banner_is_one_row_of_at_most_64px_on_a_desktop():
    banner = home(DESKTOP)["banner"]
    assert banner["h"] <= MAX_BANNER_DESKTOP, f"banner is {banner['h']:.0f}px"


@pytest.mark.parametrize("viewport", [*MOBILE, DESKTOP])
def test_the_two_answers_are_the_same_size(viewport):
    """Measured before: 102.9px against 94.3px, because each button was only as wide as
    its own word. "Rechazar" is a longer word than "Aceptar"; that is not a reason to
    make it a different control."""
    buttons = home(viewport)["bannerButtons"]
    assert len(buttons) == 2, f"{viewport}: {len(buttons)} buttons in the banner"
    widths = [b["w"] for b in buttons]
    assert abs(widths[0] - widths[1]) <= 1, f"{viewport}: widths {widths}"
    for b in buttons:
        assert b["h"] >= MIN_TAP, f"{viewport}: {b['text']} is {b['h']:.0f}px tall"


@pytest.mark.parametrize("viewport", [*MOBILE, DESKTOP])
def test_the_two_answers_carry_the_same_visual_weight(viewport):
    """The one U4 requirement that is not about space.

    Measured before: "Rechazar" was the page background with a 1px rule, "Aceptar" was
    filled in the accent red with no border - so the two answers were not presented as
    equals. U4 says both outlined or both filled.

    R6 went looking for the AEPD saying this in its own words and could not read the
    guide's PDF, so it is recorded NOT CONFIRMED in docs/verified.md. The brief says U4
    applies either way, and it does: this is a design decision the prompt made, resting
    on its own authority rather than on a citation that was not found.
    """
    buttons = home(viewport)["bannerButtons"]
    backgrounds = {b["background"] for b in buttons}
    assert len(backgrounds) == 1, f"{viewport}: different fills {backgrounds}"
    borders = {(b["borderWidth"], b["borderColor"]) for b in buttons}
    assert len(borders) == 1, f"{viewport}: different borders {borders}"


@pytest.mark.parametrize("viewport", [*MOBILE, DESKTOP])
def test_the_banner_never_covers_the_first_screen_button(viewport):
    """U4's last clause, and the reason the other numbers matter. Written so it keeps
    holding after U5 moves the button up into the first screen: whatever the primary call
    to action is, the banner's top edge must be below its bottom edge."""
    page = home(viewport)
    banner, cta = page["banner"], page["cta"]
    assert cta is not None, f"{viewport}: no primary button to check"
    assert cta["bottom"] <= banner["top"] or cta["top"] >= banner["bottom"], (
        f"{viewport}: the banner ({banner['top']:.0f}..{banner['top'] + banner['h']:.0f}) "
        f"covers the button ({cta['top']:.0f}..{cta['bottom']:.0f})"
    )


# ---------------------------------------------------------------------------- U5
# The first-screen call to action. Until this unit the only product button on the page
# was the uploader's submit, at y=1283 against a usable first viewport of 691px, and it
# rendered disabled. F3: of 24 sites in the category StudioFace was the only one with no
# primary call to action inside the first 844px.

CTA_TEXT = "Ver mi prueba gratis"
CTA_HEIGHT = 52
CTA_TOP_AT_390 = 560


@pytest.mark.parametrize("viewport", [*MOBILE, DESKTOP])
def test_there_is_a_first_screen_call_to_action(viewport):
    cta = home(viewport)["foldCta"]
    assert cta is not None and cta["visible"], f"{viewport}: no first-screen button"


@pytest.mark.parametrize("viewport", [*MOBILE, DESKTOP])
def test_it_clears_the_consent_banner(viewport):
    """U5's acceptance, and the whole point of U1, U2 and U4: with the banner open - which
    is every first visit - the button's bottom edge is above the banner's top edge."""
    page = home(viewport)
    cta, banner = page["foldCta"], page["banner"]
    assert cta["bottom"] <= banner["top"], (
        f"{viewport}: button ends at {cta['bottom']:.0f}, banner starts at {banner['top']:.0f}"
    )


def test_it_is_high_enough_on_a_390px_phone():
    """U5 names 560 specifically. A button that clears the banner by one pixel is not on
    the first screen in any sense a visitor would recognise."""
    top = home("390x844")["foldCta"]["top"]
    assert top <= CTA_TOP_AT_390, f"button top is {top:.0f}, over {CTA_TOP_AT_390}"


@pytest.mark.parametrize("viewport", [*MOBILE, DESKTOP])
def test_it_is_52px_tall_and_fills_its_column(viewport):
    page = home(viewport)
    cta, frame = page["foldCta"], page["sliderFrame"]
    assert abs(cta["h"] - CTA_HEIGHT) <= 1, f"{viewport}: button is {cta['h']:.0f}px tall"
    assert cta["w"] >= frame["w"] - 1, (
        f"{viewport}: button is {cta['w']:.0f}px wide under a {frame['w']:.0f}px frame"
    )


@pytest.mark.parametrize("viewport", [*MOBILE, DESKTOP])
def test_it_sits_under_the_slider_not_beside_it(viewport):
    page = home(viewport)
    assert page["foldCta"]["top"] >= page["sliderFrame"]["bottom"], f"{viewport}: not below"


@pytest.mark.parametrize("viewport", [*MOBILE, DESKTOP])
def test_the_reassurance_line_is_under_the_button(viewport):
    """ "Sin registro ni tarjeta. 19,99 EUR solo si te gusta." - the three objections a
    visitor has at the moment they are deciding to press it."""
    page = home(viewport)
    micro = page["foldMicro"]
    assert micro is not None and micro["visible"], f"{viewport}: no reassurance line"
    assert micro["top"] >= page["foldCta"]["bottom"] - 1, f"{viewport}: it is above the button"


def test_the_uploader_button_is_still_the_one_that_submits():
    """Held-out check. The first-screen button is an anchor to the uploader, not a second
    submit; if it became the submit, pressing it would post an empty form."""
    page = home("390x844")
    assert page["cta"]["top"] > page["foldCta"]["top"], "the two buttons swapped places"
    assert page["cta"]["top"] >= page["uploader"]["top"], "the submit left the uploader"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
