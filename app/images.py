"""Turn whatever a phone uploaded into what fal can actually read.

Three jobs, in this order, before any fal call:
  1. decode HEIC/HEIF (every iPhone photo) — pillow-heif registers the opener at import;
  2. apply the EXIF orientation physically, because fal sees pixels and ignores the tag;
  3. clamp the long side to 1536 px, which is above the 1K output and keeps the upload small.
Output is always baseline JPEG with no EXIF: no alpha, no location metadata, no surprises.
"""

from __future__ import annotations

import io
import logging

import pillow_heif
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)

pillow_heif.register_heif_opener()  # import-time, so callers cannot forget it

LONG_SIDE = 1536
JPEG_QUALITY = 90


def normalise(data: bytes) -> bytes:
    """Decode, transpose, clamp, re-encode as JPEG. Raises ValueError on junk bytes."""
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("undecodable_image") from exc

    image = ImageOps.exif_transpose(image)
    if max(image.size) > LONG_SIDE:
        image.thumbnail((LONG_SIDE, LONG_SIDE), Image.LANCZOS)
    if image.mode != "RGB":
        # JPEG has no alpha channel; flatten RGBA/P/LA onto white instead of raising.
        image = _flatten(image)

    out = io.BytesIO()
    image.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    logger.info(
        "normalised image size=%s bytes_in=%s bytes_out=%s", image.size, len(data), out.tell()
    )
    return out.getvalue()


def _flatten(image: Image.Image) -> Image.Image:
    if image.mode in ("RGBA", "LA", "P"):
        rgba = image.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, (255, 255, 255))
        canvas.paste(rgba, mask=rgba.split()[-1])
        return canvas
    return image.convert("RGB")


def normalise_all(files: list[bytes]) -> list[bytes]:
    """Order-preserving. One bad file fails the whole upload, on purpose."""
    return [normalise(f) for f in files]
