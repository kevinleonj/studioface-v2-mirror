"""Static checks on .github/workflows that catch the two failure modes we actually hit.

A. "No jobs were run": a workflow that TRIGGERS on a ref where every job is filtered out. GitHub
   records that run as a FAILURE. Forty-two of those arrived by email on 17 Sep 2026, all from
   ci.yml on main, none of them a real defect — but they make `gh run list` unreadable, which is
   how a real red run hides.
B. Pipeline drift: a `run:` step exists in a workflow with no local equivalent, so the local gate is
   not a mirror and "green locally" means nothing. Every workflow step must either be invoked by the
   local runner or be listed in CLOUD_ONLY with a reason.

Usage: python scripts/workflow_lint.py [--workflows .github/workflows] [--runner scripts/ci.py]
Exit 1 on any finding.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

# Steps that genuinely cannot run on a laptop. Keep this list short and give every entry a reason.
CLOUD_ONLY = {
    "google-github-actions/auth": "Workload Identity Federation needs the runner's OIDC token",
    "google-github-actions/setup-gcloud": "installs gcloud on the runner",
    "hashicorp/setup-terraform": "installs terraform on the runner",
    "actions/checkout": "runner-side checkout",
    "actions/setup-python": "runner-side python",
    "terraform -chdir=infra apply": "GitOps: only CI applies infra",
    "terraform -chdir=infra init": "uses the CI backend credentials",
    "gcloud run deploy": "GitOps: only CI deploys",
    "gcloud auth configure-docker": "runner-side docker auth",
    "docker push": "pushes to Artifact Registry with the runner's identity",
    "actions/setup-node": "runner-side node",
    "anthropics/claude-code-action": "runs Claude inside the runner",
    'pip install -e ".[dev]"': "the local venv is already installed; bootstrap.py owns that",
    # Fetching a browser binary is setup, not a check. The CHECK it enables —
    # tests/test_verify_production.py — runs locally under pytest and is mirrored, and
    # it fails rather than skips on CI, so a runner without the browser goes red.
    "playwright install": "downloads the browser the mirrored pytest step already has locally",
}

# Whole jobs that cannot run on a laptop at all. Exempting these step by step would
# mean listing every line of their shell, which is how an exemption list stops being
# read. Each entry states the reason and the reason is printed.
CLOUD_ONLY_JOBS = {
    "emulator": "needs a JRE 21+ this machine does not have",
    "infra": "terraform apply is CI's alone (GitOps), on the runner's backend credentials",
    "deploy": "pushes the image and deploys to Cloud Run with the runner's identity",
    "heal": "runs anthropics/claude-code-action inside the runner",
    # The canary's whole point is that it runs from OUTSIDE against the deployed public
    # hostname. There is nothing to mirror locally: a local copy would be checking a
    # localhost export, which is precisely the blind spot that let three outages ship.
    "verify": "checks the deployed public hostname from outside; there is no local equivalent",
}


class Unparseable(Exception):
    """The workflow is not valid YAML, which GitHub reports as nothing at all."""


def load(path: Path) -> dict:
    """Parse, or raise Unparseable with the reason on one line.

    This used to let PyYAML's exception escape, and the tool died on the exact file it
    exists to catch: ci.yml carried
    `concurrency: { group: ci-${{ github.ref }}, cancel-in-progress: true }`, and a
    plain scalar in a YAML flow mapping may not contain `{`. GitHub's response to an
    unparseable workflow is to run zero jobs, record a FAILURE, and not apply the
    branch filters either — which is how a workflow with `branches-ignore: [main]`
    failed on main 35 times in a day.

    A crash in a gate is indistinguishable from the gate being broken, and gates that
    look broken get switched off. So this is a finding, not a traceback.
    """
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        detail = " ".join(str(e).split())
        raise Unparseable(detail) from e


def triggers_on_main(wf: dict) -> bool:
    on = wf.get("on") or wf.get(True) or {}  # PyYAML parses bare `on:` as the boolean True
    if isinstance(on, str):
        on = {on: None}
    if isinstance(on, list):
        on = dict.fromkeys(on)
    push = on.get("push")
    if push is None:
        return False
    if not isinstance(push, dict):
        return True  # `on: push` with no filter fires on every branch, main included
    branches = push.get("branches")
    ignore = push.get("branches-ignore")
    if ignore and any(b in ("main", "master", "**") for b in ignore):
        return False
    if branches is None:
        return True
    return any(b in ("main", "master", "**") for b in branches)


def job_can_run_on_main(job: dict) -> bool:
    cond = str(job.get("if", "")).strip()
    if not cond:
        return True
    # A condition that excludes main is the whole bug: the workflow fires and every
    # job is filtered out.
    excludes_main = re.search(r"github\.ref\s*!=\s*'refs/heads/(main|master)'", cond) or re.search(
        r"github\.ref_name\s*!=\s*'(main|master)'", cond
    )
    return not excludes_main


def steps_of(wf: dict) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for jname, job in (wf.get("jobs") or {}).items():
        for step in job.get("steps") or []:
            if "uses" in step:
                out.append((jname, str(step["uses"]).split("@")[0]))
            if "run" in step:
                for line in commands(str(step["run"])):
                    out.append((jname, line))
    return out


def commands(script: str) -> list[str]:
    """Split a `run:` block into commands, joining backslash continuations.

    Splitting per physical line turned

        gcloud run deploy api --image "$IMAGE" \\
          --region europe-west1 --quiet

    into two "steps", the second a bare flag list matching nothing and reported as
    unmirrored. Eight of the first twenty-nine findings against our own workflows were
    continuation lines rather than real drift, and a checker that cries wolf eight
    times out of twenty-nine is one people stop reading.
    """
    joined: list[str] = []
    buffer = ""
    for raw in script.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            buffer += line[:-1].rstrip() + " "
            continue
        joined.append((buffer + line).strip())
        buffer = ""
    if buffer:
        joined.append(buffer.strip())
    return joined


def mirrored(step: str, runner_src: str) -> bool:
    if any(step.startswith(k) or k in step for k in CLOUD_ONLY):
        return True
    token = step.split()[0] if step.split() else step
    if token in {"printf", "echo", "URL=$(gcloud", "curl", "npx", "n=$(git"}:
        return True  # shell plumbing and smoke probes, not build logic
    for key in (
        "scripts/ci.py",
        "design_audit.py",
        "workflow_lint.py",
        "pytest",
        "ruff",
        "npm ci",
        "npm run build",
        "docker build",
    ):
        if key in step and key in runner_src:
            return True
    return False


def check(p: Path, runner_src: str) -> list[str]:
    """Every finding for one workflow file."""
    try:
        wf = load(p)
    except Unparseable as e:
        return [
            f"{p.name}: could not be parsed as YAML, so GitHub runs NO jobs, records a "
            f"FAILURE and ignores the branch filters -> {e}"
        ]
    found: list[str] = []
    jobs = wf.get("jobs") or {}
    if not jobs:
        found.append(f"{p.name}: no jobs at all - every run is recorded as a failure")
    elif triggers_on_main(wf) and not any(job_can_run_on_main(j) for j in jobs.values()):
        found.append(
            f"{p.name}: fires on push to main but every job is filtered out "
            f"-> GitHub reports 'No jobs were run' as a FAILURE on every push"
        )
    exempt: set[str] = set()
    for jname, step in steps_of(wf):
        if jname in CLOUD_ONLY_JOBS:
            if jname not in exempt:
                exempt.add(jname)
                print(f"WORKFLOW LINT: {p.name}:{jname}: cloud-only — {CLOUD_ONLY_JOBS[jname]}")
            continue
        if not mirrored(step, runner_src):
            found.append(f"{p.name}:{jname}: step has no local mirror -> {step[:90]}")
    return found


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflows", default=".github/workflows")
    ap.add_argument("--runner", default="scripts/ci.py")
    ns = ap.parse_args()
    runner_src = Path(ns.runner).read_text(encoding="utf-8") if Path(ns.runner).exists() else ""
    findings: list[str] = []

    root = Path(ns.workflows)
    for p in sorted(root.glob("*.yml")) + sorted(root.glob("*.yaml")):
        findings += check(p, runner_src)

    for f in findings:
        print("WORKFLOW LINT: " + f)
    if findings:
        print(f"\nFAIL: {len(findings)} finding(s).")
        sys.exit(1)
    print("WORKFLOW LINT: ok (every workflow can run, every step is mirrored or cloud-only)")


if __name__ == "__main__":
    main()
