"""The funnel had no events in it at all.

Before this: GA4 carried consent mode and one server-side `purchase` through the
Measurement Protocol. Nothing between arriving and paying was measured, so every
statement in docs/CONVERSION.md was an opinion. The rule from the UI skill is that we
never argue about conversion, we instrument it — and an uninstrumented hypothesis is an
argument with a number stapled to it.

The declared list is the contract. Two ways it can rot and both are checked here: a
call site can invent a name that is in no list, and a name can sit in the list forever
with nothing firing it. The second is worse, because a dashboard built on it shows a
flat line and everyone concludes the thing does not happen.

Naming rules verified 2026-09-18 (docs/verified.md): names are CASE SENSITIVE, must
start with a letter, may hold only letters, numbers and underscores, and are capped at
40 characters. Reserved names may not be reused; `query_id` is a reserved prefix.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_scan import Scanner, strip_comments  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
TRACK = FRONTEND / "lib" / "track.ts"
CONVERSION = ROOT / "docs" / "CONVERSION.md"

# https://support.google.com/analytics/answer/9267744
MAX_NAME_CHARS = 40
MAX_PARAMS = 25
# https://support.google.com/analytics/answer/13316687 — reusing one of these silently
# collides with an automatically collected event and the report becomes unreadable.
RESERVED = {
    "page_view",
    "session_start",
    "first_visit",
    "click",
    "scroll",
    "user_engagement",
    "form_start",
    "form_submit",
    "file_download",
    "view_search_results",
    "video_start",
    "purchase",
}


# A `track(EVENTS.foo)` written in a comment is not a call site, and counting it would
# make test_no_declared_name_is_dead pass for an event nothing actually fires — the
# expensive failure this file exists to prevent.
TRACK_CALL = Scanner(
    name="track-call-site",
    pattern=r"track\(\s*EVENTS\.(\w+)",
    catches=("track(EVENTS.viewProof)", "track( EVENTS.uploadStart, { files: 1 })"),
    ignores=("trackEvent(EVENTS.x)", "track(OTHER.viewProof)"),
)


def declared() -> list[str]:
    """The literal names in the EVENTS map, in declaration order."""
    text = TRACK.read_text(encoding="utf-8")
    block = re.search(r"export const EVENTS = \{(.*?)\n\} as const;", text, re.S)
    assert block, "no `export const EVENTS = { ... } as const;` in track.ts"
    return re.findall(r'"([a-z0-9_]+)"', block.group(1))


def call_sites() -> list[tuple[str, str]]:
    """Every `track(EVENTS.x)` in the app, as (file, key)."""
    out = []
    for path in sorted(FRONTEND.rglob("*.tsx")):
        text = strip_comments(path.read_text(encoding="utf-8"), language="tsx")
        for key in TRACK_CALL.findall(text):
            out.append((path.name, key))
    return out


def keys() -> list[str]:
    text = TRACK.read_text(encoding="utf-8")
    block = re.search(r"export const EVENTS = \{(.*?)\n\} as const;", text, re.S)
    return re.findall(r"^\s*(\w+):", block.group(1), re.M)


def test_every_declared_name_is_legal_for_ga4():
    for name in declared():
        assert len(name) <= MAX_NAME_CHARS, f"{name} is {len(name)} characters"
        assert re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name), name
        assert not name.startswith(("google_", "ga_", "firebase_", "query_id")), name
        assert name not in RESERVED, f"{name} collides with an automatically collected event"


def test_no_call_site_invents_a_name():
    """The whole point of a declared list. A typo in a string literal is invisible until
    someone builds a report on a name that never fires."""
    known = set(keys())
    unknown = [(f, k) for f, k in call_sites() if k not in known]
    assert not unknown, f"call sites using an undeclared key: {unknown}"


def test_no_declared_name_is_dead():
    """The failure that costs the most. A name nobody fires shows up as a flat line, and
    a flat line reads as 'this never happens' rather than 'this was never measured'."""
    used = {k for _, k in call_sites()}
    dead = [k for k in keys() if k not in used]
    assert not dead, f"declared but never fired: {dead}"


def test_every_event_is_a_hypothesis_somebody_wrote_down():
    """An event with no hypothesis is a number nobody will ever act on."""
    doc = CONVERSION.read_text(encoding="utf-8")
    missing = [n for n in declared() if n not in doc]
    assert not missing, f"events with no entry in docs/CONVERSION.md: {missing}"


def test_every_hypothesis_names_the_number_that_would_falsify_it():
    """From the UI skill: each item is a hypothesis with an event AND the number that
    would prove it wrong. Without the second half it is a slogan."""
    doc = CONVERSION.read_text(encoding="utf-8")
    rows = re.findall(r"^\| H\d+ \|(.+)$", doc, re.M)
    assert len(rows) >= 7, f"only {len(rows)} hypotheses in the table"
    for row in rows:
        # A markdown row ends with a pipe, so the naive split leaves a trailing empty
        # cell and `all(cells)` is false for every correct row. Hypothesis, ratio,
        # falsifier: three cells, and the third has to contain a digit.
        cells = [c.strip() for c in row.split("|") if c.strip()]
        assert len(cells) == 3, f"expected hypothesis | ratio | falsifier, got {cells}"
        assert re.search(r"\d", cells[2]), f"no falsifying number in: {row}"


def test_no_event_carries_more_parameters_than_ga4_accepts():
    text = TRACK.read_text(encoding="utf-8")
    for call in re.findall(r"track\(\s*EVENTS\.\w+\s*,\s*\{([^}]*)\}", text):
        assert call.count(":") <= MAX_PARAMS, f"over {MAX_PARAMS} parameters: {call[:80]}"


def test_tracking_is_a_no_op_when_analytics_never_loaded():
    """Consent is denied by default and GA4_ID is empty in every local build, so
    `window.gtag` is frequently undefined. A tracker that throws there takes the click
    handler down with it — the event is the least important thing on that line."""
    text = TRACK.read_text(encoding="utf-8")
    assert "window.gtag?." in text or "typeof window" in text, (
        "track() does not guard against gtag being absent"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
