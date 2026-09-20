"""Run work/queue/*.md one task at a time, each in a fresh Claude Code process.

The loop, the order and the meaning of "done" are code, not model judgment:
a task is done only when its own check command exits 0. A task that is already
green is skipped. A task still red after MAX_ATTEMPTS stops the whole run.
"""

from __future__ import annotations

import datetime
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "work" / "queue"
DONE = ROOT / "work" / "done"
LOG = ROOT / "work" / "run.log"
MAX_ATTEMPTS = 2
CHECK_PATTERN = re.compile(r"^check:\s*(.+)$", re.MULTILINE)
PREAMBLE = (
    "Do exactly the one task below and nothing else. Read CLAUDE.md first. "
    "Failing test first. Do not ask questions. Stop when the check command passes.\n\n"
)


def log(message: str) -> None:
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {message}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def check_passes(command: str) -> bool:
    return subprocess.run(command, shell=True, cwd=ROOT).returncode == 0


def run_agent(task_text: str) -> int:
    executable = shutil.which("claude")
    if executable is None:
        log("STOP claude not found on PATH")
        return 127
    argv = [executable, "-p", PREAMBLE + task_text, "--permission-mode", "auto"]
    return subprocess.run(argv, cwd=ROOT).returncode


def run_task(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    match = CHECK_PATTERN.search(text)
    if match is None:
        log(f"STOP {path.name} has no 'check:' line")
        return False
    command = match.group(1).strip()
    if check_passes(command):
        log(f"SKIP {path.name} already green")
        return True
    for attempt in range(1, MAX_ATTEMPTS + 1):
        log(f"RUN  {path.name} attempt {attempt}")
        run_agent(text)
        if check_passes(command):
            log(f"DONE {path.name}")
            return True
    log(f"STOP {path.name} still red after {MAX_ATTEMPTS} attempts")
    return False


def main() -> int:
    DONE.mkdir(parents=True, exist_ok=True)
    for path in sorted(QUEUE.glob("*.md")):
        if not run_task(path):
            return 1
        path.rename(DONE / path.name)
    log("ALL TASKS GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
