"""Cut the hero's before/after pair so the two faces are the same face.

Unit U3. F5, measured: the "después" is 928x1152 with the face filling the frame and the
"antes" is 400x501 with a smaller one. Put those two in a comparison slider and the halves
of the face do not meet at the divider - which is the one thing a before/after slider
exists to do.

    .venv\\Scripts\\python.exe scripts\\align_muestras.py

It reads the two files already in the repository and writes cropped copies beside them.
It generates nothing and calls no model: U3 says produce the crops with Pillow from the
existing sources, and the people in the "antes" images are generated fictions whose
likeness must not drift.

## Where the numbers came from

Pupil centres, read off a pixel grid drawn over each source image at native scale and
checked against the rendered result (docs/ui/2026-09-19/reference/). Eyes are the right
landmark because they are the only feature on a face with two unambiguous points, so the
distance between them measures scale without anyone deciding where a cheek ends.

Two quantities have to match once both crops are rendered into the same box:

  interpupillary distance / crop width   - the face is the same size
  (eye line - crop top) / crop height    - the eyes are on the same line

The "antes" has the relatively larger face (0.30 against 0.205), so it is the constraint:
it is taken at full width and everything else is derived from its ratio. Achieved 0.05%
on face width, against U3's 4% allowance, and 0.03% of height on the eye line.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MUESTRAS = ROOT / "frontend" / "public" / "muestras"

# 4:5, which is the frame this pair is rendered in from 900px up. On a phone the frame is
# 1:1 and CSS covers it, so the crop only has to be no narrower than the tallest use.
ASPECT = 0.8

# Only the hero pair. The other two muestras are shown as even side-by-side pairs in "Más
# muestras", where nothing has to align, and giving them crops nothing reads would be an
# abstraction for no caller.
PAIRS = {
    "mujer-40": {
        "antes": ((150, 205), (270, 203)),
        "despues": ((390, 435), (580, 430)),
    }
}

# Both outputs at one pixel size so the slider's clip-path divides two identical grids.
# 640 wide upscales the "antes" 1.6x from a 400px crop, which adds no detail - it is a
# phone selfie and reads as one - and avoids throwing away the "después".
OUT_W = 640
OUT_H = round(OUT_W / ASPECT)
SUFFIX = "-hero"


def landmarks(eyes: tuple) -> tuple[float, float, float]:
    (x1, y1), (x2, y2) = eyes
    return abs(x2 - x1), (x1 + x2) / 2, (y1 + y2) / 2


def crop_boxes(pair: dict, antes: Image.Image, despues: Image.Image) -> dict:
    """The two rectangles, derived from the pair's own landmarks."""
    ipd_a, cx_a, cy_a = landmarks(pair["antes"])
    ipd_d, cx_d, cy_d = landmarks(pair["despues"])

    width_a = antes.width
    ratio = ipd_a / width_a
    height_a = round(width_a / ASPECT)
    top_a = max(0, min(round(cy_a - 0.408 * height_a), antes.height - height_a))
    eye_fraction = (cy_a - top_a) / height_a

    width_d = round(ipd_d / ratio)
    height_d = round(width_d / ASPECT)
    left_d = round(cx_d - width_d / 2)
    top_d = round(cy_d - eye_fraction * height_d)
    return {
        "antes": (0, top_a, width_a, top_a + height_a, ipd_a, cy_a),
        "despues": (left_d, top_d, left_d + width_d, top_d + height_d, ipd_d, cy_d),
    }


def check(box: tuple, image: Image.Image, name: str) -> tuple[float, float]:
    left, top, right, bottom, ipd, eye_y = box
    if left < 0 or top < 0 or right > image.width or bottom > image.height:
        raise SystemExit(f"{name}: crop {box[:4]} leaves the {image.size} source")
    return ipd / (right - left), (eye_y - top) / (bottom - top)


def write(image: Image.Image, box: tuple, stem: str) -> list[Path]:
    cut = image.crop(box[:4]).resize((OUT_W, OUT_H), Image.LANCZOS)
    written = []
    for suffix, kwargs in ((".jpg", {"quality": 86}), (".webp", {"quality": 82})):
        target = MUESTRAS / f"{stem}{SUFFIX}{suffix}"
        cut.save(target, **kwargs)
        written.append(target)
    return written


def main() -> int:
    for key, pair in PAIRS.items():
        antes = Image.open(MUESTRAS / f"{key}-antes.jpg").convert("RGB")
        despues = Image.open(MUESTRAS / f"{key}-despues.jpg").convert("RGB")
        boxes = crop_boxes(pair, antes, despues)
        ratios, fractions = {}, {}
        for side, image in (("antes", antes), ("despues", despues)):
            ratios[side], fractions[side] = check(boxes[side], image, f"{key}-{side}")
            for path in write(image, boxes[side], f"{key}-{side}"):
                print(f"  wrote {path.relative_to(ROOT)}  {OUT_W}x{OUT_H}")
        width_gap = abs(ratios["antes"] - ratios["despues"]) / ratios["antes"] * 100
        eye_gap = abs(fractions["antes"] - fractions["despues"]) * 100
        print(f"  {key}: face width differs {width_gap:.2f}% (U3 allows 4), ")
        print(f"  {key}: eye line differs {eye_gap:.2f}% of the frame height")
        if width_gap > 4:
            raise SystemExit(f"{key}: face widths differ by {width_gap:.2f}%, over U3's 4%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
