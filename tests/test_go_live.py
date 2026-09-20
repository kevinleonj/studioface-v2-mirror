"""The go-live preflight, which is allowed to check everything and change nothing.

docs/GO-LIVE.md ends with a line this script has to obey rather than work around:

    It does not automate itself. A go-live that runs unattended is a go-live nobody
    read the plan for.

So `scripts/go_live.py --dry-run` is the only mode that exists. Run without the flag it
refuses and says why. It reads: git state, the built export, Secret Manager secret NAMES
(never a value), CI variable and secret NAMES, whether the live Terraform prefix is
already occupied, whether the refund events are declared, whether production is healthy
and the kill switch is off, and which "needs Kevin" issues still block.

Then it prints the ordered command list from GO-LIVE.md with a verdict per step, so the
go-live is one command to CHECK and a human decision to run.

The rule it protects: never apply infrastructure, never deploy directly, never switch
Stripe to live, never read a secret's value. A preflight that could do any of those is
not a preflight.
"""

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_scan import Scanner, strip_comments  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "go_live.py"
GO_LIVE = ROOT / "docs" / "GO-LIVE.md"

# The mutating verbs, as (command, subcommand...) tuples. If the preflight can build an
# argv containing all the parts of any one of these, it is not a preflight. Written as
# parts rather than whole strings because the file QUOTES every one of these in prose —
# printing them for a human to run is the entire job.
FORBIDDEN = (
    ("terraform", "apply"),
    ("gcloud", "run", "deploy"),
    ("secrets", "versions", "add"),
    ("gh", "secret", "set"),
    ("gh", "variable", "set"),
    ("git", "push"),
)


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        errors="replace",
        cwd=ROOT,
        check=False,
    )


# Every bracketed list, which is where an argv would have to live. A Scanner because
# go_live.py QUOTES `terraform apply` and the rest in its prose on purpose — printing
# them for a human is the job — so this must read the code and only the code.
ARGV_LIST = Scanner(
    # The quote requirement is IN the pattern, not in a filter beside it. It started as
    # `\[([^\]]*?)\]` with an `if '"' in a` afterwards, and the meta-test refused it:
    # the scanner matched `sys.argv[1:]` and only the filter saved it. A scanner whose
    # name describes the filter rather than the pattern is a scanner that will be reused
    # somewhere the filter is not.
    name="python-argv-list",
    pattern=r"\[([^\]]*\"[^\]]*)\]",
    catches=('["git", "rev-parse"]', '["gcloud", "secrets", "list"]'),
    ignores=("sys.argv[1:]", "rows[0]"),
    fixture="offenders.py",
    language="py",
)


def source(code_only: bool = False) -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    return strip_comments(text, language="py") if code_only else text


def argv_literals() -> str:
    """Comments stripped first. The docstring and the inline notes in go_live.py name
    every forbidden command, so scanning raw source would fail the file for explaining
    itself — the same bug as a test grepping its own rationale, one level up."""
    return " ".join(ARGV_LIST.findall(source(code_only=True)))


def test_it_refuses_to_run_without_the_dry_run_flag():
    """The only safe default for a script whose name is go_live."""
    r = run()
    assert r.returncode != 0, "it ran"
    assert "--dry-run" in (r.stdout + r.stderr)


def test_it_cannot_build_an_argv_that_changes_anything():
    argvs = argv_literals()
    for parts in FORBIDDEN:
        assert not all(f'"{p}"' in argvs for p in parts), f"it can run: {' '.join(parts)}"


def test_it_never_reads_a_secret_value():
    """`gcloud secrets list` returns names. `versions access` returns the value, and
    that is never ours to read — not even to print a prefix of it."""
    assert "versions access" not in source(), "it can read a secret value"
    assert "--data-file" not in source()


def test_the_dry_run_reports_every_step_of_the_documented_procedure():
    """A preflight that silently checks a subset is the same failure as a gate that
    silently skips a job."""
    steps = re.findall(r"^\| (\d+b?) \|", GO_LIVE.read_text(encoding="utf-8"), re.M)
    assert len(steps) >= 12, f"only {len(steps)} steps found in GO-LIVE.md"
    out = run("--dry-run").stdout
    missing = [s for s in steps if not re.search(rf"^\s*{re.escape(s)}[ .)]", out, re.M)]
    assert not missing, f"steps absent from the preflight output: {missing}"


def test_the_dry_run_says_plainly_whether_go_live_is_blocked():
    out = run("--dry-run").stdout
    assert "GO-LIVE PREFLIGHT" in out
    assert "BLOCKED" in out or "READY" in out, "no verdict"


def test_a_failed_check_is_never_silent():
    """Every check prints a line whether it passed or not, for the same reason the CI
    mirror prints a coverage table: the gap must never be the quiet case."""
    out = run("--dry-run").stdout
    marks = len(re.findall(r"^\s*(?:ok|NO|\?\?) ", out, re.M))
    assert marks >= 8, f"only {marks} checks reported"


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
