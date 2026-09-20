"""The buttons the money runs through must be thumb-sized.

Found by the design critic at round 3 (docs/design-review/2026-09-17-2200) with
getBoundingClientRect on the live page, not by reading CSS: the primary call to
action measured 36px tall. Every guideline puts the floor at 44px, and this is a
phone product whose entire funnel — "Ver una prueba gratis" and "Comprar las cuatro
fotos" — is that one button at size="lg".

It came from shadcn's defaults (lg was h-9) and survived every test, the design audit
and three rounds of screenshots, because 36px looks perfectly fine. It is only wrong
under a thumb.

Tailwind height classes are in 0.25rem steps: h-11 is 44px, h-9 is 36px. Parsing class
strings is crude, and it is still the only place this can be caught before a person
with average hands misses the button.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_scan import Scanner, strip_comments  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BUTTON = ROOT / "frontend" / "src" / "components" / "ui" / "button.tsx"
MIN_TAP_PX = 44
REM_STEP_PX = 4  # Tailwind h-<n> == n * 0.25rem == n * 4px at the default root size


def size_variants() -> dict[str, str]:
    """The `size: { ... }` block of the cva() call."""
    text = BUTTON.read_text(encoding="utf-8")
    block = re.search(r"\n\s*size:\s*\{(.*?)\n\s*\},", text, re.S)
    assert block, f"no size variants found in {BUTTON}"
    return dict(re.findall(r'(\w+):\s*\n?\s*"([^"]*)"', block.group(1)))


def height_px(classes: str) -> int | None:
    m = re.search(r"\bh-(\d+)\b", classes)
    return int(m.group(1)) * REM_STEP_PX if m else None


def test_the_large_button_clears_the_tap_target_floor():
    """size="lg" is what every call to action on the site uses."""
    lg = size_variants().get("lg")
    assert lg, "no lg size variant"
    px = height_px(lg)
    assert px is not None, f"lg variant declares no height: {lg!r}"
    assert px >= MIN_TAP_PX, (
        f"the primary call to action is {px}px tall, under the {MIN_TAP_PX}px tap floor"
    )


def test_every_call_to_action_actually_asks_for_that_size():
    """Held-out check: fixing the lg variant achieves nothing if the buttons on the
    money path use the default size instead. Both CTAs are in upload-form.tsx."""
    form = (ROOT / "frontend" / "src" / "components" / "upload-form.tsx").read_text(
        encoding="utf-8"
    )
    buttons = re.findall(r"<Button\b([^>]*)>", form, re.S)
    assert len(buttons) >= 2, f"expected the preview and checkout buttons, found {len(buttons)}"
    for props in buttons:
        assert 'size="lg"' in props, f"a call to action is not size=lg: {props.strip()[:80]}"


# `<Button ...>` but never `<ButtonPrimitive ...>`. Written with an explicit character
# class rather than a word boundary: twice in one day a `\b` in a pattern reached the
# file as a literal backspace byte, which matches nothing, passes everything, and is
# invisible in a diff.
#
# Both are Scanners now rather than bare regexes. Scanner refuses a pattern holding a
# control character at construction time, and tests/test_source_scanners.py runs the
# catches/ignores examples below on every test run and points both at the offender
# fixture. A pattern that has rotted into matching nothing fails there, loudly, instead
# of passing quietly here.
BUTTON_TAG = Scanner(
    name="button-without-size",
    pattern=r"<Button([\s/>][^>]*?)>",
    catches=('<Button type="submit">', '<Button size="lg" onClick={x}>'),
    ignores=("<Button>", '<ButtonPrimitive data-slot="button">'),
)
VARIANTS = Scanner(
    name="buttonvariants-call",
    pattern=r"buttonVariants\(([^)]*)\)",
    catches=("className={buttonVariants()}", 'buttonVariants({ size: "lg" })'),
    ignores=("buttonVariant(x)", "import { buttonVariants } from '@/x'"),
)


def tsx() -> dict[str, str]:
    root = ROOT / "frontend" / "src"
    return {
        path.relative_to(root).as_posix(): strip_comments(
            path.read_text(encoding="utf-8"), language="tsx"
        )
        for path in sorted(root.rglob("*.tsx"))
    }


def test_no_button_anywhere_takes_the_default_size():
    """The test above only reads upload-form.tsx, and the design critic found 32px
    controls in two files it never opens.

    `<Button type="submit">` on /recuperar/ — the only control a customer who has lost
    the link they PAID for can press — took shadcn's default size. So did the
    "Descargar" and "Volver a intentarlo" links on /g/, through buttonVariants(). Same
    bug class as the 36px CTA that this file was written to prevent, arriving through a
    door the file did not know existed. A regression test scoped to one filename only
    guards that filename."""
    offenders = []
    for name, text in tsx().items():
        if name == "components/ui/button.tsx":
            continue
        for props in BUTTON_TAG.findall(text):
            if 'size="lg"' not in props:
                offenders.append(f"{name}: <Button {props.strip()[:60]}>")
    assert not offenders, f"controls at shadcn's default height: {offenders}"


def test_no_link_styled_as_a_button_takes_the_default_size():
    """buttonVariants() with no argument is the same 32px, on an <a> where no <Button>
    grep will ever find it. It is how the download link on /g/ got there — the control a
    buyer presses to collect the four photographs they paid 19,99 EUR for."""
    offenders = []
    for name, text in tsx().items():
        if name == "components/ui/button.tsx":
            continue
        for call in VARIANTS.findall(text):
            if 'size: "lg"' not in call:
                offenders.append(f"{name}: buttonVariants({call.strip()[:50]})")
    assert not offenders, f"links styled as buttons at the default height: {offenders}"


def test_the_one_text_field_in_the_product_is_thumb_sized():
    """It is the email box on /recuperar/, and the person typing into it has already
    paid and lost their link. Measured live at 342x32 before this: shadcn's h-8."""
    text = (ROOT / "frontend" / "src" / "components" / "ui" / "input.tsx").read_text(
        encoding="utf-8"
    )
    base = re.search(r'cn\(\s*"([^"]+)"', text)
    assert base, "no base class string in input.tsx"
    px = height_px(base.group(1))
    assert px is not None, "the input declares no height"
    assert px >= MIN_TAP_PX, f"the only text field in the product is {px}px tall"


def test_an_inline_link_inside_a_sentence_is_not_counted():
    """Recorded so the next measurement does not chase it.

    `hola@studioface.app` renders 136x16 inside a paragraph, and it stays that way.
    WCAG 2.2 SC 2.5.8 (Level AA, 24x24 CSS px) lists five exceptions and the third is
    Inline: "The target is in a sentence or its size is otherwise constrained by the
    line-height of non-target text" (verified 18 Sep, docs/verified.md). Padding a link
    inside a sentence to 44px breaks the sentence, which is why the exception exists."""
    for page in ("app/g/page.tsx", "app/recuperar/page.tsx"):
        text = tsx()[page]
        assert "mailto:" in text, f"{page} lost its way to reach a human"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
