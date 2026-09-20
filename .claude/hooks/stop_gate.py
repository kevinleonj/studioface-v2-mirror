"""Stop: refuse to stop while CI is red or changes are uncommitted (stop_hook_active: no loop)."""

import os
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0] if "/" in __file__ else __file__.rsplit("\\", 1)[0])
from _common import block, project_dir, read_input, run  # noqa: E402

data = read_input()
if data.get("stop_hook_active"):
    sys.exit(0)
root = project_dir()
ci = run([sys.executable, os.path.join(root, "scripts", "ci.py")], root)
if ci.returncode != 0:
    block("scripts/ci.py is red. Fix it before stopping.\n" + (ci.stdout + ci.stderr)[-2500:])
dirty = run(["git", "status", "--porcelain"], root).stdout.strip()
if dirty:
    block(
        "Uncommitted changes exist. Commit (one logical unit, named files) before stopping:\n"
        + dirty
    )
sys.exit(0)
