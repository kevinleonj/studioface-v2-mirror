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
# .github/ is dropped here rather than deleted by hand after the build (task 94): pushing
# workflow files needs a token scope the mirror does not have, and a check that rebuilds
# the mirror must build exactly what gets published.
DROP_DIRECTORIES = (
    ".claude/state/",
    "work/",
    "frontend/out/",
    "docs/ui/2026-09-19/current/",
    ".github/",
)
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
# Split so this file's own source — which is itself copied into the public mirror,
# since it is a tracked script and no DROP rule excludes it — never carries the
# address as one readable substring. Concatenated at import time, so the pattern still
# matches the real address wherever it appears in other files.
_OWNER_EMAIL = "kevinleon" + "jouvin" + "@gmail.com"

REDACTIONS = (
    (re.compile(r"cs_(test|live)_[A-Za-z0-9]{12,}"), r"cs_\1_REDACTED"),
    (re.compile(r"([?&]t=)[0-9a-f]{32}"), r"\1REDACTED"),
    (re.compile(r"pi_[A-Za-z0-9]{16,}"), "pi_REDACTED"),
    (re.compile(r"evt_[A-Za-z0-9]{16,}"), "evt_REDACTED"),
    # The owner's own address, not a secret — it belongs in the private repository and
    # is expected to appear in ordinary docs and test fixtures. Quiet substitution, same
    # tier as the order ids above; must never move to FORBIDDEN, which is for
    # secret-shaped values and would make this exit 3 and cry "rotate" every time. No
    # \b here: it sits right after a literal backslash-n inside a string literal in one
    # fixture, and "n" before "k" is not a word boundary.
    (re.compile(re.escape(_OWNER_EMAIL)), "OWNER_EMAIL_REDACTED"),
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


RUN_ME_FIRST = r"""# Run me first

This is a public, history-free mirror of a private repository. MIRROR.txt names the
source commit it was built from.

    python -m venv .venv
    .venv\Scripts\activate          (Windows)
    source .venv/bin/activate         (macOS, Linux)
    pip install -e ".[dev]"
    pytest -q

Expected: "0 failed".

The tests listed in tests/mirror_incompatible.txt are skipped here, each with its reason.
They cannot pass in this copy because of how it is built: they read .github/, which the
mirror does not carry; they use values the mirror redacts (Stripe test session ids, the
owner's address); or they need git settings a fresh clone does not have. They run in the
private repository on every push.
"""


def source_commit() -> str:
    """The commit the files came from, marked -dirty when tracked files differ from it:
    the build copies the working tree, so a clean hash on a dirty tree would lie."""
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return f"{head}-dirty" if dirty else head


def write_notes(target: Path, commit: str) -> None:
    """MIRROR.txt is also what tests/conftest.py looks for: its presence is the one signal
    that turns the mirror_incompatible skips on, and only this script writes it."""
    (target / "MIRROR.txt").write_text(
        f"Public mirror of a private repository.\nsource commit: {commit}\n", encoding="utf-8"
    )
    (target / "RUN-ME-FIRST.md").write_text(RUN_ME_FIRST, encoding="utf-8")


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
    write_notes(target, source_commit())
    print(f"copied {len(names)} files to {target}, plus MIRROR.txt and RUN-ME-FIRST.md")
    for finding in findings:
        print("REDACTED, ROTATE THE ORIGINAL IF REAL:", finding)
    print("SAFE, WITH REDACTIONS" if findings else "CLEAN")
    return 3 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
