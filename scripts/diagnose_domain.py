"""Read-only: is studioface.app verified for the gcloud account, and what mappings exist?"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _exec import resolve  # noqa: E402

P, R = "studio-face-fresh-start", "europe-west1"


def run(args):
    print(f"\n$ {' '.join(args)}", flush=True)
    subprocess.run(resolve(args), check=False)


run(["gcloud", "config", "get-value", "account"])
run(["gcloud", "domains", "list-user-verified"])
run(["gcloud", "run", "domain-mappings", "list", "--region", R, "--project", P])
run(
    [
        "gcloud",
        "run",
        "domain-mappings",
        "describe",
        "api.studioface.app",
        "--region",
        R,
        "--project",
        P,
        "--format",
        "yaml(status.conditions,status.resourceRecords)",
    ]
)
run(
    [
        "gcloud",
        "run",
        "domain-mappings",
        "list",
        "--region",
        R,
        "--project",
        "silver-quest-489513-s3",
    ]
)
