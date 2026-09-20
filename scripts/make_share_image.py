"""Build the Open Graph / Twitter share image from the aligned hero pair.

Unit page-head. 1200x630 is Open Graph's documented practical size for a large-image
card. This is a fixed composite of the two crops scripts/align_muestras.py already
makes — nothing is generated or called here, same rule as that script: the "antes"
person is a generated fiction and its likeness must not drift, and a static asset
avoids a request-time image server this static export does not have
(next.config.ts: images.unoptimized).

    .venv\\Scripts\\python.exe scripts\\make_share_image.py

Reads the hero pair, center-crops each to one half of the 1200x630 frame, pastes them
side by side, and writes frontend/public/share.jpg. Quality steps down until the file
is under 200 KB, so a crawler's fetch stays cheap.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MUESTRAS = ROOT / "frontend" / "public" / "muestras"
OUT = ROOT / "frontend" / "public" / "share.jpg"

HERO_KEY = "mujer-40"
W, H = 1200, 630
PANEL_W, PANEL_H = W // 2, H
MAX_BYTES = 200 * 1024
QUALITIES = (85, 80, 75, 70, 65, 60)


def panel(path: Path) -> Image.Image:
    """Center-crop one hero image to the panel's aspect, then resize to fit it."""
    im = Image.open(path).convert("RGB")
    target_ratio = PANEL_W / PANEL_H
    src_ratio = im.width / im.height
    if src_ratio > target_ratio:
        new_w = round(im.height * target_ratio)
        left = (im.width - new_w) // 2
        im = im.crop((left, 0, left + new_w, im.height))
    else:
        new_h = round(im.width / target_ratio)
        top = (im.height - new_h) // 2
        im = im.crop((0, top, im.width, top + new_h))
    return im.resize((PANEL_W, PANEL_H), Image.LANCZOS)


def build() -> Image.Image:
    antes = panel(MUESTRAS / f"{HERO_KEY}-antes-hero.jpg")
    despues = panel(MUESTRAS / f"{HERO_KEY}-despues-hero.jpg")
    canvas = Image.new("RGB", (W, H))
    canvas.paste(antes, (0, 0))
    canvas.paste(despues, (PANEL_W, 0))
    return canvas


def write_under(canvas: Image.Image, limit: int) -> int:
    size = limit + 1
    for quality in QUALITIES:
        canvas.save(OUT, "JPEG", quality=quality, optimize=True)
        size = OUT.stat().st_size
        if size <= limit:
            return size
    return size


def main() -> int:
    size = write_under(build(), MAX_BYTES)
    print(f"wrote {OUT} ({size} bytes)")
    if size > MAX_BYTES:
        print(f"OVER {MAX_BYTES} bytes", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
