"""The gate has to be attached to the push, and the attachment has to be reviewable.

A hook in .git/hooks exists on exactly one machine, is not versioned, and nobody can
see it in a diff. `core.hooksPath` points git at a directory in the repository, so the
hook is reviewed like any other file and arrives with a clone.

There is no escape hatch (see tests/test_no_gate_skip.py for the proof, run against
the hook's real behaviour rather than its text): the only way a push gets through is
a green run of scripts/ci.py.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_scan import Scanner, strip_comments  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".githooks" / "pre-push"

# The hook is a shell script whose comments explain what it refuses and why, in exactly
# the words these tests look for. Every assertion below reads `code()`, not the file.
GATE_CALL = Scanner(
    name="shell-gate-invocation",
    pattern=r"scripts/ci\.py",
    catches=('"$PY" scripts/ci.py', "python scripts/ci.py || exit 1"),
    ignores=("scripts/ci_py", "scripts.ci.py"),
    fixture="offenders.sh",
    language="sh",
)


def code() -> str:
    """The hook with its comments removed. Reading the raw file means reading the
    rationale, which is the bug class this whole helper exists for."""
    return strip_comments(HOOK.read_text(encoding="utf-8"), language="sh")


def test_the_hook_is_versioned_and_executable_as_a_shell_script():
    assert HOOK.exists(), "no versioned pre-push hook"
    assert HOOK.read_text(encoding="utf-8").startswith("#!/bin/sh")


def test_the_hook_runs_the_gate_and_refuses_on_red():
    body = code()
    assert GATE_CALL.findall(body), "the hook does not run the gate"
    assert "exit 1" in body, "the hook cannot refuse anything"
    assert "REFUSED" in body


@pytest.mark.skipif(
    os.environ.get("CI") == "true",
    reason="core.hooksPath is developer-machine config; a CI checkout has none and never pushes",
)
@pytest.mark.mirror_incompatible(
    reason="a fresh clone has no core.hooksPath; the private repo's bootstrap sets it"
)
def test_git_is_actually_pointed_at_the_versioned_hooks():
    """The file existing proves nothing: git only runs it when core.hooksPath says so.

    Skipped on CI, and that skip is the point of the test below. I first wrote this
    without the guard and it failed the `ci` job of run 35313074204 with
    `assert '' == '.githooks'` — a test asserting the state of a laptop, run on a
    runner that has no laptop and no reason to push. GitHub Actions documents CI=true
    as always set (docs/verified.md), so the condition is a fact rather than a guess.
    """
    out = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.stdout.strip() == ".githooks", (
        "core.hooksPath is not .githooks — run: git config core.hooksPath .githooks"
    )


@pytest.mark.mirror_incompatible(
    reason="the mirror is committed from Windows, so the hook loses its executable bit"
)
def test_the_hook_is_executable_in_the_index_so_git_does_not_ignore_it():
    """Measured, not reasoned. Pushing this repo printed:

        hint: The '.githooks/pre-push' hook was ignored because it's not set as
        hint: executable.

    git tests the hook with access(X_OK) and skips one it cannot execute: no error, no
    gate, exit 0. So the two tests above can both pass, core.hooksPath can be set, and
    the gate can still protect nothing. The mode has to be right in the INDEX, because
    the index is what a clone receives.
    """
    out = subprocess.run(
        ["git", "ls-files", "-s", "--", ".githooks/pre-push"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.stdout.strip(), "the pre-push hook is not tracked by git at all"
    assert out.stdout.split()[0] == "100755", (
        "the versioned pre-push hook is not executable in the index, so git ignores it "
        "on every POSIX clone — run: git update-index --chmod=+x .githooks/pre-push"
    )


def test_a_fresh_clone_gets_the_hook_without_anybody_remembering():
    """Held-out check, and the half that survives the skip above. If setting
    core.hooksPath is only ever done by hand, then the gate is attached on exactly one
    machine and every other clone pushes unguarded."""
    bootstrap = (ROOT / "bootstrap.py").read_text(encoding="utf-8")
    assert "core.hooksPath" in bootstrap, (
        "bootstrap.py does not configure the hook, so a fresh clone has no pre-push gate"
    )


# ---------------------------------------------------------------- the gate's contents


def gate_source() -> str:
    return (ROOT / "scripts" / "ci.py").read_text(encoding="utf-8")


def test_the_workflow_linter_is_part_of_the_gate():
    """Item 4's actual requirement. A linter nobody runs is a file, not a check."""
    assert "workflow_lint.py" in gate_source()


def test_the_gate_declares_every_workflow_command_it_mirrors():
    """MIRRORS is the contract workflow_lint matches against. Adding a step to CI
    without adding it here makes the linter fail, which is the point."""
    src = gate_source()
    mirrors = re.search(r"MIRRORS = \((.*?)\)", src, re.S)
    assert mirrors, "the gate no longer declares what it mirrors"
    for expected in ("npm ci", "npm run build", "design_audit.py", "workflow_lint.py", "pytest"):
        assert expected in mirrors.group(1), f"{expected!r} is not declared in MIRRORS"


def test_the_gate_names_every_cloud_only_job_with_a_reason():
    """No silent subsets: anything that cannot run here is printed every run."""
    src = gate_source()
    block = re.search(r"CLOUD_ONLY_JOBS = \{(.*?)\}", src, re.S)
    assert block, "the gate no longer declares its cloud-only jobs"
    assert "JRE 21" in block.group(1), "the emulator exemption must state the reason"
    for job in ("emulator", "infra", "heal"):
        assert f'"{job}"' in block.group(1), f"{job} is not accounted for"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
