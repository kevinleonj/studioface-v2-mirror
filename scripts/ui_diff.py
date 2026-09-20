"""Compare two snapshot directories and refuse any movement on the locked pages.

B0.4. Section 2 of the 19 September brief locks five pages: they must not change by a
single pixel while the landing page is rebuilt. This is the thing that enforces it.

    .venv\\Scripts\\python.exe scripts\\ui_diff.py ^
        docs/ui/2026-09-19/before docs/ui/2026-09-19/after

Exit 1 if any locked page differs anywhere outside the consent banner.

`--allow-header-shift` is for the one case where a unit deliberately changes site chrome:
unit U1 takes the mobile header from 145px to 56px, and the header is one component on
every page, so every locked page's content moves up 89px without a character of it
changing. The flag crops each capture at its own header height before comparing, forgives
nothing else, and prints what it forgave. It is off by default, because a lock that
quietly relaxes itself is not a lock.

The consent banner is excluded from the ordinary comparison because it is the one element
that legitimately moves between runs - it is dismissed, it re-renders, and unit U4 changes
its height on purpose - and because a difference underneath it is invisible to a visitor
who has already answered it.

Unlocked pages are compared too, but only reported. A change to the landing page is the
entire point of the work; a change to /legal/terminos/ is a disclosure defect.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageChops

# Section 2, verbatim: "/legal/aviso-legal/, /legal/privacidad/, /legal/terminos/, /g/ and
# /recuperar/". The page keys are the ones scripts/ui_snapshot.py writes.
LOCKED = ("legal-aviso", "legal-privacidad", "legal-terminos", "gallery", "recuperar")

# Zero tolerance, and it is not an assumption: two independent runs of ui_snapshot.py
# against the same build were compared before this threshold was chosen, and every locked
# page came back byte-identical. A static export rendered twice by the same browser build
# has no anti-aliasing jitter to forgive.


def banner_box(geometry: dict, key: str, state: str) -> tuple[int, int, int, int] | None:
    """The consent banner's viewport rectangle, as integers, or None if it is not there."""
    entry = geometry.get("pages", {}).get(key, {}).get(state, {})
    rect = entry.get("banner")
    if not rect or not rect.get("visible"):
        return None
    left, top = int(rect["x"]), int(rect["y"])
    return (left, top, left + int(rect["w"]) + 1, top + int(rect["h"]) + 1)


def changed_region(before: Path, after: Path, mask: tuple | None):
    """The bounding box of everything that moved, once the banner is painted out of both.

    `getbbox()` answers exactly and in C. Returns (None, diff) when the two are identical.
    """
    a = Image.open(before).convert("RGB")
    b = Image.open(after).convert("RGB")
    if a.size != b.size:
        raise ValueError(f"size changed: {a.size} -> {b.size}")
    if mask:
        black = Image.new("RGB", (mask[2] - mask[0], mask[3] - mask[1]), (0, 0, 0))
        a.paste(black, mask[:2])
        b.paste(black, mask[:2])
    diff = ImageChops.difference(a, b)
    return diff.getbbox(), diff


def shots(directory: Path) -> dict[str, Path]:
    """Every screenshot, keyed by its file stem, so the two runs can be lined up."""
    return {p.stem: p for p in directory.glob("*.png")}


def header_heights(before: dict, after: dict, key: str, state: str) -> tuple[int, int]:
    """Each run's own header height for one page, or (0, 0) if either is missing."""

    def height(geometry: dict) -> int:
        rect = geometry.get("pages", {}).get(key, {}).get(state, {}).get("header")
        return int(rect["h"]) if rect else 0

    return height(before), height(after)


def shift(box: tuple | None, drop: int, height: int) -> tuple | None:
    """Move a rectangle into the coordinates of an image cropped by `drop` rows."""
    if not box:
        return None
    top, bottom = max(0, box[1] - drop), min(height, box[3] - drop)
    return (box[0], top, box[2], bottom) if bottom > top else None


def union(first: tuple | None, second: tuple | None) -> tuple | None:
    """The smallest rectangle covering both, or whichever one exists."""
    if not first or not second:
        return first or second
    return (
        min(first[0], second[0]),
        min(first[1], second[1]),
        max(first[2], second[2]),
        max(first[3], second[3]),
    )


