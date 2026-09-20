"""Upload normalisation: HEIC decode, EXIF transpose, long-side clamp, JPEG out.

The HEIC fixtures here are REAL: pillow-heif on this machine encodes HEIF, so
`heic_bytes()` produces a genuine container (ftypheic magic), not a stub header.
"""

import io
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.images import LONG_SIDE, normalise, normalise_all  # noqa: E402


def jpeg_bytes(size=(800, 600), colour=(180, 120, 90), exif=None, fmt="JPEG") -> bytes:
    buf = io.BytesIO()
    im = Image.new("RGB", size, colour)
    im.save(buf, fmt, **({"exif": exif} if exif else {}))
    return buf.getvalue()


def heic_bytes(size=(640, 480)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (30, 90, 200)).save(buf, "HEIF")
    return buf.getvalue()


def opened(data: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(data))
    im.load()
    return im


# ---------------------------------------------------------------- cold start


def test_heic_is_decoded_to_jpeg():
    """Cold start: the HEIF opener must be registered at import, not by the caller."""
    raw = heic_bytes()
    assert raw[4:12] == b"ftypheic"  # the fixture really is HEIC
    out = opened(normalise(raw))
    assert out.format == "JPEG"
    assert out.size == (640, 480)


# ---------------------------------------------------------------- one


def test_jpeg_passes_through_as_jpeg_without_upscaling():
    out = opened(normalise(jpeg_bytes((400, 300))))
    assert out.format == "JPEG"
    assert out.size == (400, 300)  # never enlarge a small selfie


def test_png_becomes_jpeg():
    assert opened(normalise(jpeg_bytes((300, 300), fmt="PNG"))).format == "JPEG"


# ---------------------------------------------------------------- transforms


def test_long_side_is_clamped_and_aspect_preserved():
    out = opened(normalise(jpeg_bytes((3000, 2000))))
    assert max(out.size) == LONG_SIDE
    assert out.size == (LONG_SIDE, 1024)  # 3:2 kept


def test_portrait_clamps_the_height_not_the_width():
    out = opened(normalise(jpeg_bytes((2000, 3000))))
    assert out.size == (1024, LONG_SIDE)


def test_exif_orientation_is_applied_and_then_stripped():
    """A phone portrait shot is 'landscape + orientation 6'. fal sees pixels, not EXIF."""
    exif = Image.Exif()
    exif[274] = 6  # Orientation: rotate 90 CW
    out = opened(normalise(jpeg_bytes((800, 600), exif=exif.tobytes())))
    assert out.size == (600, 800)  # physically rotated
    assert out.getexif().get(274) in (None, 1)  # tag not carried forward


# ---------------------------------------------------------------- many / empty


def test_normalise_all_empty_list():
    assert normalise_all([]) == []


def test_normalise_all_mixed_formats_keeps_order_and_count():
    files = [jpeg_bytes((100, 100)), heic_bytes((200, 150)), jpeg_bytes((120, 90), fmt="PNG")]
    out = normalise_all(files)
    assert len(out) == 3
    assert [opened(b).size for b in out] == [(100, 100), (200, 150), (120, 90)]
    assert all(opened(b).format == "JPEG" for b in out)


# ---------------------------------------------------------------- failure


def test_garbage_bytes_raise_value_error_not_a_pillow_error():
    with pytest.raises(ValueError, match="undecodable_image"):
        normalise(b"this is not an image" * 10)


def test_empty_bytes_raise_value_error():
    with pytest.raises(ValueError, match="undecodable_image"):
        normalise(b"")


# ---------------------------------------------------------------- held-out check


def test_transparent_png_does_not_crash_jpeg_encoding():
    """Not asked for: JPEG has no alpha channel, so a naive save() raises OSError.
    A PNG with transparency is the single likeliest upload to break this path."""
    buf = io.BytesIO()
    Image.new("RGBA", (500, 500), (10, 200, 10, 0)).save(buf, "PNG")
    out = opened(normalise(buf.getvalue()))
    assert out.format == "JPEG"
    assert out.mode == "RGB"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
