"""Every colour that carries text must clear WCAG AA, computed rather than claimed.

Two things prompted this file, and both were numbers somebody asserted.

The design critic measured the error/alert colour at 4.22:1 against the paper
background — a fail — because `--destructive` was still `oklch(0.577 0.245 27.325)`,
the untouched shadcn default. Every other token was repointed at direction B; that one
was missed, so the one message a customer sees when something has gone wrong was the
least readable text on the site, and in a red that belongs to no palette we chose.

And docs/DESIGN.md claimed the accent `#C3352B` was "5.9:1 on paper". Computed here it
is 4.81:1. It passes, so nothing was broken by it, but the number was wrong and I wrote
it. A contrast figure is either calculated or it is decoration.

So the tokens are hex — an oklch() value cannot be checked without a colour-space
conversion nobody will maintain — and the ratios are computed with the WCAG 2.x
formula rather than trusted.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "frontend" / "src" / "app" / "globals.css"

AA_NORMAL = 4.5

# The tokens that end up as text on a background, and which background they sit on.
TEXT_ON_BACKGROUND = ("--foreground", "--muted-foreground", "--primary", "--destructive")


def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4


def luminance(hex_colour: str) -> float:
    """WCAG relative luminance."""
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def tokens(block: str) -> dict[str, str]:
    """The StudioFace token block, which is appended last so it wins over shadcn."""
    text = CSS.read_text(encoding="utf-8")
    start = text.index("StudioFace — direction B")
    section = text[start:]
    body = re.search(rf"{re.escape(block)}\s*\{{(.*?)\}}", section, re.S)
    assert body, f"no {block} block after the StudioFace banner in {CSS.name}"
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", body.group(1)))


# ---------------------------------------------------------------- the formula


def test_the_contrast_helper_agrees_with_known_values():
    """A test of the ruler before the measurements. Black on white is exactly 21:1."""
    assert round(contrast("#000000", "#ffffff"), 2) == 21.0
    assert round(contrast("#ffffff", "#ffffff"), 2) == 1.0


# ---------------------------------------------------------------- the tokens


@pytest.mark.parametrize("block", [":root", ".dark"])
def test_every_text_token_is_a_hex_so_it_can_be_checked(block):
    """oklch() cannot be verified without a colour-space conversion nobody will
    maintain. A token whose contrast cannot be computed is a token nobody is checking —
    which is exactly how --destructive stayed at the shadcn default."""
    found = tokens(block)
    for name in TEXT_ON_BACKGROUND + ("--background",):
        value = found.get(name, "").strip()
        assert value, f"{block} has no {name}"
        assert re.fullmatch(r"#[0-9a-fA-F]{3,8}", value), f"{block} {name} is {value!r}, not a hex"


@pytest.mark.parametrize("block", [":root", ".dark"])
def test_every_text_token_clears_wcag_aa_against_its_background(block):
    found = tokens(block)
    background = found["--background"].strip()
    failures = []
    for name in TEXT_ON_BACKGROUND:
        ratio = contrast(found[name].strip(), background)
        if ratio < AA_NORMAL:
            failures.append(f"{block} {name} {found[name].strip()} on {background} = {ratio:.2f}:1")
    assert not failures, "below WCAG AA " + f"({AA_NORMAL}:1):\n" + "\n".join(failures)


def test_the_error_colour_is_ours_and_not_the_shadcn_default():
    """The specific regression. It was oklch(0.577 0.245 27.325) — an off-brand red at
    4.22:1 — on the one message shown when something has gone wrong."""
    destructive = tokens(":root")["--destructive"].strip().lower()
    assert "oklch" not in destructive
    assert destructive != "#ef4444", "that is a stock red, not this palette"


def test_the_accent_ratio_documented_in_design_md_is_the_real_one():
    """DESIGN.md said 5.9:1. It is 4.81:1. Numbers in a design document are load-bearing
    or they are decoration — this pins the claim to the arithmetic."""
    found = tokens(":root")
    ratio = contrast(found["--primary"].strip(), found["--background"].strip())
    claimed = re.search(r"#C3352B.*?([\d.]+):1", (ROOT / "docs" / "DESIGN.md").read_text("utf-8"))
    assert claimed, "DESIGN.md no longer states a ratio for the accent"
    assert abs(float(claimed.group(1)) - ratio) < 0.1, (
        f"DESIGN.md claims {claimed.group(1)}:1, computed {ratio:.2f}:1"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
