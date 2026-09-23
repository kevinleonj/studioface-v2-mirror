"""Task 94: the public mirror's own suite ends at "0 failed" without hiding real failures.

The reviewer ran the published mirror (6585dee) with `pip install -e ".[dev]"` and got
821 passed, 21 failed. Reproduced here on 23 September against a fresh clone of the same
snapshot: the same 21, each caused by the mirror build, not by the code. Twelve read
.github/, which the mirror does not carry; three use cs_test_ fixture ids the mirror
redacts; four feed the redactor the owner's address, which the mirror has already
redacted; one needs the hook's executable bit, lost because the mirror is committed from
Windows; one needs core.hooksPath, which a fresh clone never sets.

Those tests carry `@pytest.mark.mirror_incompatible(reason=...)`, and tests/conftest.py
skips them ONLY when MIRROR.txt is at the repository root, a file only
scripts/make_public_mirror.py writes. In this private repository they always run. The
set is pinned in tests/mirror_incompatible.txt so it cannot grow quietly: marking one
more test means editing that file too, in the same diff a reviewer reads.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(ROOT))

import conftest  # noqa: E402

from scripts import check_mirror_suite, make_public_mirror  # noqa: E402

PINNED = TESTS / "mirror_incompatible.txt"
MARKER = "mirror_incompatible"


def _is_marker(node: ast.expr) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    return isinstance(target, ast.Attribute) and target.attr == MARKER


def _reason(node: ast.expr) -> str:
    if not isinstance(node, ast.Call):
        return ""
    for kw in node.keywords:
        if kw.arg == "reason" and isinstance(kw.value, ast.Constant):
            return str(kw.value.value)
    return ""


def marked() -> dict[str, str]:
    """test id -> reason, for every test function carrying the marker."""
    found = {}
    for path in sorted(TESTS.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for deco in filter(_is_marker, node.decorator_list):
                    found[f"tests/{path.name}::{node.name}"] = _reason(deco)
    return found


def pinned() -> set[str]:
    lines = PINNED.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def differences(marked_ids: set[str], pinned_ids: set[str]) -> list[str]:
    return [f"marked, not pinned: {i}" for i in sorted(marked_ids - pinned_ids)] + [
        f"pinned, not marked: {i}" for i in sorted(pinned_ids - marked_ids)
    ]


# ------------------------------------------------ the pin: marked set == pinned file


def test_the_marked_set_is_exactly_the_pinned_set():
    assert differences(set(marked()), pinned()) == []


def test_the_pin_holds_21_plus_this_files_2_plus_the_deploy_yml_readers():
    """The reviewer's 21; this file's own 2 (option b); and the tests added since that
    read deploy.yml, the reviewer's most common reason: 4 from task 95g, 2 from 95b."""
    assert len(pinned()) == 29


def test_every_marker_states_its_reason():
    assert [i for i, reason in marked().items() if not reason.strip()] == []


def test_the_comparison_fails_when_the_sets_differ():
    """Meta-test: the pin can fail. One extra marked, one missing: both reported."""
    found = differences({"tests/a.py::x", "tests/a.py::y"}, {"tests/a.py::x", "tests/a.py::z"})
    assert found == ["marked, not pinned: tests/a.py::y", "pinned, not marked: tests/a.py::z"]


# ------------------------------------------------ the skip: only inside a mirror


@pytest.mark.mirror_incompatible(
    reason="it asserts this repository's root has no MIRROR.txt; the mirror's always does"
)
def test_a_repository_without_mirror_txt_is_not_a_mirror(tmp_path):
    """Must be refused: this private repository never skips a marked test."""
    assert conftest.in_mirror(tmp_path) is False
    assert conftest.in_mirror(ROOT) is False


def test_a_repository_with_mirror_txt_is_a_mirror(tmp_path):
    """Must get through."""
    (tmp_path / "MIRROR.txt").write_text("source commit: abc\n", encoding="utf-8")
    assert conftest.in_mirror(tmp_path) is True


def test_a_directory_called_mirror_txt_does_not_count(tmp_path):
    """Nobody asked for this one: only the file make_public_mirror writes turns skipping on."""
    (tmp_path / "MIRROR.txt").mkdir()
    assert conftest.in_mirror(tmp_path) is False


# ------------------------------------------------ the build


@pytest.mark.mirror_incompatible(
    reason="it builds a mirror, which needs the private repository's git index"
)
def test_the_build_writes_mirror_txt_and_run_me_first_and_drops_github(tmp_path):
    target = tmp_path / "mirror"
    assert make_public_mirror.main(["make_public_mirror.py", str(target)]) in (0, 3)
    commit = (target / "MIRROR.txt").read_text(encoding="utf-8")
    assert "source commit:" in commit, commit
    run_me = (target / "RUN-ME-FIRST.md").read_text(encoding="utf-8")
    for step in ("python -m venv .venv", 'pip install -e ".[dev]"', "pytest -q", "0 failed"):
        assert step in run_me, step
    assert not (target / ".github").exists()


# ------------------------------------------------ the check script's reading of pytest


def test_zero_failed_is_read_from_a_summary_with_no_failures():
    assert check_mirror_suite.failures("824 passed, 21 skipped in 113.8s") == 0


def test_failures_and_errors_both_count():
    assert check_mirror_suite.failures("3 failed, 820 passed, 2 errors in 9s") == 5


def test_an_unreadable_summary_is_a_failure_not_a_pass():
    assert check_mirror_suite.failures("") is None


def test_a_private_skip_that_mentions_the_mirror_is_found():
    out = "SKIPPED [1] tests/test_x.py:4: mirror_incompatible: reads .github/\nok\n"
    assert check_mirror_suite.mirror_skips(out) == [out.splitlines()[0]]


def test_ordinary_private_skips_are_not_mirror_skips():
    assert (
        check_mirror_suite.mirror_skips("SKIPPED [2] tests/test_y.py:9: needs RUN_FUNNEL\n") == []
    )


@pytest.mark.parametrize("line", ["SKIPPED [1] tests/t.py:1: MIRROR txt", "SKIPPED [1] a: Mirror"])
def test_the_mirror_word_is_matched_in_any_case(line):
    assert check_mirror_suite.mirror_skips(line) == [line]