def paint_out(img: Image.Image, box: tuple | None) -> Image.Image:
    if box:
        img.paste(Image.new("RGB", (box[2] - box[0], box[3] - box[1]), (0, 0, 0)), box[:2])
    return img


def aligned_region(before: Path, after: Path, drop: tuple[int, int], masks: tuple):
    """Compare with each capture's site chrome cropped off, so a header that legitimately
    changed height does not read as every page below it changing too.

    The banner is painted out AFTER each crop, at its own post-crop position. It has to
    be that way round: the banner is `position: fixed`, so it does not move with the
    document, and cropping the two images by different amounts slides it relative to the
    content that did move. Masking in absolute coordinates first was tried and left two
    uncovered bands, each exactly the height of the header change.

    This is the ONLY thing --allow-header-shift forgives. Everything under the header and
    outside the banner is still compared pixel for pixel, and the amount is printed.
    """
    a, b = Image.open(before).convert("RGB"), Image.open(after).convert("RGB")
    a = a.crop((0, drop[0], a.width, a.height))
    b = b.crop((0, drop[1], b.width, b.height))
    # The UNION of the two post-crop banner bands, painted into both images. Masking each
    # image with only its own band leaves the other's band exposed, so the comparison then
    # sees black against content for exactly the height of the header change - which is
    # what the first attempt reported, on every locked page at once.
    band = union(shift(masks[0], drop[0], a.height), shift(masks[1], drop[1], b.height))
    a, b = paint_out(a, band), paint_out(b, band)
    rows = min(a.height, b.height)
    a, b = a.crop((0, 0, a.width, rows)), b.crop((0, 0, b.width, rows))
    if a.size != b.size:
        raise ValueError(f"width changed: {a.size} -> {b.size}")
    diff = ImageChops.difference(a, b)
    return diff.getbbox(), diff


def compare(before_dir: Path, after_dir: Path, allow_header_shift=False):
    before_geo = json.loads((before_dir / "geometry.json").read_text(encoding="utf-8"))
    after_geo = json.loads((after_dir / "geometry.json").read_text(encoding="utf-8"))
    old, new = shots(before_dir), shots(after_dir)
    failures, notes, forgiven = [], [], []
    for stem in sorted(old):
        if stem not in new:
            notes.append(f"missing in after: {stem}")
            continue
        browser, viewport, rest = stem.split("--", 2)
        page = rest.split("--")[0]
        state = "rejected" if "rejected" in rest else "first-visit"
        key = f"{browser}/{viewport}/{page}"
        drop = header_heights(before_geo, after_geo, key, state)
        shifted = allow_header_shift and page in LOCKED and drop[0] != drop[1]
        masks = (banner_box(before_geo, key, state), banner_box(after_geo, key, state))
        try:
            if shifted:
                box, diff = aligned_region(old[stem], new[stem], drop, masks)
            else:
                box, diff = changed_region(old[stem], new[stem], masks[0])
        except ValueError as exc:
            # A page that is not locked is allowed to change size; that is the work.
            (failures if page in LOCKED else notes).append(f"{stem}: {exc}")
            continue
        if shifted:
            forgiven.append(f"{stem}: header {drop[0]} -> {drop[1]}")
        if box is None:
            continue
        line = f"{stem}: changed within {box} (left, top, right, bottom)"
        if page in LOCKED:
            diff.save(after_dir / f"DIFF--{stem}.png")
            failures.append(line + f"  -> DIFF--{stem}.png")
        else:
            notes.append(line)
    return failures, notes, forgiven


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    before_dir, after_dir = Path(sys.argv[1]), Path(sys.argv[2])
    allow = "--allow-header-shift" in sys.argv[3:]
    failures, notes, forgiven = compare(before_dir, after_dir, allow_header_shift=allow)
    for note in notes:
        print(f"  changed  {note}")
    print(f"\n{len(notes)} unlocked page(s) changed, which is allowed.")
    if forgiven:
        print(
            f"\n--allow-header-shift FORGAVE the site chrome on {len(forgiven)} locked frame(s).\n"
            "Everything below the header was still compared pixel for pixel:"
        )
        for line in forgiven[:6]:
            print(f"  {line}")
    if failures:
        print(f"\nLOCKED PAGES MOVED ({len(failures)}):")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"LOCKED PAGES UNCHANGED: {', '.join(LOCKED)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
