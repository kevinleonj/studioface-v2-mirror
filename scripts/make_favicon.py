"""Build the StudioFace mark: the favicon, the SVG icon and the Apple touch icon.

Unit 09-favicon. The site was serving the Next.js default triangle favicon and its five
template SVGs (next.svg, vercel.svg, globe.svg, window.svg, file.svg). This replaces
them with one mark — the letter S in Newsreader, ink on paper (docs/DESIGN.md: #f2f1ed
background, #141312 ink) — at the three places Next.js's file-based icon convention
looks (docs/verified.md N1): app/favicon.ico, app/icon.svg, app/apple-icon.png.

    .venv\\Scripts\\python.exe scripts\\make_favicon.py

Same pattern as scripts/make_share_image.py: a manual generation step, not wired into
scripts/ci.py, writing static files that are committed and read back by tests/test_favicon.py.
Unlike that script, this one reads the Newsreader variable font over the network on first
run (there is no static file of it in this repo — the web page loads it through
next/font/google at build time, not from a committed asset) and caches it under
.fonts-cache/ (gitignored) so a second run is offline. docs/verified.md N2 records the
exact upstream file and its OFL 1.1 licence, the same family and licence already declared
for the live site in docs/DESIGN.md.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend" / "src" / "app"
FAVICON_ICO = APP / "favicon.ico"
ICON_SVG = APP / "icon.svg"
APPLE_ICON = APP / "apple-icon.png"

BACKGROUND = "#f2f1ed"
INK = "#141312"
SIZES = (16, 32, 48, 256)
APPLE_SIZE = 180
SUPERSAMPLE = 4  # rendered this many times larger, then LANCZOS-downscaled for antialiasing

# A public, licence-fixed asset address (SIL OFL 1.1, docs/verified.md N2), not a secret
# or a per-environment endpoint — same reasoning as BASE in scripts/check.py.
FONT_URL = (
    "https://raw.githubusercontent.com/google/fonts/main/ofl/newsreader/"
    "Newsreader%5Bopsz%2Cwght%5D.ttf"
)
FONT_CACHE = ROOT / ".fonts-cache" / "Newsreader-Variable.ttf"
FONT_WEIGHT = 700  # bold: axis range is 200-800 (docs/verified.md N2)

ICON_SVG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <circle cx="32" cy="32" r="28" fill="{background}" stroke="{ink}" stroke-width="3"/>
  <text x="32" y="33" text-anchor="middle" dominant-baseline="central"
        font-family="Newsreader, Georgia, serif" font-weight="700" font-size="34"
        fill="{ink}">S</text>
</svg>
"""


def fetch_newsreader() -> Path:
    """Download the Newsreader variable font once and cache it locally."""
    if not FONT_CACHE.is_file():
        FONT_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(FONT_URL, timeout=30) as response:
            FONT_CACHE.write_bytes(response.read())
    return FONT_CACHE


def newsreader(pixel_size: int) -> ImageFont.FreeTypeFont:
    """Newsreader at `pixel_size`, set to the bold weight, optical size following size."""
    font = ImageFont.truetype(str(fetch_newsreader()), pixel_size)
    optical_size = max(6, min(72, round(pixel_size / SUPERSAMPLE)))
    font.set_variation_by_axes([FONT_WEIGHT, optical_size])
    return font


def mark(size: int, font: ImageFont.ImageFont, scale: int = SUPERSAMPLE) -> Image.Image:
    """The StudioFace mark: an ink-bordered paper disc with a centred 'S', rendered at
    `scale`x and downsampled so a 16px favicon is antialiased rather than blocky."""
    big = size * scale
    canvas = Image.new("RGB", (big, big), BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    border = max(1, round(big * 0.045))
    inset = border / 2
    draw.ellipse((inset, inset, big - inset, big - inset), outline=INK, width=border)
    bbox = draw.textbbox((0, 0), "S", font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    origin = ((big - text_w) / 2 - bbox[0], (big - text_h) / 2 - bbox[1])
    draw.text(origin, "S", font=font, fill=INK)
    return canvas.resize((size, size), Image.LANCZOS)


def build_favicon_ico() -> None:
    base_size = 256
    font = newsreader(round(base_size * SUPERSAMPLE * 0.62))
    # RGBA, not RGB: Next.js's build-time ICO decoder (Turbopack) rejects a 256px frame
    # whose embedded PNG has no alpha channel ("The PNG is not in RGBA format!"), even
    # though the mark itself is fully opaque.
    base = mark(base_size, font).convert("RGBA")
    FAVICON_ICO.parent.mkdir(parents=True, exist_ok=True)
    base.save(FAVICON_ICO, sizes=[(s, s) for s in SIZES])


def build_apple_icon() -> None:
    font = newsreader(round(APPLE_SIZE * SUPERSAMPLE * 0.62))
    mark(APPLE_SIZE, font).save(APPLE_ICON, format="PNG")


def build_icon_svg() -> None:
    ICON_SVG.write_text(ICON_SVG_TEMPLATE.format(background=BACKGROUND, ink=INK), encoding="utf-8")


def main() -> int:
    build_favicon_ico()
    build_icon_svg()
    build_apple_icon()
    for path in (FAVICON_ICO, ICON_SVG, APPLE_ICON):
        print(f"wrote {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
