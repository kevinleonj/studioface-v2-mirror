"""Task 91: every issue the 'after launch' label keeps out of the verdict is printed.

Task 80 made the label decide what blocks a launch. Nothing stops a label being added
by habit rather than by decision, and a skipped issue that is never shown is a decision
nobody re-reads. So each one is listed, number and title, in every dry run - and the
READY line says how many were set aside, because the verdict is the line people read.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import go_live  # noqa: E402

PARKED_7 = {
    "number": 7,
    "title": "needs Kevin: Resend region is us-east-1",
    "labels": [{"name": "after launch"}],
}
PARKED_9 = {
    "number": 9,
    "title": "needs Kevin: Docker Desktop is not installed",
    "labels": [{"name": "after launch"}],
}
BLOCKING_4 = {"number": 4, "title": "needs Kevin: run the test purchase", "labels": []}


def _checks(monkeypatch, rows):
    monkeypatch.setattr(go_live, "sh", lambda argv: (0, json.dumps(rows)))
    return go_live.check_blocking_issues()


def _parked(checks):
    return [c for c in checks if c.mark == go_live.PARKED]


def test_no_parked_issue_prints_no_parked_line(monkeypatch):
    """Empty: nothing set aside, nothing extra printed."""
    assert _parked(_checks(monkeypatch, [BLOCKING_4])) == []


def test_one_parked_issue_is_listed_with_its_number_and_title(monkeypatch):
    (line,) = _parked(_checks(monkeypatch, [PARKED_7]))
    assert "#7" in line.detail and "Resend region is us-east-1" in line.detail


def test_every_parked_issue_is_listed_not_just_the_first(monkeypatch):
    lines = _parked(_checks(monkeypatch, [PARKED_7, BLOCKING_4, PARKED_9]))
    details = " ".join(c.detail for c in lines)
    assert len(lines) == 2 and "#7" in details and "#9" in details


def test_a_parked_line_never_blocks_the_verdict(monkeypatch, capsys):
    """Must get through: listing an issue is not the same as blocking on it."""
    assert go_live.verdict(_checks(monkeypatch, [PARKED_7, PARKED_9])) == 0


def test_the_ready_line_counts_what_was_set_aside(monkeypatch, capsys):
    """The verdict is the line people read, so the count is on it."""
    go_live.verdict(_checks(monkeypatch, [PARKED_7, PARKED_9]))
    out = capsys.readouterr().out
    assert "READY" in out and "2 issue(s) parked 'after launch'" in out, out


def test_an_unlabelled_issue_still_blocks_and_is_not_listed_as_parked(monkeypatch):
    """Must be refused: the listing never turns a blocking issue into a parked one."""
    checks = _checks(monkeypatch, [PARKED_7, BLOCKING_4])
    assert go_live.verdict(checks) == 1
    assert all("#4" not in c.detail for c in _parked(checks))


def test_gh_failing_still_answers_unknown_not_an_empty_parked_list(monkeypatch):
    """Failure: gh down must stay an unanswered check, never a silent READY."""
    monkeypatch.setattr(go_live, "sh", lambda argv: (1, "gh: not logged in"))
    checks = go_live.check_blocking_issues()
    assert [c.mark for c in checks] == [go_live.UNKNOWN]
