"""Shared helpers for hooks. Python only: same file runs on Windows and macOS. No bash, no jq."""

import json
import os
import subprocess
import sys


def read_input() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def project_dir() -> str:
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def block(msg: str) -> None:
    """Exit 2 = blocking error; Claude sees stderr (hooks reference, exit-code table)."""
    print(msg, file=sys.stderr)
    sys.exit(2)


def run(args: list[str], cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)
