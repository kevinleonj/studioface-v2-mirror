"""Five named moments, and the rules they are held to.

The budget comes from `.claude/skills/studioface-ui`: no animation library, only
`opacity` and `transform`, nothing over 400ms, nothing loops, nothing moves on load
above the fold, and every non-essential animation inside
`@media (prefers-reduced-motion: no-preference)` with a global reduce guard as well.

`prefers-reduced-motion` is Baseline Widely Available, across browsers since **January
2020** — verified 18 Sep 2026 against MDN and recorded in docs/verified.md. The brief
said July 2022; that was wrong and the correction is why the guard needs no fallback.

The 400ms ceiling is a PROJECT DECISION, not a standard. Material Design 2 and 3 are
JS-rendered and could not be fetched, and MDN and web.dev give example values but no
normative recommendation. Stated as ours so nobody cites it as an authority later.

The rule that bites hardest is opacity-and-transform-only, because it fails an animation
that was already shipping: `.sf-focus:focus-visible` drew its ring with a `box-shadow`
keyframe. A focus ring should also not fade in at all — a keyboard user is waiting on
it, and 220ms of drawing is 220ms of not knowing where they are.
"""

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_scan import Scanner, strip_comments  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "frontend" / "src" / "app" / "globals.css"
PACKAGE = ROOT / "frontend" / "package.json"
DESIGN = ROOT / "docs" / "DESIGN.md"
EXPORT = ROOT / "frontend" / "out"

MAX_MS = 400
ALLOWED_PROPERTIES = {"opacity", "transform"}
ANIMATION_LIBRARIES = ("framer-motion", "motion", "gsap", "animejs", "lottie-web", "aos")
# The class every arrival animation is hung on. Nothing carrying one may be in the
# server-rendered landing page, because that is what "nothing moves on load" means.
ARRIVAL = ("sf-arrive", "sf-land")
# Tailwind motion utilities. Everything else in this file reads globals.css, and
# these live in className strings where none of those rules can see them.
TAILWIND_MOTION = Scanner(
    name="tailwind-motion-utility",
    pattern=r"transition-all|transition-colors|animate-[a-z-]+",
    catches=('className="x transition-all y"', 'className="animate-in fade-in"'),
    ignores=('className="transition-transform"', 'className="transition-[opacity]"'),
)
# Fourth time in three days that a check has read its own rationale: test_header grepped
# the comment saying why the header is not sticky, the bootstrap test grepped the comment
# naming core.hooksPath, test_the_wait caught `<Progress value={60}>` inside the note
# recording its deletion, and this one found `transition-all` twice in the comment
# explaining that transition-all was removed. Strip the prose, then read the code.
#
# The stripper itself now lives in tests/source_scan.py, so there is one implementation
# instead of a copy per test file — four copies had already diverged.


def css() -> str:
    return CSS.read_text(encoding="utf-8")


def durations_ms() -> list[tuple[str, float]]:
    """Every duration declared anywhere, in milliseconds, with its source line."""
    out = []
    for line in css().splitlines():
        if not re.search(r"\b(transition|animation)(-duration)?\s*:", line):
            continue
        for value, unit in re.findall(r"(\d*\.?\d+)(ms|s)\b", line):
            out.append((line.strip(), float(value) * (1 if unit == "ms" else 1000)))
    return out


def test_no_animation_or_transition_is_longer_than_the_ceiling():
    """sf-wait is the one named exception: CLAUDE.md's brief for task 12 explicitly
    allows "a slow pulse" as the honest replacement for the fake progress bars this
    project has already deleted twice, and a pulse read as "in progress" needs longer
    than 400ms a cycle. Everything else still obeys the ceiling."""
    over = [(line, ms) for line, ms in durations_ms() if ms > MAX_MS and "sf-wait" not in line]
    assert not over, f"over the {MAX_MS}ms ceiling: {over}"


def test_nothing_animated_is_outside_opacity_and_transform():
    """Anything else is laid out or painted by the compositor's slow path, and on the
    phone this product is used on that is the difference between motion and jank."""
    offenders = []
    for block in re.findall(r"@keyframes\s+[\w-]+\s*\{(.*?)\n\}", css(), re.S):
        for prop in re.findall(r"^\s*([a-z-]+)\s*:", block, re.M):
            if prop not in ALLOWED_PROPERTIES:
                offenders.append(f"@keyframes -> {prop}")
    for value in re.findall(r"transition:\s*([^;]+);", css()):
        first = value.strip().split()[0]
        if first not in ALLOWED_PROPERTIES and first != "none":
            offenders.append(f"transition: {first}")
    assert not offenders, offenders


