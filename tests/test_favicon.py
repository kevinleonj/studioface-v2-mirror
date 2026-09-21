"""The StudioFace favicon/app-icon set, replacing the Next.js default template icons.

Built by scripts/make_favicon.py (the letter S in Newsreader, on the paper/ink pair from
docs/DESIGN.md) and committed to the repo like the share image (tests/test_share_image.py)
— a static export with images.unoptimized has no request-time renderer, so the icon bytes
ship as-is. Not wired into scripts/ci.py, same as scripts/make_share_image.py: it is a
manual generation step, re-run only when the mark itself changes, and its network read of
the Newsreader font (docs/verified.md N2) must not make the gate flaky.

scripts/check.py's own `favicon` check is the outside-in half of this, against production:
it asserts the served /favicon.ico is not the Next.js default md5 and that the five
template SVGs stop answering 200. This file is the inside half: the generation is
deterministic and the committed files are the right shape before any deploy.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image, ImageFont  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from make_favicon import (  # noqa: E402
    APPLE_ICON,
    APPLE_SIZE,
    BACKGROUND,
    FAVICON_ICO,
    ICON_SVG,
    INK,
    SIZES,
    mark,
)

APP = ROOT / "frontend" / "src" / "app"
PUBLIC = ROOT / "frontend" / "public"
TEMPLATE_LEFTOVERS = ("next.svg", "vercel.svg", "globe.svg", "window.svg", "file.svg")
NEXT_DEFAULT_FAVICON_MD5 = "c30c7d42707a47a3f4591831641e50dc"


# ---------------------------------------------------------------- committed files


def test_the_favicon_lives_at_the_nextjs_convention_path():
    """favicon.ico can only be set at the root of app/ (docs/verified.md N1)."""
    assert FAVICON_ICO == APP / "favicon.ico"
    assert FAVICON_ICO.is_file()


def test_the_favicon_is_not_the_nextjs_default_triangle():
    digest = hashlib.md5(FAVICON_ICO.read_bytes()).hexdigest()  # noqa: S324 - identity
    assert digest != NEXT_DEFAULT_FAVICON_MD5


def test_the_favicon_ico_carries_every_required_size():
    with Image.open(FAVICON_ICO) as im:
        assert im.info["sizes"] == {(s, s) for s in SIZES}


def test_the_icon_svg_exists_with_the_project_tokens():
    assert ICON_SVG == APP / "icon.svg"
    svg = ICON_SVG.read_text(encoding="utf-8")
    assert BACKGROUND in svg
    assert INK in svg
    assert "Newsreader" in svg
    assert ">S<" in svg


def test_the_apple_icon_is_a_square_png():
    assert APPLE_ICON == APP / "apple-icon.png"
    with Image.open(APPLE_ICON) as im:
        assert im.format == "PNG"
        assert im.size == (APPLE_SIZE, APPLE_SIZE)


# ---------------------------------------------------------------- the five template leftovers


def test_the_five_template_images_are_deleted():
    still_there = [name for name in TEMPLATE_LEFTOVERS if (PUBLIC / name).is_file()]
    assert not still_there, f"template leftovers still committed: {still_there}"


def test_demo_server_no_longer_points_at_a_deleted_placeholder():
    """scripts/demo_server.py served /next.svg etc. as gallery-thumbnail stand-ins.
    Held-out: it must not just avoid the literal five names, it must point at files
    that actually exist under frontend/public, or the demo gallery renders broken
    images again with different filenames."""
    import demo_server

    for placeholder in demo_server.PLACEHOLDERS:
        name = placeholder.lstrip("/")
        assert name not in TEMPLATE_LEFTOVERS, f"still references deleted {placeholder}"
        assert (PUBLIC / name).is_file(), f"{placeholder} does not exist under frontend/public"


# ---------------------------------------------------------------- the mark itself (no network)


def _test_font(size: int) -> ImageFont.ImageFont:
    """A scalable built-in font, so this file never needs the Newsreader network read
    the real generation does (fetch_newsreader in scripts/make_favicon.py)."""
    return ImageFont.load_default(size=size)


def test_mark_is_square_and_rgb():
    im = mark(64, _test_font(40))
    assert im.size == (64, 64)
    assert im.mode == "RGB"


def test_mark_paints_the_background_in_the_corner():
    """Outside the circle, held out from the border/letter checks below."""
    im = mark(64, _test_font(40))
    assert im.getpixel((1, 1)) == Image.new("RGB", (1, 1), BACKGROUND).getpixel((0, 0))


def test_mark_paints_ink_somewhere_for_the_border_and_the_letter():
    im = mark(64, _test_font(40))
    ink_rgb = Image.new("RGB", (1, 1), INK).getpixel((0, 0))
    pixels = im.get_flattened_data()
    assert ink_rgb in pixels, "no ink-coloured pixel found (border and letter both missing)"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
