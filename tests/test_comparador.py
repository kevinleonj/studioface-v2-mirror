"""U3: the before/after comparison slider, and the crop that makes it honest.

The hero used to hang a small "antes" in the corner of a large "después". F5 measured why
that was the wrong shape for a comparison: the "después" is 928x1152 with the face filling
the frame and the "antes" is 400x501 with a smaller one, so the two faces are not the same
face at the same size, and a slider laid over them slides one face across a different one.

Two halves, tested separately because they fail separately:

  the crop      scripts/align_muestras.py, whose numbers are checked here arithmetically
                rather than by looking at the output
  the control   a real <input type="range"> under an invisible layer, which is what keeps
                the keyboard, the drag, the touch target and the slider semantics

Every source scan strips comments first (M4). This file's own prose contains
`clip-path`, `44px` and `type="range"`, and a scan that read its own comments would pass
against a page that had none of them.
"""

import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

from source_scan import strip_comments  # noqa: E402

EXPORT = Path(os.environ.get("SF_EXPORT", ROOT / "frontend" / "out"))
CSS = ROOT / "frontend" / "src" / "app" / "globals.css"
COMPONENT = ROOT / "frontend" / "src" / "components" / "comparador.tsx"

pytestmark = pytest.mark.skipif(
    not (EXPORT / "index.html").exists(), reason="no build; CI builds first"
)

CAPTION = (
    "Persona ficticia generada con IA. El resultado se ha producido con el mismo proceso "
    "por el que pasan tus fotos."
)


def css() -> str:
    return strip_comments(CSS.read_text(encoding="utf-8"), language="css")


def rule(selector: str) -> str:
    """The body of one CSS rule, so an assertion cannot be satisfied by a different one."""
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css())
    assert match, f"no rule for {selector}"
    return match.group(1)


def hero_html() -> str:
    html = (EXPORT / "index.html").read_text(encoding="utf-8", errors="ignore")
    body = html[html.index("</header>") : html.index("</footer>")]
    start = body.index("<figure")
    return body[start : body.index("</figure>", start)]


# ------------------------------------------------------------------ the crop


def test_the_two_crops_put_the_faces_at_the_same_size_and_the_eyes_on_one_line():
    """U3's numeric requirement, recomputed from the landmarks rather than trusted.

    The eyes are the landmark because they are the only feature with two unambiguous
    points, so the distance between them measures scale without anyone deciding where a
    cheek ends.
    """
    from align_muestras import ASPECT, PAIRS, crop_boxes
    from PIL import Image

    muestras = ROOT / "frontend" / "public" / "muestras"
    for key, pair in PAIRS.items():
        antes = Image.open(muestras / f"{key}-antes.jpg")
        despues = Image.open(muestras / f"{key}-despues.jpg")
        boxes = crop_boxes(pair, antes, despues)
        widths, lines = {}, {}
        for side in ("antes", "despues"):
            left, top, right, bottom, ipd, eye_y = boxes[side]
            widths[side] = ipd / (right - left)
            lines[side] = (eye_y - top) / (bottom - top)
            assert abs((right - left) / (bottom - top) - ASPECT) < 0.01, f"{side} is not 4:5"
        drift = abs(widths["antes"] - widths["despues"]) / widths["antes"] * 100
        assert drift <= 4, f"{key}: faces differ in width by {drift:.2f}%, over U3's 4%"
        assert abs(lines["antes"] - lines["despues"]) < 0.01, f"{key}: eyes are not on one line"


def test_the_crops_exist_and_are_the_same_shape():
    """The component references them by name; a missing file is a broken hero, and a pair
    at two different pixel sizes divides into two different grids under the clip."""
    from PIL import Image

    muestras = ROOT / "frontend" / "public" / "muestras"
    sizes = set()
    for side in ("antes", "despues"):
        for suffix in (".jpg", ".webp"):
            path = muestras / f"mujer-40-{side}-hero{suffix}"
            assert path.is_file(), f"{path.name} was never produced"
            sizes.add(Image.open(path).size)
    assert len(sizes) == 1, f"the cropped pair is not one size: {sizes}"


def test_the_originals_are_untouched():
    """Held-out check. U3 says produce crops FROM the existing sources; overwriting them
    would pass every test above and destroy the only copy of the gallery's images."""
    from PIL import Image

    muestras = ROOT / "frontend" / "public" / "muestras"
    assert Image.open(muestras / "mujer-40-antes.jpg").size == (400, 501)
    assert Image.open(muestras / "mujer-40-despues.jpg").size == (928, 1152)


# ------------------------------------------------------------------ the control


def test_the_control_is_a_real_range_input():
    """A div with pointer handlers throws away the keyboard, the drag, the touch target
    and the slider semantics, and then rebuilds them badly."""
    mark = hero_html()
    assert 'type="range"' in mark, "the slider is not an <input type=range>"
    assert 'min="0"' in mark and 'max="100"' in mark, "the range is not 0-100"
    assert 'aria-label="Comparar antes y despu' in mark, "no aria-label on the control"


