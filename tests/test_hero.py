"""The hero, decided from screenshots and measurements rather than from the argument.

Two shapes were built and both were measured on a served copy of the real export, at
390x844 and 1440x900, with the consent banner up — because the banner is up on every
first visit, and measuring against 844 is measuring a page nobody is looking at. The
usable slot on a phone is 691px, not 844.

    variant                    "despues" rendered      visible in the 691px slot
    A, even pair               170 x 212               85px of 212   (40%)
    B, inset, old order        340 x 425               85px of 425   (20%)
    D, inset, photo after H1   340 x 340               340px of 340  (100%)

B doubles the linear size of the thing being sold, exactly as the round-4 critique
predicted. But on a phone it was WORSE than A: a bigger picture starting at y=606
inside a 691px slot shows more of the top of someone's hair and no face at all. The
argument could not have produced that; only the screenshot did.

So the shape is B and the order is new. The photograph now follows the H1 directly on a
phone, and the price moves below the slot — which is fine, and deliberate: the header
carries the price, so "the price is above the fold" is still true, discharged by the
element that is above the fold on every page rather than by the hero alone.

The square crop on mobile is 85px shorter than 4:5, and the thing being sold is a
profile picture, which is square everywhere it will be used.
"""

import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPORT = Path(os.environ.get("SF_EXPORT", ROOT / "frontend" / "out"))
MUESTRAS = ROOT / "frontend" / "src" / "components" / "muestras.tsx"

pytestmark = pytest.mark.skipif(
    not (EXPORT / "index.html").exists(), reason="no build; CI builds first"
)


def body() -> str:
    """The rendered markup between the header and the footer.

    Both ends matter. The header carries the price, so a position test that counted its
    copy would pass no matter what the hero did. And Next inlines the whole RSC flight
    payload in <script> tags after the footer — every className appears there a second
    time, escaped, so a naive slice to the end of the file finds the hero's classes
    inside what is supposed to be the gallery. That is how the first version of
    test_the_gallery_keeps_the_even_pair failed against a page that was correct."""
    html = (EXPORT / "index.html").read_text(encoding="utf-8", errors="ignore")
    return html[html.index("</header>") : html.index("</footer>")]


def hero() -> str:
    """The first <figure> of the body is the hero pair; the rest are the gallery."""
    text = body()
    start = text.index("<figure")
    return text[start : text.index("</figure>", start)]


def test_the_first_photograph_comes_before_the_price():
    """docs/CONVERSION.md hypothesis 1. It did not: the old order put 606px of prose in
    front of the only photograph on a 390px viewport, so the proof arrived after the
    price, the payment copy and the AI disclosure."""
    text = body()
    photo = re.search(r"<img[^>]*muestras/[^>]*-despues", text)
    price = text.index("19,99")
    assert photo, "no muestra photograph in the body of the page"
    assert photo.start() < price, (
        "the price reaches the visitor before any photograph does; "
        f"photo at {photo.start()}, price at {price}"
    )


def test_the_hero_is_the_comparison_slider_not_the_even_pair():
    """Unit U3 replaced the inset thumbnail with a slider. The reasoning that chose the
    inset over the even pair still holds and is still enforced here: an even 50/50 split
    spends half of the only photograph on the problem rather than on the product.

    The shape assertions this replaced (`w-[34%]`, `aspect-square sm:aspect-[4/5]`) were
    the inset's, and the inset was deleted with U3. tests/test_comparador.py carries the
    slider's own contract; this one only holds the hero to being it.
    """
    mark = hero()
    assert "sf-ba" in mark, "the hero is not the comparison slider"
    assert "grid-cols-2" not in mark, "the hero is the even 50/50 pair again"


def test_the_hero_frame_is_square_on_a_phone():
    """Unchanged requirement, moved from a Tailwind class to plain CSS by M14: square on a
    phone is 85px shorter than 4:5, which is the difference between the whole face being
    inside the 691px slot and the top of a head being inside it."""
    css = (ROOT / "frontend" / "src" / "app" / "globals.css").read_text(encoding="utf-8")
    rule = re.search(r"\.sf-ba\s*\{([^}]*)\}", css)
    assert rule, "no .sf-ba rule"
    assert "aspect-ratio: 1 / 1" in rule.group(1), "the hero frame is 4:5 on a phone again"


def test_the_gallery_keeps_the_even_pair():
    """Held-out check. The inset is right for the hero, where one image is the product
    and the other is the disclosure. In the gallery the visitor is comparing, and there
    the two are equals — so this must NOT have been applied everywhere."""
    rest = body()
    rest = rest[rest.index("</figure>") :]
    assert "grid-cols-2" in rest, "the gallery lost the even pair"
    assert "sf-ba" not in rest, "the hero's comparison slider leaked into the gallery"


def test_both_labels_sit_on_paper_not_on_the_photograph():
    """Over a photograph, the contrast of a label is whatever that photograph happens to
    be at that corner: unmeasurable, and different for every pair. The labels were
    muted-foreground text laid directly on the image. On an opaque paper chip it is ink
    on paper, 16.1:1, the same on every pair (tests/test_contrast.py)."""
    src = MUESTRAS.read_text(encoding="utf-8")
    chip = re.search(r"function Chip\(.*?\n\}", src, re.S)
    assert chip, "no Chip component"
    assert "bg-[color:var(--background)]" in chip.group(0), "the label chip is transparent"
    for label in ("Antes", "Después"):
        assert f"<Chip>{label}</Chip>" in src or f">{label}</span>" in src, label


def test_the_price_is_carried_by_the_element_that_is_always_above_the_fold():
    """The hero photograph pushes the price below the 691px slot on a phone. That is
    only acceptable because the header holds it, so this is the assertion that makes the
    trade honest rather than a regression nobody noticed."""
    html = (EXPORT / "index.html").read_text(encoding="utf-8", errors="ignore")
    head = html[html.index("<header") : html.index("</header>")]
    assert "19,99" in head, "the price left the header while the hero stopped showing it"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
