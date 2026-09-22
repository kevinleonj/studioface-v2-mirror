"""No escape hatch. `SF_SKIP_GATE` let an agent push a red gate on 20 Sep 2026 (see
HANDOFF.md) against the standing rule that the local gate is never skipped. The
override is gone from `.githooks/pre-push`; this file proves it by running the real
hook file as a subprocess against a scratch git repository with a stand-in gate
script, so the proof is what the hook actually does when it runs, not a word in its
comments or a marker anywhere in its source.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".githooks" / "pre-push"

GREEN_CI = "import sys\nsys.exit(0)\n"
RED_CI = "import sys\nsys.exit(1)\n"


def _sanitized_git_env() -> dict[str, str]:
    """Every `GIT_*` variable stripped.

    The incident this guards against: a real push sets `GIT_DIR` (and sometimes
    `GIT_WORK_TREE`) in the hook's own process environment, exactly the way every
    git hook receives them. This file's scratch-repo commands used to inherit that
    environment unfiltered, so when the hook ran for real (not by hand) its own
    `git init`/`add`/`commit` calls, run with `cwd` pointing at a throwaway
    directory, silently targeted the REAL repository's object database instead —
    `GIT_DIR` wins over `cwd` in git's own resolution order. That committed this
    file's one-line HANDOFF.md and stand-in ci.py, authored by "Test
    <test@example.com>", onto a real branch, and one of the runs also flipped
    `core.bare`. See HANDOFF.md, 22 Sep 2026, for the forensic trail. Every
    subprocess in this file that touches a scratch repository — including the
    nested hook invocation, which shells out to git itself — now runs with this
    stripped environment, so no ambient `GIT_DIR` can ever redirect it.
    """
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _scratch_repo(tmp_path: Path, ci_source: str) -> Path:
    """A throwaway git repository holding only what the hook touches: its own root,
    a HANDOFF.md, and a scripts/ci.py stand-in. Real git, real subprocess, real exit
    code — the hook never sees a test double of itself, only of the gate it calls.

    A real commit is required: the pre-existing hook, before this task's fix, ran
    `git rev-parse --short HEAD` on the SF_SKIP_GATE path, and a repo with no commit
    yet fails that with an unrelated 128 rather than exercising the hatch. Without a
    HEAD the old hatch's bypass and a crash look the same from outside (both
    non-zero), which would have let this test pass for the wrong reason.
    """
    env = _sanitized_git_env()
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, env=env, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=repo, env=env, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, env=env, check=True)
    (repo / "scripts" / "ci.py").write_text(ci_source, encoding="utf-8")
    (repo / "HANDOFF.md").write_text("# HANDOFF\n", encoding="utf-8")
    subprocess.run(["git", "add", "scripts/ci.py", "HANDOFF.md"], cwd=repo, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=repo, env=env, check=True)
    return repo


def _run_hook(repo: Path, *, skip_gate: str | None) -> subprocess.CompletedProcess:
    env = _sanitized_git_env()
    if skip_gate is not None:
        env["SF_SKIP_GATE"] = skip_gate
    return subprocess.run(
        ["sh", str(HOOK)],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("skip_gate", [None, "because I said so"])
def test_a_red_gate_is_refused_whether_or_not_the_variable_is_set(tmp_path, skip_gate):
    repo = _scratch_repo(tmp_path, RED_CI)
    result = _run_hook(repo, skip_gate=skip_gate)
    assert result.returncode != 0, (
        f"a red gate must be refused (SF_SKIP_GATE={skip_gate!r}); got exit "
        f"{result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


@pytest.mark.parametrize("skip_gate", [None, "because I said so"])
def test_a_green_gate_still_lets_the_push_through(tmp_path, skip_gate):
    repo = _scratch_repo(tmp_path, GREEN_CI)
    result = _run_hook(repo, skip_gate=skip_gate)
    assert result.returncode == 0, (
        f"a green gate must let the push through (SF_SKIP_GATE={skip_gate!r}); got "
        f"exit {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_the_variable_changes_nothing_about_the_outcome(tmp_path):
    """The claim in plain words: setting the variable and not setting it must land
    on the exact same exit code, red or green, because there is no branch left that
    reads it."""
    red_repo = _scratch_repo(tmp_path / "red", RED_CI)
    green_repo = _scratch_repo(tmp_path / "green", GREEN_CI)

    red_without = _run_hook(red_repo, skip_gate=None)
    red_with = _run_hook(red_repo, skip_gate="because I said so")
    assert red_without.returncode == red_with.returncode != 0

    green_without = _run_hook(green_repo, skip_gate=None)
    green_with = _run_hook(green_repo, skip_gate="because I said so")
    assert green_without.returncode == green_with.returncode == 0


def _rev_parse_head(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_scratch_repo_ignores_an_ambient_git_dir(tmp_path, monkeypatch):
    """The exact incident, reproduced safely. `ambient` here stands in for a real,
    live repository: it is a genuine git repository with its own commit, built the
    same way `_scratch_repo` builds its throwaway one. `GIT_DIR`/`GIT_WORK_TREE` are
    then pointed at it, in the process environment, the same way a real git hook
    invocation sets them — not passed as an argument, because the leak this guards
    against was never a function argument, it was the ambient environment. If
    `_scratch_repo`'s git commands ever again inherit that environment unfiltered,
    they will commit into `ambient`'s history instead of their own, and this test
    catches that by checking `ambient`'s own HEAD never moved."""
    ambient = tmp_path / "ambient"
    ambient.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=ambient, check=True)
    subprocess.run(["git", "config", "user.email", "ambient@example.com"], cwd=ambient, check=True)
    subprocess.run(["git", "config", "user.name", "Ambient"], cwd=ambient, check=True)
    (ambient / "real-work.txt").write_text("not a scratch file\n", encoding="utf-8")
    subprocess.run(["git", "add", "real-work.txt"], cwd=ambient, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "the real repository's own history"],
        cwd=ambient,
        check=True,
    )
    ambient_head_before = _rev_parse_head(ambient)

    monkeypatch.setenv("GIT_DIR", str(ambient / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(ambient))
    victim = _scratch_repo(tmp_path / "victim", GREEN_CI)
    # The poisoning must stay scoped to the call above, the thing under test - the
    # verification reads below must see the real, unpoisoned environment, or they
    # would inherit the same leak they exist to catch.
    monkeypatch.delenv("GIT_DIR", raising=False)
    monkeypatch.delenv("GIT_WORK_TREE", raising=False)

    assert (victim / ".git").is_dir(), (
        "the scratch repo has no .git of its own - it committed somewhere else"
    )
    scratch_head = _rev_parse_head(victim)
    ambient_head_after = _rev_parse_head(ambient)
    assert ambient_head_after == ambient_head_before, (
        "the ambient repository's HEAD moved: the scratch repo's seed commit leaked "
        "into it instead of landing in its own .git - this is the 22 Sep 2026 "
        "incident, reproduced"
    )
    assert scratch_head != ambient_head_after
