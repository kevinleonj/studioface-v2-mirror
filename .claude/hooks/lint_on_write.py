"""PostToolUse on Edit|Write: format + lint the file; exit 2 with the error so Claude sees it."""

import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0] if "/" in __file__ else __file__.rsplit("\\", 1)[0])
from _common import block, project_dir, read_input, run  # noqa: E402

f = read_input().get("tool_input", {}).get("file_path", "") or ""
if not f.endswith(".py"):
    sys.exit(0)
root = project_dir()
run([sys.executable, "-m", "ruff", "format", "-q", f], root)
run([sys.executable, "-m", "ruff", "check", "-q", "--fix", f], root)
r = run([sys.executable, "-m", "ruff", "check", "-q", f], root)
if r.returncode != 0:
    block(f"ruff rejected {f} (complexity or lint). Fix before continuing.\n{r.stdout}{r.stderr}")
sys.exit(0)
