"""B0.4: the gate that stops the locked pages moving.

Section 2 of the 19 September brief locks five pages - the three legal pages, `/g/` and
`/recuperar/` - against any pixel change while the landing page is rebuilt. An obscured or
altered legal page is a disclosure defect, not a layout nit, so the thing that detects it
needs its own tests rather than only the end-to-end demonstration.

That demonstration was run and is the unit's headline evidence: one character changed in
`frontend/src/app/legal/terminos/page.tsx` ("Terminos" -> "Termigos"), rebuilt,
re-snapshotted, and `ui_diff.py` exited 1 naming six locked-page frames with the bounding
box of the heading. Reverted afterwards.

What that demonstration cannot show is the masking rule, because it is the mask that
decides what counts. Get it wrong in the generous direction and every locked page is
compared with a hole in it. These tests pin the mask from both sides.
"""

import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ui_diff import (  # noqa: E402
    LOCKED,
    aligned_region,
    banner_box,
    changed_region,
    shift,
    union,
)

BANNER = {"x": 0, "y": 80, "w": 100, "h": 20, "visible": True}


def write(path: Path, colour=(242, 241, 237), dots=()) -> Path:
    img = Image.new("RGB", (100, 100), colour)
    for x, y in dots:
        img.putpixel((x, y), (195, 53, 43))
    img.save(path)
    return path


def test_two_identical_frames_report_no_change(tmp_path):
    """Empty case. Two runs of the same build must not accuse anybody."""
    a, b = write(tmp_path / "a.png"), write(tmp_path / "b.png")
    box, _ = changed_region(a, b, None)
    assert box is None


def test_one_changed_pixel_is_caught(tmp_path):
    """One pixel. The threshold is zero, so one is enough - and it must be, because the
    difference between a legal page that says 7 days and one that says 1 is small."""
    a = write(tmp_path / "a.png")
    b = write(tmp_path / "b.png", dots=[(50, 10)])
    box, _ = changed_region(a, b, None)
    assert box is not None
    assert box[0] <= 50 < box[2] and box[1] <= 10 < box[3], box


def test_a_change_inside_the_banner_is_ignored(tmp_path):
    """The banner legitimately differs between runs and U4 changes its height on purpose,
    so it is painted out of both frames before they are compared."""
    a = write(tmp_path / "a.png")
    b = write(tmp_path / "b.png", dots=[(10, 85), (90, 95)])
    mask = banner_box({"pages": {"k": {"first-visit": {"banner": BANNER}}}}, "k", "first-visit")
    assert mask == (0, 80, 101, 101), mask
    box, _ = changed_region(a, b, mask)
    assert box is None, f"a change under the banner was reported: {box}"


def test_a_change_just_above_the_banner_is_still_caught(tmp_path):
    """The other side of the same rule, and the one that matters. If the mask is one pixel
    too tall it starts swallowing the page, and nothing would say so."""
    a = write(tmp_path / "a.png")
    b = write(tmp_path / "b.png", dots=[(10, 79)])
    mask = banner_box({"pages": {"k": {"first-visit": {"banner": BANNER}}}}, "k", "first-visit")
    box, _ = changed_region(a, b, mask)
    assert box is not None, "a change above the banner was swallowed by the mask"


def test_no_mask_when_the_banner_is_not_on_screen(tmp_path):
    """After "Rechazar" there is no banner, so nothing may be excluded. A stale mask here
    would blind the comparison on exactly the frames a visitor spends longest looking at."""
    dismissed = {"pages": {"k": {"rejected": {"banner": None}}}}
    assert banner_box(dismissed, "k", "rejected") is None
    invisible = {"pages": {"k": {"rejected": {"banner": dict(BANNER, visible=False)}}}}
    assert banner_box(invisible, "k", "rejected") is None


def test_a_frame_that_changed_size_is_a_failure_not_a_crash(tmp_path):
    """Failure case. Pillow cannot difference two sizes; the run must name the frame
    rather than stop with a traceback halfway through the comparison."""
    a = write(tmp_path / "a.png")
    Image.new("RGB", (100, 120), (242, 241, 237)).save(tmp_path / "b.png")
    with pytest.raises(ValueError, match="size changed"):
        changed_region(a, tmp_path / "b.png", None)


def test_shift_moves_a_rectangle_into_cropped_coordinates():
    """`shift` is what lets a fixed banner be found again after the crop."""
    assert shift((0, 691, 390, 844), 145, 699) == (0, 546, 390, 699)
    assert shift((0, 691, 390, 844), 56, 788) == (0, 635, 390, 788)
    assert shift(None, 56, 788) is None
    assert shift((0, 10, 390, 40), 90, 500) is None, "a band cropped away entirely is gone"


def test_the_banner_band_is_the_union_of_both_positions():
    """The bug this replaced: masking each image with only its OWN band left the other's
    band exposed, so the comparison saw black against content for exactly the height of
    the header change - on every locked page at once."""
    assert union((0, 546, 390, 699), (0, 635, 390, 788)) == (0, 546, 390, 788)
    assert union(None, (0, 635, 390, 788)) == (0, 635, 390, 788)
    assert union(None, None) is None


def test_a_pure_header_shift_is_forgiven_but_a_content_change_is_not(tmp_path):
    """The whole point of --allow-header-shift, from both sides.

    Two pages whose content is identical but sits 20px higher must compare clean; the
    same pair with one pixel of content altered must not.
    """
    tall = Image.new("RGB", (100, 140), (242, 241, 237))
    short = Image.new("RGB", (100, 120), (242, 241, 237))
    for img, top in ((tall, 40), (short, 20)):
        img.putpixel((50, top), (195, 53, 43))
    tall.save(tmp_path / "before.png")
    short.save(tmp_path / "after.png")
    box, _ = aligned_region(tmp_path / "before.png", tmp_path / "after.png", (40, 20), (None, None))
    assert box is None, f"a pure header shift was reported as a change: {box}"

    short.putpixel((70, 60), (195, 53, 43))
    short.save(tmp_path / "after.png")
    box, _ = aligned_region(tmp_path / "before.png", tmp_path / "after.png", (40, 20), (None, None))
    assert box is not None, "a real content change survived the alignment"


def test_the_locked_list_is_exactly_the_five_pages_section_2_names():
    """Held-out check: a comparison that quietly stopped covering /g/ would pass every
    test above. These five keys are what scripts/ui_snapshot.py writes."""
    assert set(LOCKED) == {
        "legal-aviso",
        "legal-privacidad",
        "legal-terminos",
        "gallery",
        "recuperar",
    }


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
