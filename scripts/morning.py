"""Morning: what happened, what is live, what to click."""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _exec import resolve  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
print("== MORNING-REPORT.md")
if os.path.exists("MORNING-REPORT.md"):
    with open("MORNING-REPORT.md", encoding="utf-8") as fh:
        print(fh.read())
else:
    print("(not written: the run stopped early; read logs/overnight.err and HANDOFF.md)")
print("\n== last 3 CI/deploy runs")
subprocess.run(resolve(["gh", "run", "list", "--limit", "3"]))
print("\n== Cloud Run")
subprocess.run(
    resolve(
        [
            "gcloud",
            "run",
            "services",
            "describe",
            "studioface-api",
            "--region",
            "europe-west1",
            "--format",
            "value(status.url,status.latestReadyRevisionName)",
        ]
    )
)
print(
    "\n== rate limit acceptance: python scripts/verify_ratelimit.py https://api.<domain> <selfie>"
)
print("== Stripe to live: python scripts/set_secret.py stripe-secret-key   (prompts hidden)")
