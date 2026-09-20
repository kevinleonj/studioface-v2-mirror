"""CI Mirror Gate. Green here must mean green there, and it says so job by job.

The gate used to run ruff and pytest and call itself a mirror of CI. It was not: CI
also builds the frontend, audits that build, builds the image, and runs a workflow
linter. "Green locally" therefore meant "the cheap half of CI passed", which is how a
design regression and an unparseable workflow both reached main.

Every CI job now reports as mirrored, partially mirrored, or cloud-only WITH A REASON.
No silent subsets: if something cannot run on this machine it is named, every run.

Slow steps are skipped when their inputs have not changed since the last green run,
and the skip is printed. A gate nobody waits for is a gate nobody runs.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, ".claude", "state")
EXPORT = os.path.join(ROOT, "frontend", "out")
FRONTEND = os.path.join(ROOT, "frontend")
FRONTEND_SRC = os.path.join(FRONTEND, "src")
INPUTS = os.path.join(STATE, "gate_inputs.json")

# Jobs in .github/workflows that cannot run here, each with the reason. Printed every
# run so the gap is visible rather than remembered.
CLOUD_ONLY_JOBS = {
    "emulator": "needs a JRE 21+ this machine does not have",
    "infra": "terraform apply is CI's alone (GitOps), using the runner's backend credentials",
    "heal": "runs anthropics/claude-code-action inside the runner",
    "verify": "the canary checks the deployed hostname from outside; nothing to mirror here",
}


# The workflow commands this gate claims to reproduce, written as they appear in
# .github/workflows so scripts/workflow_lint.py can match on a stated contract rather
# than on whatever text happens to be in this file. Adding a step to CI without adding
# it here makes the linter fail, which is the point.
MIRRORS = (
    "python scripts/ci.py",
    "ruff check .",
    "pytest",
    "npm ci",
    "npm run build",
    "python scripts/design_audit.py frontend/out",
    "python scripts/workflow_lint.py",
    "python -m playwright install",
    'docker build -t "$IMAGE" .',
)


@dataclass
class Step:
    name: str
    job: str
    argv: list[str]
    cwd: str = ROOT
    watch: tuple[str, ...] = ()  # when unchanged since the last green run, skip
    needs: str = ""  # executable that must exist, else the step is cloud-only
    note: str = ""
    skipped: str = field(default="", init=False)


def npm() -> list[str]:
    """npm is a .cmd on Windows and CreateProcess does not search PATHEXT."""
    found = shutil.which("npm")
    return [found] if found else ["npm"]


def steps() -> list[Step]:
    py = sys.executable
    return [
        Step("ruff check", "ci", [py, "-m", "ruff", "check", "."]),
        Step("ruff format", "ci", [py, "-m", "ruff", "format", "--check", "."]),
        # Before pytest, and HERE rather than in each workflow job, because the browser
        # was installed in deploy.yml's job and missed in ci.yml's — two jobs run this
        # suite and a step repeated per job is a step that gets forgotten in one. The
        # gate is the single place every job already goes through.
        #
        # No --with-deps: that half is apt-get as root, and this also runs on Kevin's
        # Windows box. Measured on the ubuntu-latest image: a plain `playwright install
        # chromium` launches fine, so the OS libraries are already there.
        Step("playwright browser", "ci", [py, "-m", "playwright", "install", "chromium"]),
        Step("pytest", "ci", [py, "-m", "pytest", "-q"]),
        Step("workflow lint", "ci", [py, os.path.join(ROOT, "scripts", "workflow_lint.py")]),
        Step(
            "npm ci",
            "design",
            npm() + ["ci"],
            cwd=FRONTEND,
            watch=(os.path.join(FRONTEND, "package-lock.json"),),
            needs="npm",
        ),
        Step(
            "frontend build",
            "design",
            npm() + ["run", "build"],
            cwd=FRONTEND,
            watch=(FRONTEND_SRC, os.path.join(FRONTEND, "public")),
            needs="npm",
        ),
        Step(
            "design audit",
            "design",
            [py, os.path.join(ROOT, "scripts", "design_audit.py"), EXPORT],
        ),
        Step(
            "docker build",
            "deploy",
            ["docker", "build", "-t", "studioface-api:gate", "."],
            watch=(os.path.join(ROOT, "app"), os.path.join(ROOT, "Dockerfile")),
            needs="docker",
            note="the push and `gcloud run deploy` beside it stay cloud-only",
        ),
    ]


# ---------------------------------------------------------------- change detection


def _digest(path: str) -> str:
    h = hashlib.sha256()
    if os.path.isfile(path):
        with open(path, "rb") as fh:
            h.update(fh.read())
        return h.hexdigest()
    for base, _, names in os.walk(path):
        for name in sorted(names):
            full = os.path.join(base, name)
            h.update(os.path.relpath(full, ROOT).encode())
            try:
                with open(full, "rb") as fh:
                    h.update(fh.read())
            except OSError:
                continue
    return h.hexdigest()


def fingerprint(step: Step) -> str:
    return hashlib.sha256("".join(_digest(p) for p in step.watch).encode()).hexdigest()


def load_inputs() -> dict:
    try:
        with open(INPUTS, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


# ---------------------------------------------------------------- freshness


def _extremes(directory: str, skip_mirrored_in: str = "") -> tuple[float | None, float | None, str]:
    """(oldest mtime, newest mtime, path of the oldest) over every file in a tree.

    `skip_mirrored_in` excludes files that exist at the same relative path in another
    directory. Next copies frontend/public verbatim into the export and PRESERVES the
    original mtime, so public/file.svg arrives stamped hours before the build. Those
    are copies, not build output: counting them made every build look stale.
    """
    oldest = newest = None
    oldest_path = ""
    for base, _, names in os.walk(directory):
        for name in names:
            path = os.path.join(base, name)
            if skip_mirrored_in:
                rel = os.path.relpath(path, directory)
                if os.path.exists(os.path.join(skip_mirrored_in, rel)):
                    continue
            try:
                when = os.stat(path).st_mtime
            except OSError:
                continue
            if oldest is None or when < oldest:
                oldest, oldest_path = when, path
            if newest is None or when > newest:
                newest = when
    return oldest, newest, oldest_path


def stale_export(src_dir: str, out_dir: str) -> str | None:
    """Reason the export cannot be trusted, or None.

    Oldest-to-newest on purpose: a build that wrote one route and left the rest behind
    still has a fresh newest file, and that is the shape of the EBUSY failure this
    exists to catch — a server held frontend/out, the build could not replace it, and
    the gate audited the previous export and went green.
    """
    public = os.path.join(os.path.dirname(src_dir), "public")
    _, newest_src, _ = _extremes(src_dir)
    oldest_out, _, oldest_path = _extremes(out_dir, skip_mirrored_in=public)
    if newest_src is None or oldest_out is None:
        return None
    if oldest_out >= newest_src:
        return None
    return (
        f"{os.path.relpath(oldest_path, ROOT)} predates the newest file in "
        f"{os.path.relpath(src_dir, ROOT)} by {newest_src - oldest_out:.0f}s — "
        "the export is stale; run `npm run build` in frontend/"
    )


def record_run(state_dir: str, now: float | None = None) -> None:
    """Both markers. ci_mirror_ok is judged by mtime by the user-level guard_bash;
    last_test_run holds a timestamp and is read by the Stop hook. Writing only the
    first left the Stop hook unsatisfiable by the one command this project mandates."""
    os.makedirs(state_dir, exist_ok=True)
    open(os.path.join(state_dir, "ci_mirror_ok"), "w").close()
    with open(os.path.join(state_dir, "last_test_run"), "w") as fh:
        fh.write(str(time.time() if now is None else now))


# ---------------------------------------------------------------- reporting


def report(plan: list[Step]) -> None:
    """One line per CI job. The whole point is that the gap is never silent."""
    print("\nCI JOB COVERAGE")
    by_job: dict[str, list[Step]] = {}
    for s in plan:
        by_job.setdefault(s.job, []).append(s)
    for job, owned in by_job.items():
        missing = [s for s in owned if s.skipped.startswith("cloud-only")]
        names = ", ".join(s.name for s in owned if not s.skipped.startswith("cloud-only"))
        if missing:
            why = "; ".join(f"{s.name} ({s.skipped[11:]})" for s in missing)
            print(f"  {job:<10} PARTIAL   ran: {names or 'nothing'} | not here: {why}")
        else:
            extra = next((s.note for s in owned if s.note), "")
            print(f"  {job:<10} mirrored  {names}" + (f" | {extra}" if extra else ""))
    for job, reason in CLOUD_ONLY_JOBS.items():
        print(f"  {job:<10} CLOUD-ONLY {reason}")


def run_step(step: Step, previous: dict, fresh: dict) -> bool:
    if step.needs and shutil.which(step.needs) is None:
        step.skipped = f"cloud-only: {step.needs} is not installed on this machine"
        print(f"SKIP {step.name}: {step.needs} is not on PATH")
        return True
    if step.watch:
        fresh[step.name] = fingerprint(step)
        if previous.get(step.name) == fresh[step.name]:
            step.skipped = "unchanged"
            print(f"SKIP {step.name}: inputs unchanged since the last green run")
            return True
    started = time.time()
    code = subprocess.run(step.argv, cwd=step.cwd).returncode
    print(f"  ({step.name}: {time.time() - started:.1f}s)")
    return code == 0


def main() -> None:
    began = time.time()
    # The plan is NOT filtered here. It used to drop the design audit when frontend/out
    # was missing — decided before the build step that creates frontend/out had run, so
    # on a clean clone the audit vanished and the coverage report still said the design
    # job was mirrored. Whether it can run is a RUN-time question, answered below and
    # printed either way.
    plan = steps()
    previous, fresh = load_inputs(), {}
    for step in plan:
        if step.name == "design audit":
            if not os.path.isdir(EXPORT):
                step.skipped = "cloud-only: no frontend/out — the build step did not run"
                print("SKIP design audit: no frontend/out (the build step did not run)")
                continue
            reason = stale_export(FRONTEND_SRC, EXPORT)
            if reason:
                print(f"CI MIRROR GATE: red at: stale export — {reason}")
                sys.exit(1)
        if not run_step(step, previous, fresh):
            print(f"CI MIRROR GATE: red at: {step.name}")
            sys.exit(1)
    os.makedirs(STATE, exist_ok=True)
    with open(INPUTS, "w", encoding="utf-8") as fh:
        json.dump({**previous, **fresh}, fh)
    record_run(STATE)
    report(plan)
    print(f"\nCI MIRROR GATE: green in {time.time() - began:.0f}s")


if __name__ == "__main__":
    main()