def test_the_control_is_invisible_but_still_focusable():
    """opacity:0, not display:none and not visibility:hidden - either of those would take
    it out of the tab order and out of the accessibility tree."""
    body = rule(".sf-ba-range")
    assert "opacity: 0" in body
    assert "display: none" not in body and "visibility: hidden" not in body


def test_the_focus_ring_is_drawn_on_the_handle():
    """The element holding focus is invisible, so without this the control is
    keyboard-operable and gives no sign of it."""
    assert ".sf-ba-range:focus-visible ~ .sf-ba-handle" in css(), "no focus ring rule"
    assert "outline" in rule(".sf-ba-range:focus-visible ~ .sf-ba-handle")


def test_the_before_image_is_clipped_exactly_as_u3_specifies():
    assert "clip-path: inset(0 calc(100% - var(--p)) 0 0)" in rule(".sf-ba-antes")


def test_the_divider_and_the_handle_are_the_specified_sizes():
    divider = rule(".sf-ba-divider")
    assert "width: 2px" in divider, "the divider is not 2px"
    handle = rule(".sf-ba-handle")
    assert "width: 44px" in handle and "height: 44px" in handle, "the handle is not 44px"
    assert "border-radius: 50%" in handle, "the handle is not round"


def test_the_frame_is_square_on_a_phone_and_capped_at_42svh():
    body = rule(".sf-ba")
    assert "aspect-ratio: 1 / 1" in body, "the phone frame is not square"
    assert "max-height: 42svh" in body, "the 42svh cap is missing"


def media_blocks(condition: str) -> list[str]:
    """Every block for one media condition, matched by counting braces.

    A non-greedy regex stops at the first `}` inside the query, which is the end of its
    first nested rule - so it found U1's header block and reported the slider missing.
    """
    text, blocks = css(), []
    for match in re.finditer(re.escape(f"@media ({condition})") + r"\s*\{", text):
        depth, i = 1, match.end()
        while depth and i < len(text):
            depth += (text[i] == "{") - (text[i] == "}")
            i += 1
        blocks.append(text[match.end() : i - 1])
    return blocks


def test_the_frame_is_four_by_five_from_900px():
    """Asserted inside the 900px query, not merely present in the file: a `4 / 5` sitting
    in the base rule would satisfy a substring search and break the phone."""
    blocks = media_blocks("min-width: 900px")
    assert blocks, "no 900px breakpoint"
    slider = [b for b in blocks if ".sf-ba {" in b]
    assert slider, "the slider has no 900px rule"
    assert "aspect-ratio: 4 / 5" in slider[0], "the desktop frame is not 4:5"


def test_nothing_in_the_slider_animates():
    """U3 asks for no animation on load and for nothing at all under reduced motion. The
    way to satisfy both is to have none to suppress."""
    for selector in (".sf-ba", ".sf-ba-antes", ".sf-ba-divider", ".sf-ba-handle"):
        body = rule(selector)
        assert "transition" not in body, f"{selector} has a transition"
        assert "animation" not in body, f"{selector} has an animation"


def test_both_images_are_eager_and_the_result_has_priority():
    """Both are in the first paint: the "después" is the LCP candidate and the "antes" is
    revealed by the very first drag, so lazy-loading it shows a hole where the comparison
    is."""
    mark = hero_html()
    images = re.findall(r"<img[^>]*>", mark)
    assert len(images) == 2, f"expected two images in the hero, found {len(images)}"
    for img in images:
        assert 'loading="eager"' in img, f"not eager: {img[:90]}"
        assert "width=" in img and "height=" in img, f"no intrinsic size: {img[:90]}"
    priority = [i for i in images if "fetchpriority" in i.lower()]
    assert len(priority) == 1, "exactly one image should carry fetchPriority"
    assert "despues" in priority[0], "priority is on the 'antes', not the result"


def test_the_labels_are_on_both_sides():
    mark = hero_html()
    assert "sf-ba-tag-antes" in mark and "sf-ba-tag-despues" in mark
    assert ">Antes<" in mark and "Despu" in mark


def test_the_disclosure_caption_is_under_the_frame_word_for_word():
    """AI Act Art. 50 and Directive 2005/29/EC. U3 says it stays word for word, and it has
    to be under the frame rather than somewhere on the page."""
    mark = hero_html()
    assert CAPTION in mark, "the fictional-person disclosure is not in the hero figure"
    assert mark.index("</div>") < mark.index(CAPTION), "the caption is not under the frame"


def test_view_proof_still_fires_from_the_same_observer():
    """U3: "Existing event view_proof keeps firing exactly where it fires today." Today is
    once, at a 0.5 threshold, disconnected after the first hit."""
    src = strip_comments(COMPONENT.read_text(encoding="utf-8"), language="tsx")
    assert "EVENTS.viewProof" in src, "view_proof no longer fires from the hero"
    assert "threshold: 0.5" in src, "the observer threshold changed"
    assert src.count("io.disconnect()") >= 2, "the observer is not disconnected"


def test_no_animation_library_was_added():
    """The landing budget is 400 KB and U3 says no library."""
    package = (ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    for banned in ("framer-motion", "gsap", "motion", "react-compare"):
        assert f'"{banned}"' not in package, f"{banned} was added"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
