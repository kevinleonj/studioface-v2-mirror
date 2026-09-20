"""The production image installed whatever PyPI happened to be serving that minute.

    COPY pyproject.toml ./
    RUN pip install --no-cache-dir .

`pyproject.toml` names `fastapi`, `stripe`, `google-cloud-storage` and eight more with no
versions at all. So every build resolved afresh: two deploys an hour apart could ship
different code, and a compromised release of any direct or transitive dependency would
land in production on the next push with nothing to notice it.

A lock file with hashes closes both. `--require-hashes` makes pip refuse anything whose
artifact does not match, which means a package can be yanked, re-uploaded or tampered
with and the build fails rather than shipping it.

The frontend was already correct — `npm ci` installs from package-lock.json and fails if
the lock disagrees with package.json. Only the Python half was open.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_scan import strip_comments  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "requirements.lock"
DOCKERFILE = ROOT / "Dockerfile"
PYPROJECT = ROOT / "pyproject.toml"


def dockerfile() -> str:
    """Comments stripped, and it caught me immediately.

    The comment explaining WHY --require-hashes is there contains the string
    --require-hashes, so the assertion below passed against a Dockerfile that merely
    mentioned it. Same bug class as every other one today, found by the meta-test written
    for it this morning rather than by a build that shipped unpinned."""
    return strip_comments(DOCKERFILE.read_text(encoding="utf-8"), language="sh")


def runtime_dependencies() -> list[str]:
    block = re.search(
        r"^dependencies = \[(.*?)\]", PYPROJECT.read_text(encoding="utf-8"), re.S | re.M
    )
    assert block, "pyproject declares no runtime dependencies"
    return [
        name.strip().strip('"')
        for name in block.group(1).replace("\n", " ").split(",")
        if name.strip()
    ]


def test_a_lock_file_exists():
    assert LOCK.exists(), "the image still resolves dependencies at build time"


def test_every_locked_package_is_pinned_to_one_exact_version():
    """`>=` in a lock file is not a lock."""
    loose = []
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-", " ")) or line.startswith("--"):
            continue
        if "==" not in line.split(";")[0]:
            loose.append(line[:60])
    assert not loose, f"lines that are not an exact pin: {loose}"


def test_every_locked_package_carries_a_hash():
    """Without hashes the lock pins a version number, and a version number is a label
    somebody else controls. The hash is what ties it to the bytes."""
    text = LOCK.read_text(encoding="utf-8")
    pins = re.findall(r"^([A-Za-z0-9_.\-]+)==", text, re.M)
    assert pins, "no pinned packages found in the lock"
    assert text.count("--hash=sha256:") >= len(pins), (
        f"{len(pins)} packages pinned but only {text.count('--hash=sha256:')} hashes"
    )


def test_every_runtime_dependency_appears_in_the_lock():
    """Held-out check: a lock generated from a different file, or from a stale one, is
    worse than none because it looks authoritative."""
    text = LOCK.read_text(encoding="utf-8").lower()
    missing = [d for d in runtime_dependencies() if d.lower() not in text]
    assert not missing, f"declared in pyproject but absent from the lock: {missing}"


def test_the_image_installs_from_the_lock_and_refuses_anything_unhashed():
    body = dockerfile()
    assert "requirements.lock" in body, "the Dockerfile does not use the lock"
    assert "--require-hashes" in body, (
        "without --require-hashes pip will happily install a package whose hash is absent"
    )


def test_the_image_does_not_resolve_dependencies_a_second_time():
    """Installing the project itself must not quietly re-resolve what the lock just
    pinned. --no-deps is what keeps the lock authoritative."""
    body = dockerfile()
    install_app = [ln for ln in body.splitlines() if re.search(r"pip install[^\n]*\s\.\s*$", ln)]
    assert install_app, "the app itself is never installed"
    for line in install_app:
        assert "--no-deps" in line, f"this re-resolves around the lock: {line.strip()}"


def test_the_frontend_half_is_still_locked_too():
    """npm ci fails when package-lock.json and package.json disagree; npm install would
    quietly update the lock. This is the half that was already right."""
    assert (ROOT / "frontend" / "package-lock.json").exists()
    body = dockerfile()
    assert "npm ci" in body
    assert not re.search(r"npm install\b", body), "npm install would rewrite the lock"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
