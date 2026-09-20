"""The Open Graph / Twitter share image: one static 1200x630 JPEG under 200 KB.

Unit page-head. Built by scripts/make_share_image.py from the aligned hero pair that
scripts/align_muestras.py already cuts (frontend/public/muestras/mujer-40-*-hero.jpg) —
nothing is generated or called here, same rule as that script: the "antes" person is a
generated fiction and its likeness must not drift.

Committed to the repo like the hero crops themselves, not built at deploy time: this is
a static export with images.unoptimized (next.config.ts), so there is no image server to
regenerate it from, and og:image needs one fixed URL a crawler can fetch once and cache.
"""

import sys
from pathlib import Path

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from make_share_image import OUT, PANEL_H, PANEL_W, build, panel  # noqa: E402

MUESTRAS = ROOT / "frontend" / "public" / "muestras"
MAX_BYTES = 200 * 1024


def test_the_share_image_exists_in_the_export_source():
    assert OUT.is_file(), f"{OUT} is missing — run scripts/make_share_image.py"


def test_the_share_image_is_1200x630():
    with Image.open(OUT) as im:
        assert im.size == (1200, 630)


def test_the_share_image_is_a_jpeg_under_200kb():
    assert OUT.stat().st_size <= MAX_BYTES, f"{OUT} is over {MAX_BYTES} bytes"
    with Image.open(OUT) as im:
        assert im.format == "JPEG"


def test_panel_crops_the_hero_to_the_right_aspect():
    """Held out: a panel that is not PANEL_W x PANEL_H would paste unevenly and the
    two faces would not line up with the frame the way they do in the comparison
    slider (scripts/align_muestras.py)."""
    cropped = panel(MUESTRAS / "mujer-40-antes-hero.jpg")
    assert cropped.size == (PANEL_W, PANEL_H)


def test_build_pastes_both_panels_side_by_side_at_1200x630():
    canvas = build()
    assert canvas.size == (1200, 630)
    assert canvas.mode == "RGB"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
