"""Every workflow gets the scopes it uses and no others.

GitHub's rule, quoted: "If you specify the access for any of these permissions, all of
those that are not specified are set to `none`." So an explicit block is already a
whitelist — the only question is whether anything in it is unused, and in self-heal two
things were.

self-heal is the workflow that matters most here. It runs an agent with a broad tool
allowlist, on a repository it can push to, triggered by a failing deploy. What its token
can reach is what a prompt injection in a build log could reach.

    id-token: write     lets a job fetch an OIDC token. There is no
                        google-github-actions/auth step in the workflow and nothing else
                        requests one, so it granted the ability to mint a federated
                        identity to a job that never uses it.
    pull-requests: write  the healer pushes to main or opens an issue. It has never
                        opened a pull request; there is no `gh pr` in the file.

Both removed. What stays is what it demonstrably does: contents (it pushes the fix),
actions (it reads the failed run's logs), issues (it opens "needs Kevin" when the failure
needs a human).
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

# scope -> the thing in the workflow that proves it is used.
EVIDENCE = {
    "contents": ("git push", "actions/checkout"),
    "actions": ("gh run view", "workflow_run"),
    "issues": ("gh issue", "needs Kevin"),
    "pull-requests": ("gh pr ", "pull_request"),
    "id-token": ("google-github-actions/auth", "id_token"),
}


def permissions(name: str) -> dict[str, str]:
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    block = re.search(r"^permissions:\s*\{([^}]*)\}", text, re.M)
    assert block, f"{name} declares no permissions block, so it gets the repo default"
    return dict(
        (k.strip(), v.strip()) for k, v in (pair.split(":") for pair in block.group(1).split(","))
    )


def body(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_every_workflow_declares_its_permissions_explicitly():
    """Without a block the job gets the repository default, which can be read-and-write
    on everything. An explicit block is a whitelist; its absence is not."""
    missing = [
        p.name
        for p in sorted(WORKFLOWS.glob("*.yml"))
        if not re.search(r"^permissions:", p.read_text(encoding="utf-8"), re.M)
    ]
    assert not missing, f"workflows with no explicit permissions: {missing}"


@pytest.mark.mirror_incompatible(reason="reads .github/workflows, which the mirror does not carry")
def test_self_heal_holds_no_scope_it_does_not_use():
    """The one that found something. Each granted scope must have a use in the file."""
    unused = []
    for scope in permissions("self-heal.yml"):
        markers = EVIDENCE.get(scope)
        assert markers, f"unknown scope {scope!r}: add its evidence to EVIDENCE"
        if not any(m in body("self-heal.yml") for m in markers):
            unused.append(scope)
    assert not unused, f"self-heal holds scopes nothing in it uses: {unused}"


@pytest.mark.mirror_incompatible(reason="reads .github/workflows, which the mirror does not carry")
def test_self_heal_can_still_do_the_three_things_it_exists_to_do():
    """Held-out check against over-trimming. Narrowing that breaks the healer is worse
    than the scopes it removed, because the healer is what catches my mistakes."""
    perms = permissions("self-heal.yml")
    assert perms.get("contents") == "write", "it can no longer push the fix"
    assert perms.get("actions") == "read", "it can no longer read the failed run's logs"
    assert perms.get("issues") == "write", "it can no longer open 'needs Kevin'"


def test_no_workflow_grants_write_to_everything():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"^permissions:\s*write-all", text, re.M), path.name


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
