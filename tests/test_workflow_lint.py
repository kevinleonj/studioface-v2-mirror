"""The linter must catch the two things that actually bit us, and stay quiet otherwise."""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
# The linter lives in scripts/, not beside this file, and the fixtures are under
# fixtures/workflows/. The delivered version looked for both as siblings of itself and
# exited 2 (file not found) on every case, which reads as a failure but is not one.
LINT = Path(__file__).resolve().parents[1] / "scripts" / "workflow_lint.py"


def run(folder: str) -> tuple[int, str]:
    r = subprocess.run(
        [
            sys.executable,
            str(LINT),
            "--workflows",
            str(HERE / folder),
            "--runner",
            str(HERE / "fake_runner.py"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return r.returncode, r.stdout


def test_workflow_that_filters_every_job_on_main_is_a_finding():
    """The 42-email bug: ci.yml fires on main, its only job excludes main, and
    GitHub records that as a failure."""
    code, out = run("fixtures/workflows/bad")
    assert code == 1
    assert "No jobs were run" in out


def test_an_unparseable_workflow_is_a_finding_not_a_traceback(tmp_path):
    """The real ci.yml was invalid YAML for a day and this linter died on it.

    `concurrency: { group: ci-${{ github.ref }}, cancel-in-progress: true }` is a flow
    mapping, and a plain scalar in flow context may not contain `{`. PyYAML says
    "expected ',' or '}', but got '{'". GitHub says nothing at all: it cannot parse the
    file, so it runs zero jobs, records a FAILURE, and does not apply the branch filter
    either — which is why a workflow with `branches-ignore: [main]` fired on main 35
    times.

    An unparseable workflow is the single most important thing this tool can find. It
    has to be reported as a finding, because a crash in a gate is indistinguishable
    from the gate being broken and gets switched off."""
    wf = tmp_path / "wf"
    wf.mkdir()
    (wf / "broken.yml").write_text(
        "name: x\non:\n  push:\n"
        "concurrency: { group: ci-${{ github.ref }}, cancel-in-progress: true }\n"
        "jobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        [
            sys.executable,
            str(LINT),
            "--workflows",
            str(wf),
            "--runner",
            str(HERE / "fake_runner.py"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "Traceback" not in r.stderr, r.stderr[-400:]
    assert r.returncode == 1
    assert "could not be parsed" in r.stdout


def test_a_backslash_continuation_is_one_command_not_several(tmp_path):
    """Real noise from our own deploy.yml. A multi-line `run:` split per physical line
    turns

        gcloud run deploy x --image "$IMAGE" \\
          --region eu --quiet

    into two "steps", the second of which is a bare flag list that matches nothing and
    is reported as unmirrored. Eight of the first 29 findings were continuation lines."""
    wf = tmp_path / "wf"
    wf.mkdir()
    (wf / "x.yml").write_text(
        "name: x\non:\n  push:\n    branches: [main]\njobs:\n  a:\n    runs-on: ubuntu-latest\n"
        '    steps:\n      - run: |\n          gcloud run deploy api --image "$IMAGE" \\\n'
        "            --region europe-west1 --quiet\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        [
            sys.executable,
            str(LINT),
            "--workflows",
            str(wf),
            "--runner",
            str(HERE / "fake_runner.py"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "--region" not in r.stdout, f"a continuation was treated as its own step:\n{r.stdout}"
    assert r.returncode == 0, r.stdout


def test_a_whole_job_can_be_declared_cloud_only_with_a_reason(tmp_path):
    """Some jobs cannot run on a laptop at all — the Firestore emulator needs a JRE 21+
    this machine does not have, terraform apply is CI's alone, and the healer runs
    claude-code-action inside the runner. Exempting them step by step would mean
    listing every line of their shell; the exemption belongs at the job."""
    wf = tmp_path / "wf"
    wf.mkdir()
    (wf / "x.yml").write_text(
        "name: x\non:\n  push:\n    branches: [main]\njobs:\n  emulator:\n"
        "    runs-on: ubuntu-latest\n    steps:\n      - run: java -version\n"
        "      - run: some-thing-only-a-runner-has\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        [
            sys.executable,
            str(LINT),
            "--workflows",
            str(wf),
            "--runner",
            str(HERE / "fake_runner.py"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stdout
    assert "JRE 21" in r.stdout, "a cloud-only job must still state its reason out loud"


def test_healthy_pipeline_passes():
    code, out = run("fixtures/workflows/good")
    assert code == 0, out


def test_unmirrored_step_is_a_finding(tmp_path):
    wf = tmp_path / "wf"
    wf.mkdir()
    (wf / "x.yml").write_text(
        "name: x\non:\n  push:\n    branches: [main]\njobs:\n  a:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: npm run build:special\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        [
            sys.executable,
            str(LINT),
            "--workflows",
            str(wf),
            "--runner",
            str(HERE / "fake_runner.py"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 1
    assert "no local mirror" in r.stdout


def test_empty_workflow_is_a_finding(tmp_path):
    wf = tmp_path / "wf"
    wf.mkdir()
    (wf / "empty.yml").write_text(
        "name: empty\non:\n  push:\n    branches: [main]\njobs: {}\n", encoding="utf-8"
    )
    r = subprocess.run(
        [
            sys.executable,
            str(LINT),
            "--workflows",
            str(wf),
            "--runner",
            str(HERE / "fake_runner.py"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 1
    assert "no jobs at all" in r.stdout
