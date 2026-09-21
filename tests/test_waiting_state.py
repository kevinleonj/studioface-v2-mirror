"""The wait, task 12: an empty box replaced by the visitor's own face.

Before this task the upload form's `Generating` frame and the gallery's four
"working" frames were empty boxes — a blank rectangle for as long as the free preview
or the paid order takes. `.claude/skills/studioface-ui` and CLAUDE.md's brief both name
the honest replacement: the visitor's own first chosen photo, dimmed and blurred, with
a slow pulse — one class, `sf-wait`, real CSS in the global stylesheet (never a Tailwind
arbitrary value, which this project has already lost to silent compile-away once, see
M14 in globals.css) so `scripts/check.py waiting_state` can find it in the stylesheet a
GET of the home page actually links.

`sf-wait` is deliberately the one animation on this site allowed to loop — CLAUDE.md's
brief for this task says so in as many words ("A slow pulse is allowed; an unbounded
spinner is not"), as the honest middle ground between an empty box and the fake
`<Progress value={45}>` bars this project has already deleted twice
(tests/test_the_wait.py). Everything else about the motion budget still applies: opacity
only, the animation lives inside `@media (prefers-reduced-motion: no-preference)` and
nowhere else, so under `reduce` it does not run at all.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_scan import strip_comments  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
UPLOAD = ROOT / "frontend" / "src" / "components" / "upload-form.tsx"
GALLERY = ROOT / "frontend" / "src" / "app" / "g" / "page.tsx"
CSS = ROOT / "frontend" / "src" / "app" / "globals.css"


def css() -> str:
    return CSS.read_text(encoding="utf-8")


def upload_code() -> str:
    return strip_comments(UPLOAD.read_text(encoding="utf-8"), language="tsx")


def gallery_code() -> str:
    return strip_comments(GALLERY.read_text(encoding="utf-8"), language="tsx")


def generating_body() -> str:
    code = upload_code()
    start = code.index("function Generating(")
    end = code.index("function labelFor(", start)
    return code[start:end]


def waiting_body() -> str:
    code = gallery_code()
    start = code.index("function Waiting()")
    end = code.index("function Ending(", start)
    return code[start:end]


def test_sf_wait_is_real_css_in_the_global_stylesheet():
    """Not a Tailwind arbitrary value: check.py greps the compiled stylesheet linked
    from the home page, which is exactly what an arbitrary class never survives into
    (Tailwind only emits utilities it sees used, and even then some are tree-shaken
    unpredictably across builds — the reason M14 already banned this pattern once)."""
    assert ".sf-wait" in css(), "sf-wait is not a real rule in globals.css"


def test_sf_wait_animation_lives_only_inside_the_no_preference_guard():
    no_pref = re.search(
        r"@media \(prefers-reduced-motion: no-preference\) \{(.*?)\n\}\n", css(), re.S
    )
    assert no_pref, "no no-preference block at all"
    inside = no_pref.group(1)
    assert re.search(r"\.sf-wait\s*\{[^}]*animation\s*:", inside), (
        "sf-wait has no animation declared inside the no-preference query — without "
        "one there, prefers-reduced-motion: reduce cannot be the reason it stops"
    )
    outside = css().replace(no_pref.group(0), "")
    assert not re.search(r"\.sf-wait\s*\{[^}]*animation\s*:", outside), (
        "sf-wait's animation is declared a second time outside the guard, so reduce "
        "would not actually stop it"
    )


def test_sf_wait_keyframes_only_touch_opacity_or_transform():
    match = re.search(r"@keyframes sf-wait-pulse\s*\{(.*?)\n\}", css(), re.S)
    assert match, "no @keyframes sf-wait-pulse"
    props = re.findall(r"^\s*([a-z-]+)\s*:", match.group(1), re.M)
    assert props, "the keyframes declare nothing"
    assert all(p in ("opacity", "transform") for p in props), props


def test_the_upload_wait_shows_the_first_chosen_photo():
    body = generating_body()
    assert "sf-wait" in body, "the generating frame does not use the sf-wait treatment"
    assert "photoUrl" in body, "the generating frame has no way to receive a photo"


def test_the_upload_wait_is_fed_the_visitors_first_chosen_file():
    """thumbs[0] is the same blob URL already used for the upload-target thumbnails
    (O12) — one source of truth for "what did they choose", not a second decode."""
    code = upload_code()
    assert re.search(r"<Generating[^>]*thumbs\[0\]", code), (
        "Generating is not called with the first chosen photo"
    )


def test_the_upload_wait_keeps_the_timer_and_focus_behaviour():
    body = generating_body()
    assert "setElapsed" in body and "setInterval" in body, "the elapsed-seconds timer is gone"
    assert "status.current?.focus()" in body, "the wait no longer moves focus to itself"
    assert 'role="status"' in body and 'aria-live="polite"' in body, (
        "the wait is no longer announced to a screen reader"
    )


def test_the_gallery_wait_uses_the_same_treatment_on_its_four_frames():
    body = waiting_body()
    assert "sf-wait" in body, "the gallery's four generating frames do not use sf-wait"


def test_the_gallery_loading_state_is_left_alone():
    """The brief asks for the treatment on the frames shown 'while an order is being
    generated' — Waiting(), not the sub-second Loading() shown before the first status
    answer arrives. Asserting Loading() is untouched is the held-out half of the pair:
    a change broad enough to hit both would still pass the assertion above."""
    code = gallery_code()
    start = code.index("function Loading()")
    end = code.index("function Waiting()", start)
    body = code[start:end]
    assert "sf-wait" not in body


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
