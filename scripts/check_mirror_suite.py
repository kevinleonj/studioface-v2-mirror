r"""Prove the public mirror's suite ends at "0 failed", and that nothing hides here (task 94).

1. Builds the mirror into a temp folder with scripts/make_public_mirror.py (no push),
   makes a fresh venv there, installs ".[dev]", runs pytest exactly as RUN-ME-FIRST.md
   tells a reviewer to. Passes only on 0 failed and 0 errors.
2. Runs pytest in this private repository and fails if any test was skipped with a
   reason mentioning the mirror: here every mirror_incompatible test must run, so a skip
   like that means the marker leaked out of the mirror.

The temp folder is removed on exit, pass or fail. Usage:
    .venv\Scripts\python.exe scripts\check_mirror_suite.py
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = Path(".venv") / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
SUMMARY = re.compile(r"\b\d+ (passed|failed|skipped|errors?|deselected)\b|no tests ran")


def failures(output: str) -> int | None:
    """Failed plus errors from pytest's summary line; None when there is no summary,
    which counts as a failure: a run that printed nothing did not pass."""
    lines = [line for line in output.splitlines() if SUMMARY.search(line)]
    if not lines:
        return None
    last = lines[-1]
    return sum(int(n) for n in re.findall(r"(\d+) (?:failed|errors?)\b", last))


def mirror_skips(output: str) -> list[str]:
    """`-rs` lines whose reason mentions the mirror, in any case."""
    return [
        line
        for line in output.splitlines()
        if line.startswith("SKIPPED") and "mirror" in line.lower()
    ]


def run(argv: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    started = time.monotonic()
    done = subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    took = time.monotonic() - started
    print(f"  {' '.join(argv[1:4])} ... exit={done.returncode} took={took:.0f}s", flush=True)
    return done


def mirror_failures(workdir: Path) -> int | None:
    src = workdir / "mirror"
    build = run([sys.executable, "scripts/make_public_mirror.py", str(src)], ROOT, 300)
    if build.returncode not in (0, 3):
        print(build.stdout + build.stderr)
        return None
    run([sys.executable, "-m", "venv", ".venv"], src, 300)
    python = str(src / VENV_PYTHON)
    install = run(
        [python, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "-e", ".[dev]"],
        src,
        900,
    )
    if install.returncode != 0:
        print(install.stdout[-2000:] + install.stderr[-2000:])
        return None
    suite = run([python, "-m", "pytest", "-q", "-p", "no:cacheprovider"], src, 1800)
    print("  mirror:  " + (suite.stdout.strip().splitlines() or ["(no output)"])[-1])
    return failures(suite.stdout)


def private_mirror_skips() -> list[str] | None:
    suite = run([sys.executable, "-m", "pytest", "-q", "-rs", "-p", "no:cacheprovider"], ROOT, 1800)
    print("  private: " + (suite.stdout.strip().splitlines() or ["(no output)"])[-1])
    if failures(suite.stdout) is None:
        return None
    return mirror_skips(suite.stdout)


def _force(func, path, _exc) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="sf-mirror-suite-"))
    try:
        print("1. the mirror's own suite, as RUN-ME-FIRST.md runs it", flush=True)
        failed = mirror_failures(workdir)
        print("2. this private repository: no skip may mention the mirror", flush=True)
        leaked = private_mirror_skips()
    finally:
        shutil.rmtree(workdir, onexc=_force)
    if failed != 0:
        print(f"MIRROR SUITE: RED, failed+errors={failed} (None = no readable summary)")
        return 1
    if leaked is None or leaked:
        print(f"MIRROR SUITE: RED, private run skipped for the mirror: {leaked}")
        return 1
    print("MIRROR SUITE: GREEN, mirror 0 failed, private repository skips nothing for the mirror")
    return 0


if __name__ == "__main__":
    sys.exit(main())
