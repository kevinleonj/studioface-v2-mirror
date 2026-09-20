"""The gate must not audit a build that predates the source.

This happened, and it produced a green tick on work nobody had built. The design
critic left a `python -m http.server` running on frontend/out; the next `npm run
build` failed with

    [Error: EBUSY: resource busy or locked, rmdir '...frontend\\out']

and scripts/ci.py then ran design_audit.py over the PREVIOUS export and printed
`DESIGN AUDIT: 0 P0, 0 P1, 0 P2 / CI MIRROR GATE: green`. Every check passed. None of
them had seen the code being committed.

A stale artifact is the worst kind of false green: it is not a flake, it reproduces,
and the output is indistinguishable from a real pass. So freshness is now a gate step
of its own, and it says which file gave it away.

The rule is deliberately strict — the OLDEST file in the export must be newer than the
newest file in frontend/src. Comparing newest-to-newest would pass a partial rebuild
where one route was written and the rest left behind, which is exactly the shape of
the EBUSY failure.
"""

import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
ROOT = Path(__file__).resolve().parents[1]


def gate():
    import importlib.util

    spec = importlib.util.spec_from_file_location("ci_gate", ROOT / "scripts" / "ci.py")
    mod = importlib.util.module_from_spec(spec)
    # Registered BEFORE exec: @dataclass resolves annotations through
    # sys.modules[cls.__module__].__dict__, and a module loaded by path alone
    # raises AttributeError: 'NoneType' object has no attribute '__dict__'.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def touch(path: Path, when: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    os.utime(path, (when, when))


def tree(root: Path, name: str, files: dict[str, float]) -> Path:
    d = root / name
    for rel, when in files.items():
        touch(d / rel, when)
    return d


# ---------------------------------------------------------------- stale


def test_an_export_older_than_the_source_is_rejected(tmp_path):
    """The exact EBUSY case: source edited, build refused, old export left in place."""
    now = time.time()
    src = tree(tmp_path, "src", {"app/page.tsx": now})
    out = tree(tmp_path, "out", {"index.html": now - 600})
    reason = gate().stale_export(str(src), str(out))
    assert reason, "a stale export was accepted"
    assert "index.html" in reason, f"the reason must name the file: {reason}"


def test_a_partial_rebuild_is_rejected_even_though_the_newest_file_is_fresh(tmp_path):
    """Held-out check, and the reason the rule compares oldest-to-newest. A build that
    wrote one route and left the others behind has a perfectly fresh newest file."""
    now = time.time()
    src = tree(tmp_path, "src", {"app/page.tsx": now - 100})
    out = tree(tmp_path, "out", {"index.html": now, "g/index.html": now - 500})
    reason = gate().stale_export(str(src), str(out))
    assert reason and "g" in reason.replace("\\", "/")


# ---------------------------------------------------------------- fresh


def test_a_fresh_export_passes(tmp_path):
    now = time.time()
    src = tree(tmp_path, "src", {"app/page.tsx": now - 100})
    out = tree(tmp_path, "out", {"index.html": now, "g/index.html": now})
    assert gate().stale_export(str(src), str(out)) is None


# ---------------------------------------------------------------- nothing to judge


def test_no_export_is_not_a_staleness_failure(tmp_path):
    """A clean checkout has no build. That is the design audit's problem to report, and
    it already does; this check must not turn it into a second, confusing error."""
    src = tree(tmp_path, "src", {"app/page.tsx": time.time()})
    assert gate().stale_export(str(src), str(tmp_path / "missing")) is None


def test_no_source_is_not_a_staleness_failure(tmp_path):
    out = tree(tmp_path, "out", {"index.html": time.time()})
    assert gate().stale_export(str(tmp_path / "missing"), str(out)) is None


def test_an_empty_export_directory_is_not_a_staleness_failure(tmp_path):
    src = tree(tmp_path, "src", {"app/page.tsx": time.time()})
    (tmp_path / "empty").mkdir()
    assert gate().stale_export(str(src), str(tmp_path / "empty")) is None


def test_assets_copied_from_public_do_not_count_as_stale(tmp_path):
    """Next copies frontend/public verbatim into the export and PRESERVES the mtime,
    so an asset touched months ago arrives stamped months ago. Counting those made
    every build look stale: the first run of this gate reported the real export 28824s
    behind, on a build that had just succeeded, because of one file.svg."""
    now = time.time()
    frontend = tmp_path / "frontend"
    src = tree(frontend, "src", {"app/page.tsx": now - 10})
    tree(frontend, "public", {"file.svg": now - 90000})
    out = tree(frontend, "out", {"index.html": now, "file.svg": now - 90000})
    assert gate().stale_export(str(src), str(out)) is None


def test_a_stale_generated_file_is_still_caught_when_public_assets_are_old(tmp_path):
    """Held-out check on the exclusion itself: skipping public copies must not become
    a hole a genuinely stale route can hide in."""
    now = time.time()
    frontend = tmp_path / "frontend"
    src = tree(frontend, "src", {"app/page.tsx": now})
    tree(frontend, "public", {"file.svg": now - 90000})
    built = {"index.html": now, "file.svg": now - 90000, "g/index.html": now - 50}
    out = tree(frontend, "out", built)
    reason = gate().stale_export(str(src), str(out))
    assert reason and "g" in reason.replace("\\", "/")


# ---------------------------------------------------------------- wired in


def test_the_gate_checks_the_real_frontend_directories():
    """The unit tests above all use tmp dirs, so they would pass unchanged while the
    gate pointed at nothing."""
    mod = gate()
    assert Path(mod.FRONTEND_SRC) == ROOT / "frontend" / "src"
    assert Path(mod.EXPORT) == ROOT / "frontend" / "out"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
