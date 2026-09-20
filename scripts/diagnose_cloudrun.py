"""Collect the real Cloud Run failure reason. Terraform only shows the generic "internal error".
Usage: .venv\\Scripts\\python.exe scripts\\diagnose_cloudrun.py
Read-only. Prints service conditions, revision conditions, the last 40 log lines, and runs one
isolation experiment: deploys the same placeholder image WITHOUT secrets as `probe-hello`.
If probe-hello turns Ready, the region/project can run containers and the secret references
are the problem; if it fails the same way, the project/service agent is the problem.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _exec import resolve  # noqa: E402

PROJECT = "studio-face-fresh-start"
REGION = "europe-west1"
SVC = "studioface-api"


def run(args: list[str]) -> None:
    print(f"\n$ {' '.join(args)}", flush=True)
    subprocess.run(resolve(args), check=False)


run(
    [
        "gcloud",
        "run",
        "services",
        "describe",
        SVC,
        "--region",
        REGION,
        "--project",
        PROJECT,
        "--format",
        "yaml(status.conditions,status.latestCreatedRevisionName,spec.template.spec.serviceAccountName)",
    ]
)
run(
    [
        "gcloud",
        "run",
        "revisions",
        "list",
        "--service",
        SVC,
        "--region",
        REGION,
        "--project",
        PROJECT,
        "--format",
        "table(name,status.conditions[0].type,status.conditions[0].status,status.conditions[0].message)",
    ]
)
run(
    [
        "gcloud",
        "logging",
        "read",
        f'resource.type="cloud_run_revision" AND resource.labels.service_name="{SVC}"',
        "--project",
        PROJECT,
        "--limit",
        "40",
        "--freshness",
        "1d",
        "--format",
        "value(timestamp,severity,textPayload,protoPayload.status.message,jsonPayload.message)",
    ]
)
run(
    [
        "gcloud",
        "projects",
        "get-iam-policy",
        PROJECT,
        "--flatten",
        "bindings[].members",
        "--filter",
        "bindings.members:serverless-robot OR bindings.members:sa-studioface-api",
        "--format",
        "table(bindings.role,bindings.members)",
    ]
)
run(
    [
        "gcloud",
        "run",
        "deploy",
        "probe-hello",
        "--image",
        "us-docker.pkg.dev/cloudrun/container/hello",
        "--region",
        REGION,
        "--project",
        PROJECT,
        "--no-allow-unauthenticated",
        "--quiet",
    ]
)
run(
    [
        "gcloud",
        "run",
        "services",
        "describe",
        "probe-hello",
        "--region",
        REGION,
        "--project",
        PROJECT,
        "--format",
        "yaml(status.conditions)",
    ]
)
print(
    "\nPaste everything above. Delete the probe afterwards with:\n"
    f"  gcloud run services delete probe-hello --region {REGION} --project {PROJECT} --quiet"
)
