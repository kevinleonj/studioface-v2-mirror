"""Task 80: an issue parked until after launch must not block the launch.

#6 (your own before/after pairs), #7 (Resend region), #9 (Docker Desktop) and #11 (CI
token permission) are all real and all wanted, and none of them has to be true before an
ad runs. They were blocking only because the preflight counted every open issue except
the go-live one. The label is the record of that decision, so the preflight reads it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import go_live  # noqa: E402

AFTER_LAUNCH = "after launch"


def _rows(monkeypatch, rows):
    monkeypatch.setattr(go_live, "sh", lambda argv: (0, json.dumps(rows)))


def test_an_after_launch_issue_does_not_block(monkeypatch):
    """Must get through."""
    _rows(
        monkeypatch,
        [{"number": 7, "title": "needs Kevin: Resend region", "labels": [{"name": AFTER_LAUNCH}]}],
    )
    check = go_live.check_blocking_issues()[0]  # the verdict check; parked lines follow it
    assert check.mark == go_live.OK, check


def test_an_unlabelled_issue_still_blocks(monkeypatch):
    """Must be refused. The label is a decision someone made, not a default."""
    _rows(monkeypatch, [{"number": 4, "title": "needs Kevin: run the test purchase", "labels": []}])
    check = go_live.check_blocking_issues()[0]  # the verdict check; parked lines follow it
    assert check.mark == go_live.NO, check
    assert "#4" in check.detail


def test_the_go_live_issue_itself_is_still_not_counted(monkeypatch):
    """The behaviour that was already there, kept."""
    _rows(monkeypatch, [{"number": 8, "title": "needs Kevin: go live", "labels": []}])
    check = go_live.check_blocking_issues()[0]  # the verdict check; parked lines follow it
    assert check.mark == go_live.OK, check


def test_a_missing_labels_field_is_treated_as_unlabelled(monkeypatch):
    """Nobody asked for this one. If the gh JSON ever comes back without `labels`, the
    preflight must fail CLOSED - block - not wave the issue through."""
    _rows(monkeypatch, [{"number": 4, "title": "needs Kevin: run the test purchase"}])
    check = go_live.check_blocking_issues()[0]  # the verdict check; parked lines follow it
    assert check.mark == go_live.NO, check
