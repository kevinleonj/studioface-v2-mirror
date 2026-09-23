"""The escalation channel: a GitHub issue titled "needs Kevin: <what>".

Both the operating rules and .github/workflows/self-heal.yml say the same thing when
something needs money, credentials or a console action: stop and open an issue. That
instruction was dead. `github_repository` defaults `has_issues` to false and infra/
never set it, so the repository had issues disabled and every escalation failed with

    the 'kevinleonj/studioface-v2' repository has disabled issues

A failed escalation is silent: the deploy is green, the rule was followed, and nobody
is told. So the channel is pinned here, at both ends — the repository accepts issues,
and the healer workflow holds the permission to file one.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GITHUB_TF = ROOT / "infra" / "github.tf"
SELF_HEAL = ROOT / ".github" / "workflows" / "self-heal.yml"


def repo_resource() -> str:
    """The body of resource "github_repository" "repo" { ... }."""
    text = GITHUB_TF.read_text(encoding="utf-8")
    m = re.search(r'resource\s+"github_repository"\s+"repo"\s*\{(.*?)\n\}', text, re.S)
    assert m, f'no github_repository "repo" resource in {GITHUB_TF}'
    return m.group(1)


def test_the_repository_accepts_issues():
    """Without this the only way these rules have to ask Kevin for anything is closed."""
    assert re.search(r"^\s*has_issues\s*=\s*true\s*$", repo_resource(), re.M), (
        "github.tf must set has_issues = true; the provider defaults it to false"
    )


@pytest.mark.mirror_incompatible(reason="reads .github/workflows, which the mirror does not carry")
def test_the_healer_workflow_can_open_one():
    """Held-out check: the other end of the same channel. self-heal.yml's prompt ends
    with "open a GitHub issue", which needs the issues: write permission on the job's
    token — and that permission is worthless if the repository refuses issues."""
    perms = SELF_HEAL.read_text(encoding="utf-8")
    assert re.search(r"issues:\s*write", perms), (
        f"{SELF_HEAL} tells Claude to open an issue but does not grant issues: write"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
