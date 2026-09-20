"""PreToolUse on Bash|PowerShell. Second line of defence behind permissions.deny."""

import re
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0] if "/" in __file__ else __file__.rsplit("\\", 1)[0])
from _common import block, read_input  # noqa: E402

DENY = re.compile(
    r"gcloud run deploy|terraform (apply|destroy)|git push.*(--force|-f\b)|git reset --hard"
    r"|rm -rf|Remove-Item.*-Recurse|gcloud secrets versions add"
    r"|gcloud projects delete|firebase deploy"
)
cmd = read_input().get("tool_input", {}).get("command", "") or ""
if DENY.search(cmd):
    block(f"Blocked by hook: '{cmd}' is irreversible or owned by CI/bootstrap. CI deploys.")
sys.exit(0)
