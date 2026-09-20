"""SessionStart: factual context (plain stdout becomes context on this event)."""

import os
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0] if "/" in __file__ else __file__.rsplit("\\", 1)[0])
from _common import project_dir, run  # noqa: E402

root = project_dir()
branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root).stdout.strip()
last = run(["git", "log", "-1", "--oneline"], root).stdout.strip()
print(f"Branch: {branch}. Last commit: {last}.")
h = os.path.join(root, "HANDOFF.md")
if os.path.exists(h):
    print("HANDOFF.md tail:")
    with open(h, encoding="utf-8") as fh:
        print("".join(fh.readlines()[-20:]))
print("HANDOFF.md follow-ups are the backlog. Deploy target: Cloud Run via CI on push to main.")
