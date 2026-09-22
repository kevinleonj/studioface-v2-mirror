"""The meta-test. It tests the tests, because four of them were asleep in one day.

Two failure modes, both of which produce a test that passes against every offender it
was written to catch, and both of which look completely correct in a diff.

**A test that greps its own rationale.** `test_header` searched the header source for
"fixed" and "sticky" — words that appear in the comment explaining why it is neither.
`test_bootstrap` grepped `bootstrap.py` for `core.hooksPath`, which also appears in the
comment describing that line. `test_the_wait` caught `<Progress value={60}>` inside the
note recording that `<Progress value={60}>` had been deleted.

**A regex whose `\\b` reached the file as a literal backspace byte.** Written through a
heredoc, `\\b` arrived as `\\x08`. `<Button\\x08([^>]*?)>` matches nothing. It passed
against four 32px controls on the money path, and `transition-all|animate-[\\w-]+` with
the same corruption passed against seven.

So a scanning pattern is no longer a regex somebody wrote inline. It is a `Scanner`,
which carries examples of what it must catch and what it must ignore, refuses a pattern
containing a control character at construction time, and is registered here so this file
can prove every one of them can still fail.

`tests/fixtures/offenders/` holds one file per language containing every violation the
suite claims to catch. Any scanner that does not fire against it was asleep.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_scan import REGISTRY, Scanner, strip_comments  # noqa: E402

# Importing these is what populates REGISTRY. Named explicitly rather than discovered by
# a glob: if a module is dropped from this list its scanners stop being proved, and a
# missing name in a literal list is visible in a diff where a silently-smaller glob
# result is not.
SCANNER_MODULES = (
    "test_tap_targets",
    "test_motion",
    "test_the_wait",
    "test_conversion_events",
    "test_go_live",
    "test_pre_push_hook",
    "test_same_origin",
)
for _name in SCANNER_MODULES:
    __import__(_name)

ROOT = Path(__file__).resolve().parents[1]
SCANNED_DIRS = (ROOT / "tests", ROOT / "scripts")
# The byte that started it. \x08 is a legal character in a Python string and a legal
# character in a regex, where it means "match a backspace" — which no source file
# contains, so the pattern silently matches nothing.
BACKSPACE = "\x08"


def registered() -> list[Scanner]:
    assert REGISTRY, "no scanners registered; the importing tests did not load"
    assert len(REGISTRY) >= len(SCANNER_MODULES), (
        f"only {len(REGISTRY)} scanners for {len(SCANNER_MODULES)} modules"
    )
    return list(REGISTRY.values())


def test_every_scanner_catches_what_it_says_it_catches():
    """The positive half. A pattern with no worked example is a pattern nobody checked."""
    for scanner in registered():
        assert scanner.catches, f"{scanner.name} declares nothing it must catch"
        for example in scanner.catches:
            assert scanner.findall(example), f"{scanner.name} missed its own example: {example!r}"


def test_every_scanner_ignores_what_it_says_it_ignores():
    """The negative half, which is the one that keeps a scanner honest. Without it the
    cheapest way to pass the test above is `.` — and that flags everything."""
    for scanner in registered():
        assert scanner.ignores, f"{scanner.name} declares nothing it must ignore"
        for example in scanner.ignores:
            assert not scanner.findall(example), (
                f"{scanner.name} fired on something it should ignore: {example!r}"
            )


def test_no_scanner_can_be_built_from_a_pattern_with_a_control_character():
    """Construction-time, not lint-time. The corrupted pattern should never survive an
    import, let alone a commit."""
    with pytest.raises(ValueError, match="control character"):
        Scanner(
            name="deliberately-corrupt",
            pattern=f"<Button{BACKSPACE}([^>]*?)>",
            catches=('<Button type="submit">',),
            ignores=("<ButtonPrimitive>",),
            register=False,
        )


def test_no_source_file_in_the_repo_holds_a_stray_backspace():
    """The repo-wide sweep. A control character in a pattern is invisible in every diff
    view I have, so the only place to catch it is a byte-level check."""
    offenders = []
    for directory in SCANNED_DIRS:
        for path in sorted(directory.rglob("*.py")):
            text = path.read_text(encoding="utf-8", errors="replace")
            if BACKSPACE in text:
                line = text[: text.index(BACKSPACE)].count("\n") + 1
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{line}")
    assert not offenders, f"literal backspace byte in source: {offenders}"


def test_comment_stripping_removes_prose_without_removing_the_code_beside_it():
    js = 'const a = 1; // was transition-all\n<div className="transition-colors" />'
    stripped = strip_comments(js, language="ts")
    assert "transition-all" not in stripped, "the comment survived"
    assert "transition-colors" in stripped, "the code did not"

    jsx = "{/* <Progress value={60} /> was deleted */}\n<Progress value={45} />"
    stripped = strip_comments(jsx, language="ts")
    assert "value={60}" not in stripped
    assert "value={45}" in stripped

    py = 'x = 1  # core.hooksPath in a comment\nsh(["git", "config", "core.hooksPath"])'
    stripped = strip_comments(py, language="py")
    assert stripped.count("core.hooksPath") == 1, "the comment and the call both survived"


def test_comment_stripping_does_not_eat_a_url_inside_a_string():
    """`//` in `https://` is not a comment, and a stripper that thinks it is deletes the
    rest of the line — which would quietly blind every test that scans a file holding a
    URL."""
    text = 'const u = "https://studioface.app/health"; // the real comment'
    stripped = strip_comments(text, language="ts")
    assert "studioface.app/health" in stripped
    assert "the real comment" not in stripped


def test_every_scanner_fires_against_the_offender_fixture():
    """The question item 2 actually asked: which of these were asleep?

    One fixture file per language, holding every violation the suite claims to catch.
    A scanner that cannot find its own violation in here is not guarding anything."""
    fixtures = ROOT / "tests" / "fixtures" / "offenders"
    assert fixtures.is_dir(), "no offender fixture directory"
    asleep = []
    for scanner in registered():
        path = fixtures / scanner.fixture
        assert path.exists(), f"{scanner.name} names a fixture that does not exist: {path.name}"
        text = path.read_text(encoding="utf-8")
        if scanner.strips_comments:
            text = strip_comments(text, language=scanner.language)
        if not scanner.findall(text):
            asleep.append(scanner.name)
    assert not asleep, f"scanners that found nothing in the offender fixture: {asleep}"


def test_the_fixture_is_not_quietly_empty():
    """A fixture that lost its contents would make the test above pass for every scanner
    at once, which is the same shape of failure all over again."""
    fixtures = ROOT / "tests" / "fixtures" / "offenders"
    for path in sorted(fixtures.glob("*")):
        assert len(path.read_text(encoding="utf-8").strip()) > 200, f"{path.name} is nearly empty"


def test_tests_that_scan_product_source_strip_comments_first():
    """The rule, enforced. A test that reads a source file under app/, scripts/ or
    frontend/src/ and then searches it must go through the helper, because searching raw
    source means searching the prose that explains the code."""
    exempt = {
        # Reads its own fixture files, not product source.
        "test_source_scanners.py",
        # Reads a temporary state file it wrote itself; the path words that trip the
        # heuristic are in its prose, not in a scan.
        "test_ci_state_markers.py",
        # Reads .github/workflows/deploy.yml and extracts the curl paths with an anchored
        # pattern that a YAML comment cannot satisfy — `curl -fsS ... "$URL..."` inside a
        # `#` line would still be a smoke path somebody wrote and then commented out,
        # which is worth flagging rather than hiding.
        "test_health.py",
        # Compares a built artefact (frontend/out) against itself; HTML has no comments
        # carrying our rationale, and the RSC payload is handled explicitly.
        "test_budgets.py",
        "test_hero.py",
        "test_header.py",
        "test_demo_assets.py",
        "test_footer_links.py",
        "test_seo.py",
        "test_legal_identity.py",
        "test_contrast.py",
        # Reads a generated SVG artefact (scripts/make_favicon.py output, no comments to
        # strip) and demo_server.PLACEHOLDERS, a plain list checked by membership, not by
        # a pattern that could also match a comment.
        "test_favicon.py",
        # Compares two built artefacts (frontend/out) against each other and against
        # sitemap.xml; HTML has no comments carrying our rationale. Its one product-source
        # scan (ad-landing.tsx, checking the shared uploader is imported) goes through
        # strip_comments explicitly.
        "test_ad_landing_pages.py",
        # Reads docs/ads/rsa.json (JSON data, no comments to strip) and built export
        # HTML pages (frontend/out), same as test_ad_landing_pages.py above; runs
        # scripts/check_ad_copy.py and scripts/check_ad_claims.py as subprocesses
        # rather than reading their source.
        "test_check_ad_copy.py",
        # Renamed from test_check_ad_claims.py in task 33 — this is the check command's
        # own name for the file (work/queue/33...), and the reason above still holds.
        "test_ad_claims.py",
        # Task 52. Reads built export HTML (frontend/out) only, same reason as
        # test_legal_identity.py and test_ad_landing_pages.py above: rendered HTML
        # carries no source comments to strip.
        "test_return_policy.py",
        # Task 74. Reads scripts/make_public_mirror.py whole, comments included, on
        # purpose: that file ships byte for byte into the public mirror, so a leak
        # sitting in a comment is exactly as real as one sitting in code. Stripping
        # comments first would hide the failure this test exists to catch.
        "test_make_public_mirror.py",
    }
    sources = re.compile(r'"(?:app|scripts|frontend)"|/\s*"src"|"(?:tsx|py)"')
    offenders = []
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        if path.name in exempt:
            continue
        text = path.read_text(encoding="utf-8")
        if not sources.search(text):
            continue
        if "read_text" not in text:
            continue
        if "strip_comments" not in text and "COMMENT" not in text and "source_scan" not in text:
            offenders.append(path.name)
    assert not offenders, f"tests scanning product source without stripping comments: {offenders}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
