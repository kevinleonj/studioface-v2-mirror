"""The audit must separate the AI default from a decided design, and must not fire
on the decided one."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
# The script is in scripts/, not beside this file, and the fixtures are two files in
# ONE directory rather than directories named f_slop / f_ref. Delivered as siblings of
# this test both times; exit code 2 (file not found) reads as a failure but is not one.
LINT = HERE.parent / "scripts" / "design_audit.py"
FIXTURES = HERE / "fixtures" / "design"
FIXTURE_FILES = {"f_slop": "slop.html", "f_ref": "refined.html"}


def audit(directory: Path) -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, str(LINT), str(directory)],
        capture_output=True,
        text=True,
        errors="replace",  # the emoji rule's evidence is unprintable on a cp1252 console
        check=False,
    )
    return r.returncode, r.stdout


def run(target: str) -> tuple[int, str]:
    """One fixture, staged alone. Auditing the fixtures directory judges slop.html and
    refined.html together, so 'the decided design passes' could never pass."""
    staged = Path(tempfile.mkdtemp()) / "one"
    staged.mkdir()
    shutil.copy(FIXTURES / FIXTURE_FILES[target], staged / FIXTURE_FILES[target])
    return audit(staged)


def test_slop_fixture_fails_with_the_named_tells():
    code, out = run("f_slop")
    assert code == 1
    for rule in (
        "only-default-typeface",
        "ai-purple-primary",
        "gradient-text",
        "cardocalypse",
        "emoji-in-ui",
        "left-border-strip",
        "default-blue-button",
        "averaged-copy",
    ):
        assert rule in out, rule


def test_decided_design_passes():
    code, out = run("f_ref")
    assert code == 0, out
    assert "0 P0, 0 P1" in out


def test_tasteful_default_is_also_a_failure(tmp_path):
    (tmp_path / "x.css").write_text(
        'body{font-family:"Instrument Serif",serif;background:#faf9f6;color:#8a9a5b}',
        encoding="utf-8",
    )
    r = subprocess.run(
        [sys.executable, str(LINT), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 1
    assert "tasteful-default-2026" in r.stdout


def test_allcaps_tracked_eyebrows_are_a_p0(tmp_path):
    """The frontend-design skill lists the tracked ALL-CAPS eyebrow as generated chrome."""
    (tmp_path / "a.css").write_text(
        ".x{text-transform:uppercase;letter-spacing:0.2em}\n"
        ".y{text-transform:uppercase;letter-spacing:0.2em}\n"
        ".z{text-transform:uppercase;letter-spacing:0.12em}\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        [sys.executable, str(LINT), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 1
    assert "allcaps-tracked-eyebrow" in r.stdout


def test_every_finding_prints_on_a_console_that_cannot_encode_emoji(tmp_path):
    """Regression, twice over.

    `emoji-in-ui` is one of this tool's own rules, so its evidence line carries the
    emoji it caught. Printing that on a cp1252 console raises

        UnicodeEncodeError: 'charmap' codec can't encode character '\\U0001f680'

    mid-report, AFTER the exit code is already 1 — so the run looks like a legitimate
    FAIL while every finding sorted after the emoji one disappears. `5 P0, 7 P1` becomes
    one visible line.

    Fixed on 17 Sep, lost when design_audit.py was rewritten, and it returned the moment
    the Stop hook ran the gate in a cp1252 shell instead of my UTF-8 one. Asserting only
    the exit code would pass against the bug, because the crash also exits 1 — which is
    precisely how it got through the first time."""
    shutil.copy(FIXTURES / "slop.html", tmp_path / "slop.html")
    r = subprocess.run(
        [sys.executable, str(LINT), str(tmp_path)],
        capture_output=True,
        text=True,
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
        check=False,
    )
    assert "UnicodeEncodeError" not in r.stderr, r.stderr[-300:]
    assert "Traceback" not in r.stderr, r.stderr[-300:]
    assert "emoji-in-ui" in r.stdout
    assert "averaged-copy" in r.stdout, "findings after the emoji one were lost"
    assert "DESIGN AUDIT:" in r.stdout


def test_the_eyebrow_rule_does_not_depend_on_declaration_order(tmp_path):
    """The gap that let our own page through.

    .sf-label is used 51 times in the built HTML and compiles to

        .sf-label{font-family:var(--font-chivo-mono),ui-monospace,monospace;
                  letter-spacing:.2em;text-transform:uppercase;color:...;font-size:11px}

    which is cluster 5 exactly. The rule did not fire, because it required
    `text-transform: uppercase` to appear BEFORE `letter-spacing`, and Tailwind emitted
    them the other way round. A detector that depends on the order a compiler happens
    to choose is not a detector."""
    (tmp_path / "a.css").write_text(
        ".a{letter-spacing:.2em;text-transform:uppercase}\n"
        ".b{letter-spacing:0.2em;text-transform:uppercase}\n"
        ".c{letter-spacing:.15em;text-transform:uppercase}\n",
        encoding="utf-8",
    )
    code, out = audit(tmp_path)
    assert code == 1, out
    assert "allcaps-tracked-eyebrow" in out


def test_broadsheet_combination_is_a_p0(tmp_path):
    """Hairline rules + zero radius + a mono label family is skill cluster 3, not a decision."""
    (tmp_path / "a.css").write_text(
        ":root{--radius:0}.f{border:1px solid #141312}.l{font-family:var(--font-chivo-mono)}",
        encoding="utf-8",
    )
    r = subprocess.run(
        [sys.executable, str(LINT), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 1
    assert "broadsheet-default" in r.stdout


def test_decided_design_still_passes_after_the_new_rules():
    code, out = run("f_ref")
    assert code == 0, out