def test_nothing_loops():
    """sf-wait is the one exception, named in the assertion itself so the exception
    stays narrow: any other line using "infinite" fails this test. "alternate" stays
    banned outright — sf-wait's own keyframes go up and back down inside one cycle, so
    even the one exception does not need it."""
    lines = css().splitlines()
    offenders = [line for line in lines if "infinite" in line and "sf-wait" not in line]
    assert not offenders, offenders
    assert "alternate" not in css()


def test_every_moment_is_inside_a_no_preference_query():
    """The guard is not optional and not a nice-to-have: vestibular disorders are the
    reason the media query exists."""
    block = re.search(
        r"@media \(prefers-reduced-motion: no-preference\) \{(.*?)\n\}\n", css(), re.S
    )
    assert block, "no no-preference block at all"
    inside = block.group(1)
    declared = re.findall(r"(?:transition|animation)\s*:", css())
    covered = re.findall(r"(?:transition|animation)\s*:", inside)
    assert len(covered) == len(declared), (
        f"{len(declared) - len(covered)} animation declarations outside the guard"
    )


def test_there_is_also_a_global_reduce_guard():
    """Belt and braces. The no-preference block covers what is written today; this
    covers whatever somebody adds next without reading this file."""
    guard = re.search(r"@media \(prefers-reduced-motion: reduce\) \{(.*?)\n\}\n", css(), re.S)
    assert guard, "no global reduce guard"
    body = guard.group(1)
    assert "animation-duration" in body and "transition-duration" in body
    assert "*" in body, "the guard does not apply to everything"


def test_no_animation_library_was_added():
    """The landing budget is 400 KB and the LCP element is the H1. Measured 18 Sep:
    GSAP core alone is 27.35 KB gzipped and Motion is 47.7 KB (docs/verified.md)."""
    deps = json.loads(PACKAGE.read_text(encoding="utf-8"))
    installed = {**deps.get("dependencies", {}), **deps.get("devDependencies", {})}
    found = [name for name in installed if name in ANIMATION_LIBRARIES]
    assert not found, f"animation library in the bundle: {found}"


@pytest.mark.skipif(not (EXPORT / "index.html").exists(), reason="no build; CI builds first")
def test_nothing_moves_on_load_above_the_fold():
    """Every moment has to be triggered by something the visitor did. An arrival
    animation in the server-rendered landing markup is a page that performs at you."""
    html = (EXPORT / "index.html").read_text(encoding="utf-8", errors="ignore")
    body = html[: html.index("</footer>")]
    present = [c for c in ARRIVAL if c in body]
    assert not present, f"arrival animation in the landing markup: {present}"


def test_every_moment_is_written_down_with_all_five_columns():
    """Trigger, property, duration, easing and reason. A moment with no reason is
    decoration that survived review because it was small."""
    doc = DESIGN.read_text(encoding="utf-8")
    rows = re.findall(r"^\| `(sf-[\w-]+)` \|(.+)$", doc, re.M)
    assert len(rows) == 5, f"expected five named moments in DESIGN.md, found {len(rows)}"
    for name, row in rows:
        cells = [c.strip() for c in row.split("|") if c.strip()]
        assert len(cells) == 5, f"{name}: expected trigger/property/duration/easing/reason"
        assert re.search(r"\d+\s*ms", cells[2]), f"{name}: no duration"
        for prop in cells[1].replace("+", " ").split():
            assert prop in ALLOWED_PROPERTIES, f"{name} animates {prop}"


def test_no_component_animates_through_a_tailwind_utility():
    """Held-out check, and it caught the real one.

    Every rule above reads globals.css. The button carried shadcn's `transition-all` and
    its own `active:translate-y-px`, written in Tailwind classes where nothing looked —
    so the site had a sixth unnamed moment, animating every property including colour,
    outside the reduced-motion guard, purely because nobody repointed a factory default.
    The press now lives in globals.css as `sf-press`, once, inside the guard."""
    offenders = []
    for path in sorted((ROOT / "frontend" / "src").rglob("*.tsx")):
        text = strip_comments(path.read_text(encoding="utf-8"), language="tsx")
        for cls in TAILWIND_MOTION.findall(text):
            offenders.append(f"{path.name}: {cls}")
    assert not offenders, f"motion outside globals.css and outside the guard: {offenders}"


def test_the_focus_ring_does_not_animate_at_all():
    """It was `animation: sf-draw 0.22s`, drawn with a box-shadow keyframe. Two rules
    broken at once, and the second is the one that matters: a keyboard user is waiting
    on that ring to know where they are, so it must be there the instant they arrive."""
    assert "sf-draw" not in css(), "the focus ring still animates"
    assert "@keyframes sf-draw" not in css()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
