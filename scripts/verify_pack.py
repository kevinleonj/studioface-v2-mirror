"""Verify every file against MANIFEST.sha256; detects a stale or altered folder."""

import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Files bootstrap.py rewrites on purpose, and build artifacts, are never part of the manifest.
MUTABLE = {"infra/versions.tf", "infra/terraform.tfvars", ".bootstrap-answers.json"}
bad = 0
with open(os.path.join(ROOT, "MANIFEST.sha256"), encoding="utf-8") as fh:
    lines = [ln.split("  ", 1) for ln in fh.read().splitlines() if ln.strip()]
for digest, rel in lines:
    if rel in MUTABLE or ".egg-info" in rel:
        continue
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        print(f"MISSING  {rel}")
        bad += 1
        continue
    with open(path, "rb") as fh:
        if hashlib.sha256(fh.read()).hexdigest() != digest:
            print(f"CHANGED  {rel}")
            bad += 1
print(f"MANIFEST OK: {len(lines)} files" if not bad else f"MANIFEST FAILED: {bad} problem(s)")
sys.exit(1 if bad else 0)
