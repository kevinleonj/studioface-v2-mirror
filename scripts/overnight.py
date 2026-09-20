"""Unattended build. Flags verified against code.claude.com/docs/en/cli-reference (2026-09-16)."""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _exec import resolve  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
os.makedirs("logs", exist_ok=True)
os.makedirs(os.path.join("docs", "screens"), exist_ok=True)
if subprocess.run(resolve(["claude", "auth", "status"]), capture_output=True).returncode != 0:
    sys.exit("Claude Code is not logged in. Run: claude auth login")
with open("GOAL.md", encoding="utf-8") as fh:
    goal = fh.read()
env = dict(os.environ, CLAUDE_CODE_SUBAGENT_MODEL="sonnet")
cmd = resolve(
    [
        "claude",
        "-p",
        goal,
        "--name",
        "overnight-studioface",
        "--permission-mode",
        "auto",
        "--permission-prompts",
        "none",
        "--model",
        "opus",
        "--effort",
        "high",
        "--max-turns",
        "600",
        "--output-format",
        "stream-json",
        "--verbose",
    ]
)
if sys.platform == "darwin":
    cmd = resolve(["caffeinate", "-i"]) + cmd
with (
    open("logs/overnight.jsonl", "w", encoding="utf-8") as out,
    open("logs/overnight.err", "w", encoding="utf-8") as err,
):
    rc = subprocess.run(cmd, stdout=out, stderr=err, env=env, shell=False).returncode
print(f"claude exited {rc}. Logs in logs/. Next: python scripts/morning.py")
