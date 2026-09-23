"""What the workflow files must keep true. Parsed as text, deliberately.

Two different problems live here.

The first is money. Every job that can hang burns Actions minutes until GitHub's
six-hour default kills it, and a workflow with no concurrency group runs a job per
push. timeout-minutes and a concurrency group on every one of them is the standing
rule; three of the four jobs did not have a timeout.

The second is the one that made this file necessary. tests/test_counter_atomicity.py
skips itself unless FIRESTORE_EMULATOR_HOST is set, and nothing on a developer
machine sets it — which is correct, the emulator needs Java 21+. But a test that
skips in every environment passes forever while proving nothing, and the skip is a
green dot in the output. So the contract is pinned from this side: some job must
really set that variable and really run that file.

No yaml parser: pyyaml is not a dependency and adding one needs a reason and a yes.
The workflow files here are flat enough to read with a regex, and a parser would not
have caught the thing this file exists to catch anyway.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
EMULATOR_TEST = "tests/test_counter_atomicity.py"


def jobs(path: Path) -> dict[str, str]:
    """{job id: its block}, where a job id is a key at exactly two spaces under jobs:."""
    text = path.read_text(encoding="utf-8")
    body = text.split("\njobs:\n", 1)
    assert len(body) == 2, f"{path.name} has no jobs: block"
    found, current, lines = {}, None, []
    for line in body[1].splitlines():
        m = re.match(r"^  ([A-Za-z_][\w-]*):\s*$", line)
        if m:
            if current:
                found[current] = "\n".join(lines)
            current, lines = m.group(1), []
        elif current is not None:
            lines.append(line)
    if current:
        found[current] = "\n".join(lines)
    assert found, f"{path.name}: parsed no jobs"
    return found


@pytest.mark.mirror_incompatible(reason="reads .github/workflows, which the mirror does not carry")
def test_there_are_workflows_to_check():
    assert WORKFLOWS, "no workflow files found; every assertion below would pass vacuously"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_job_has_a_timeout(path):
    for name, block in jobs(path).items():
        assert re.search(r"^\s*timeout-minutes:\s*\d+", block, re.M), (
            f"{path.name}: job {name!r} has no timeout-minutes; it can hang for six hours"
        )


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_workflow_has_a_concurrency_group(path):
    assert re.search(r"^concurrency:", path.read_text(encoding="utf-8"), re.M), (
        f"{path.name}: no concurrency group, so every push runs its own copy"
    )


# ---------------------------------------------------------------- the skipped test


def emulator_jobs() -> list[tuple[str, str, str]]:
    return [
        (p.name, name, block)
        for p in WORKFLOWS
        for name, block in jobs(p).items()
        if EMULATOR_TEST in block
    ]


@pytest.mark.mirror_incompatible(reason="reads .github/workflows, which the mirror does not carry")
def test_some_job_actually_runs_the_emulator_test():
    """Without this, tests/test_counter_atomicity.py is five permanent skips."""
    assert emulator_jobs(), (
        f"no workflow job runs {EMULATOR_TEST}; it skips everywhere and proves nothing"
    )


def test_the_job_that_runs_it_sets_the_variable_that_un_skips_it():
    for file, name, block in emulator_jobs():
        assert "FIRESTORE_EMULATOR_HOST" in block, (
            f"{file}: job {name!r} runs {EMULATOR_TEST} without FIRESTORE_EMULATOR_HOST, "
            "so every case in it skips and the job passes green"
        )


def test_the_job_installs_the_emulator_and_picks_a_java_the_emulator_accepts():
    """Held-out check on the two facts that are easy to get wrong and only fail in CI:
    the component is not part of a plain gcloud install, and the emulator needs Java
    21+ while the ubuntu-latest default JAVA_HOME is 17 (docs/verified.md)."""
    for file, name, block in emulator_jobs():
        assert "cloud-firestore-emulator" in block, (
            f"{file}: job {name!r} never installs the cloud-firestore-emulator component"
        )
        assert "JAVA_HOME_21" in block, (
            f"{file}: job {name!r} leaves JAVA_HOME at the runner default of 17; "
            "the Firestore emulator requires Java 21 or newer"
        )
        # This assertion is the one that would have caught run 35241448581. The job
        # exported JAVA_HOME_21_X64 and still failed, because gcloud reads the `java`
        # on PATH: "The java executable on your PATH is not a Java 21+ JRE".
        assert re.search(r'PATH="\$JAVA_HOME/bin:\$PATH"', block), (
            f"{file}: job {name!r} sets JAVA_HOME but never puts that JDK's bin on PATH, "
            "and gcloud checks PATH, not JAVA_HOME"
        )


# ---------------------------------------------------------------- the design floor


@pytest.mark.mirror_incompatible(reason="reads .github/workflows, which the mirror does not carry")
def test_some_job_runs_the_design_audit_against_a_built_export():
    """The audit only means anything if it runs on a real build. Lighthouse scored the
    previous design 96 and Playwright passed on it; neither could see that it was
    Inter + Fraunces + cream. A job that forgets `npm run build` audits an empty
    directory, and the script treats that as an error rather than a pass — but only if
    a job actually invokes it."""
    jobs_running_it = [
        (p.name, name, block)
        for p in WORKFLOWS
        for name, block in jobs(p).items()
        if "design_audit.py" in block
    ]
    assert jobs_running_it, "no workflow job runs scripts/design_audit.py"
    for file, name, block in jobs_running_it:
        assert "npm run build" in block, (
            f"{file}: job {name!r} audits without building the export first"
        )


# ---------------------------------------------------------------- the browser

# A `run:` step, not a mention. self-heal.yml contains the words "python scripts/ci.py"
# inside the PROMPT it hands the healer, and a substring search would read that prose as
# a job that runs the gate and demand a browser install inside it. Treating rationale as
# if it were code is the bug class that bit four times on 17 Sep.
GATE_STEP = re.compile(r"^\s*- run:.*scripts/ci\.py", re.M)


def gate_jobs() -> list[tuple[str, str, str]]:
    """Jobs that run the whole pytest suite through the gate."""
    return [
        (p.name, name, block)
        for p in WORKFLOWS
        for name, block in jobs(p).items()
        if GATE_STEP.search(block)
    ]


@pytest.mark.mirror_incompatible(reason="reads .github/workflows, which the mirror does not carry")
def test_the_gate_step_is_found_by_reading_steps_and_not_prose():
    """Held-out check on the matcher. It must find the real gate jobs and must NOT find
    self-heal.yml, which talks about the gate without ever running it."""
    found = {(file, name) for file, name, _ in gate_jobs()}
    assert found, "matched no job running scripts/ci.py; the assertion below is vacuous"
    assert not [f for f, _ in found if f == "self-heal.yml"], (
        "matched self-heal.yml, which only MENTIONS the gate in its prompt text"
    )


def gate_step_names() -> list[str]:
    """The gate's own plan, imported rather than read as text. Asserting on the source
    string would pass on a step that is described in a comment and never run."""
    sys.path.insert(0, str(ROOT))
    from scripts.ci import steps  # noqa: PLC0415 - importing the thing under test

    return [s.name for s in steps() if "pytest" in s.argv or "playwright" in s.argv]


def test_the_gate_installs_a_browser_before_it_runs_the_suite():
    """Deploy run 35346406139 went red because `pip install -e ".[dev]"` installs the
    playwright PACKAGE and not the ~100 MB browser BINARY, so the real-browser cases in
    tests/test_verify_production.py died on "Executable doesn't exist".

    0ea9dd9 fixed that in deploy.yml and added a fixture that SKIPS on a laptop and
    FAILS when CI=true — the right shape, measured to work. But TWO jobs run this suite
    and only one was fixed. ci.yml's `ci` job, which GitHub also runs with CI=true, was
    left as it was. Measured on 0ea9dd9, in that job's exact environment:

        $ CI=true PLAYWRIGHT_BROWSERS_PATH=/nonexistent pytest tests/...
        6 errors                       <- every pull request, while main stayed green

    So the install belongs in the GATE, which every one of those jobs already runs,
    rather than copied into each job where it can be — and was — forgotten in one. That
    also means Kevin's box runs these cases instead of skipping them forever.

    Order matters and is the whole assertion: installing after pytest fixes nothing.
    """
    order = gate_step_names()
    assert "playwright browser" in order, (
        "the gate never installs a browser, so tests/test_verify_production.py either "
        "fails (CI=true) or skips (a laptop) and proves nothing in both cases"
    )
    assert order.index("playwright browser") < order.index("pytest"), (
        f"the gate installs the browser AFTER running the suite: {order}"
    )


def test_every_job_that_runs_the_suite_ends_up_with_a_browser():
    """The job-level half of the same invariant: a job either installs the browser
    itself or gets one from the gate it runs. It fails the day both disappear."""
    gate_covers = "playwright browser" in gate_step_names()
    for file, name, block in gate_jobs():
        assert gate_covers or "playwright install" in block, (
            f"{file}: job {name!r} runs the whole suite with no browser from either the "
            "job or the gate; tests/test_verify_production.py fails hard when CI=true"
        )


# ---------------------------------------------------------------- the healer


@pytest.mark.mirror_incompatible(reason="reads .github/workflows, which the mirror does not carry")
def test_the_healer_does_not_heal_a_commit_main_has_already_moved_past():
    """Observed on 2026-09-17: three self-heal runs fired against SHAs that main had
    already superseded, in a session that was actively pushing fixes. Each one checks
    out `main` — which already contained the fix — diagnoses a failure that no longer
    exists, and can push a commit over the top of the human's work. The guard is to
    compare the failed run's head_sha with the current tip of main and stop when they
    differ: the newer commit either fixed it or will fail on its own and trigger its
    own heal."""
    text = (ROOT / ".github" / "workflows" / "self-heal.yml").read_text(encoding="utf-8")
    assert "head_sha" in text, (
        "self-heal.yml never looks at the failed run's head_sha, so it heals stale "
        "commits and races whoever is pushing"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
