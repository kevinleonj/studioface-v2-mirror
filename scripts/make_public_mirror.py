"""Build a public, history-free snapshot of this repository that is safe to publish.

Copies only files git tracks, drops risky paths, and redacts order identifiers, gallery
tokens and anything secret-shaped. No git history is copied, so nothing from old commits
can leak. Exit 0 = nothing secret-shaped was found. Exit 3 = something was found and
redacted: the snapshot is still safe, but the original file holds a value to rotate. Usage:
    python scripts/make_public_mirror.py <empty target directory>
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DROP_PATTERNS = (".env", ".tfstate", ".tfvars", "bootstrap.config.json", ".pem", ".p12", ".key")
DROP_DIRECTORIES = (".claude/state/", "work/", "frontend/out/", "docs/ui/2026-09-19/current/")
BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".heic",
    ".ico",
    ".woff",
    ".woff2",
    ".pdf",
    ".zip",
}
REDACTIONS = (
    (re.compile(r"cs_(test|live)_[A-Za-z0-9]{12,}"), r"cs_\1_REDACTED"),
    (re.compile(r"([?&]t=)[0-9a-f]{32}"), r"\1REDACTED"),
    (re.compile(r"pi_[A-Za-z0-9]{16,}"), "pi_REDACTED"),
    (re.compile(r"evt_[A-Za-z0-9]{16,}"), "evt_REDACTED"),
)
FORBIDDEN = {
    "Stripe secret key": re.compile(r"\b[sr]k_(test|live)_[A-Za-z0-9]{16,}"),
    "Stripe webhook secret": re.compile(r"\bwhsec_[A-Za-z0-9]{16,}"),
    "Resend key": re.compile(r"\bre_[A-Za-z0-9]{8,}_[A-Za-z0-9]{16,}"),
    "fal key": re.compile(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:[0-9a-f]{32}\b"
    ),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "Cloudflare token assignment": re.compile(
        r"(?i)cloudflare[_a-z]*token\s*[=:]\s*[\"'][A-Za-z0-9_-]{30,}"
    ),
}


def tracked_files() -> list[str]:
    output = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
    return [name for name in output.stdout.decode("utf-8").split("\0") if name]


def is_dropped(name: str) -> bool:
    lowered = name.lower()
    in_dropped_directory = any(lowered.startswith(prefix) for prefix in DROP_DIRECTORIES)
    return in_dropped_directory or any(pattern in lowered for pattern in DROP_PATTERNS)


def redact(text: str) -> str:
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def copy_file(name: str, target: Path) -> list[str]:
    source = ROOT / name
    destination = target / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() in BINARY_SUFFIXES:
        destination.write_bytes(source.read_bytes())
        return []
    text = redact(source.read_text(encoding="utf-8", errors="replace"))
    findings = []
    for label, pattern in FORBIDDEN.items():
        text, count = pattern.subn(f"<{label} REDACTED>", text)
        findings += [f"{name}: {label} x{count}"] * bool(count)
    destination.write_text(text, encoding="utf-8")
    return findings


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: make_public_mirror.py <empty target directory>")
        return 2
    target = Path(argv[1]).resolve()
    if target.exists() and any(target.iterdir()):
        print(f"REFUSED: {target} is not empty")
        return 2
    names = [name for name in tracked_files() if not is_dropped(name)]
    findings = [finding for name in names for finding in copy_file(name, target)]
    print(f"copied {len(names)} files to {target}")
    for finding in findings:
        print("REDACTED, ROTATE THE ORIGINAL IF REAL:", finding)
    print("SAFE, WITH REDACTIONS" if findings else "CLEAN")
    return 3 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
