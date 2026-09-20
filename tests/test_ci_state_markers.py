"""The CI gate writes two state markers, and they are not the same file.

`ci_mirror_ok` is empty; the user-level guard_bash judges it by mtime and refuses a
push without it. `last_test_run` holds a unix timestamp and is read by the Stop hook
(~/.claude/hooks/pack/check_done.py), which blocks the end of a turn when it is older
than the newest changed source file.

scripts/ci.py wrote only the first. The second is stamped by guard_shell.py:124, for
commands it recognises as a test run — and `python scripts/ci.py`, the one command
this project tells everyone to use, does not look like one. So the canonical gate left
last_test_run at 17:49 on 2026-09-17 while going green at 19:39, and the Stop hook
blocked the turn twice on work whose suite had passed both times.

A marker whose value depends on what a command line looks like is worse than no
marker: it does not fail, it nags, and the obvious response — run the suite again the
documented way — never helps.
"""

import importlib.util
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def ci_module():
    """Import scripts/ci.py by path. It has no package, and importing it is only safe
    because main() is behind an __main__ guard — otherwise this re-runs the suite."""
    spec = importlib.util.spec_from_file_location("ci_gate", ROOT / "scripts" / "ci.py")
    mod = importlib.util.module_from_spec(spec)
    # Registered BEFORE exec: @dataclass resolves annotations through
    # sys.modules[cls.__module__].__dict__, and a module loaded by path alone
    # raises AttributeError: 'NoneType' object has no attribute '__dict__'.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_importing_the_gate_does_not_run_the_gate():
    """The guard itself. Without it every test here would fork a nested pytest.

    `STEPS` became `steps()` when the gate grew conditional steps whose argv depends on
    where npm lives on this machine."""
    assert ci_module().steps(), "the plan should be buildable without having been run"


def test_both_markers_are_written(tmp_path):
    ci_module().record_run(str(tmp_path))
    assert (tmp_path / "ci_mirror_ok").exists()
    assert (tmp_path / "last_test_run").exists(), (
        "the Stop hook reads last_test_run; writing only ci_mirror_ok makes it unsatisfiable"
    )


def test_last_test_run_holds_a_timestamp_the_hook_can_parse():
    """check_done.py does float(path.read_text()). Anything else raises there, inside
    a hook, where the traceback is not shown."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        before = time.time()
        ci_module().record_run(d)
        value = float(Path(d, "last_test_run").read_text())
    assert before <= value <= time.time()


def test_the_timestamp_is_injectable_so_this_test_is_not_a_clock_race():
    with __import__("tempfile").TemporaryDirectory() as d:
        ci_module().record_run(d, now=1234.5)
        assert Path(d, "last_test_run").read_text() == "1234.5"


def test_a_missing_state_directory_is_created(tmp_path):
    """Cold start: a fresh clone has no .claude/state at all."""
    nested = tmp_path / "deep" / "state"
    ci_module().record_run(str(nested))
    assert (nested / "last_test_run").exists()


def test_the_design_audit_is_not_dropped_on_a_clean_clone():
    """Follow-up left by the self-heal run, and it is my bug.

    The plan was built with `if s.name != "design audit" or os.path.isdir(EXPORT)`,
    evaluated BEFORE the frontend build step runs. On a clean clone there is no
    frontend/out at that moment, so the audit was filtered out of the plan entirely —
    and the coverage report then printed `design  mirrored  npm ci, frontend build`
    without ever mentioning that the audit had not run. A silent subset, which is the
    one thing this gate exists not to do.

    The audit now stays in the plan and decides at RUN time, after the build that
    produces what it audits."""
    plan = [s.name for s in ci_module().steps()]
    assert "design audit" in plan, "the audit is missing from the plan before anything ran"
    assert plan.index("frontend build") < plan.index("design audit"), (
        "the audit must run after the build that produces the export it reads"
    )


def test_the_real_gate_points_at_the_repo_state_directory():
    """Held-out check: the unit tests above all use a tmp dir, so they would still pass
    if STATE pointed somewhere harmless and the real hook kept starving."""
    mod = ci_module()
    assert Path(mod.STATE) == ROOT / ".claude" / "state"
    assert os.path.basename(mod.ROOT) == ROOT.name


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
