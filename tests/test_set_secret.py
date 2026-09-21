"""scripts/set_secret.py called subprocess.run(["gcloud", ...]) directly. On Windows
gcloud is gcloud.cmd; CreateProcess does not search PATHEXT, so that raised WinError 2
(the project's own 17 Sep 2026 lesson) even with gcloud on PATH. The fix routes argv[0]
through _exec.resolve, the same shutil.which fix bootstrap.py already uses.

The whole point of this script is that a secret value never appears on a screen, in a
log, in shell history, or in an argv list. Every test here uses an obvious placeholder
value, never a real-looking secret, and no test ever adds a real Secret Manager
version: subprocess.run and shutil.which are always doubled.

Four cases plus cold start, this repo's own rule: empty, one, many, failure, cold start.
"""

import importlib.util
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def load_set_secret():
    """Fresh module object each time, the same way tests/test_bootstrap.py loads
    bootstrap.py — spec_from_file_location, not a cached sys.modules import, so one
    test's monkeypatching of module globals cannot bleed into the next test."""
    spec = importlib.util.spec_from_file_location(
        "set_secret_mod", os.path.join(ROOT, "scripts", "set_secret.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeCompleted:
    returncode = 0


def test_cold_start_import_runs_no_subprocess_and_asks_for_no_secret(monkeypatch):
    """Regression for the original file: `name = sys.argv[1]` and `getpass.getpass(...)`
    ran at module level, so merely importing the module (as this test suite must, to
    reach the functions inside it) would crash on a missing argv and prompt for a
    secret as a side effect of loading. Importing must do nothing but define things."""
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: calls.append((a, kw)) or FakeCompleted())
    prompts = []
    monkeypatch.setattr("getpass.getpass", lambda prompt="": prompts.append(prompt) or "unused")
    load_set_secret()
    assert calls == []
    assert prompts == []


def test_one_secret_is_resolved_and_piped_on_stdin_not_argv(monkeypatch, capsys):
    mod = load_set_secret()
    calls = []
    monkeypatch.setattr("shutil.which", lambda n: r"C:\sdk\bin\gcloud.cmd")
    monkeypatch.setattr(
        mod.subprocess, "run", lambda args, **kw: calls.append((args, kw)) or FakeCompleted()
    )
    monkeypatch.setattr(mod.getpass, "getpass", lambda prompt="": "PLACEHOLDER_VALUE")

    rc = mod.main(["set_secret.py", "stripe-secret-key"])

    assert rc == 0
    args, kwargs = calls[0]
    assert args == [
        r"C:\sdk\bin\gcloud.cmd",
        "secrets",
        "versions",
        "add",
        "stripe-secret-key",
        "--data-file=-",
    ]
    assert args[0] == r"C:\sdk\bin\gcloud.cmd"  # exactly what shutil.which returned
    assert kwargs["input"] == "PLACEHOLDER_VALUE"
    assert "PLACEHOLDER_VALUE" not in args  # the value is never an argv token
    out = capsys.readouterr().out
    assert "PLACEHOLDER_VALUE" not in out
    assert out.strip() == "stripe-secret-key: version added"


def test_empty_value_is_still_piped_not_skipped(monkeypatch):
    """An empty hidden prompt (Enter pressed with nothing typed) must still reach
    gcloud on stdin rather than being silently dropped or treated as absent."""
    mod = load_set_secret()
    calls = []
    monkeypatch.setattr("shutil.which", lambda n: "/usr/bin/gcloud")
    monkeypatch.setattr(
        mod.subprocess, "run", lambda args, **kw: calls.append((args, kw)) or FakeCompleted()
    )
    monkeypatch.setattr(mod.getpass, "getpass", lambda prompt="": "")

    rc = mod.main(["set_secret.py", "some-secret"])

    assert rc == 0
    args, kwargs = calls[0]
    assert kwargs["input"] == ""
    assert args[0] == "/usr/bin/gcloud"


def test_many_secrets_in_sequence_never_mix_up_or_leak_values(monkeypatch):
    mod = load_set_secret()
    calls = []
    monkeypatch.setattr("shutil.which", lambda n: "/usr/bin/gcloud")
    monkeypatch.setattr(
        mod.subprocess, "run", lambda args, **kw: calls.append((args, kw)) or FakeCompleted()
    )
    values = iter(["PLACEHOLDER_ONE", "PLACEHOLDER_TWO", "PLACEHOLDER_THREE"])
    monkeypatch.setattr(mod.getpass, "getpass", lambda prompt="": next(values))
    names = ["fal-key", "resend-api-key", "ga4-api-secret"]

    for name in names:
        assert mod.main(["set_secret.py", name]) == 0

    assert [args[4] for args, _ in calls] == names
    got_values = [kwargs["input"] for _, kwargs in calls]
    assert got_values == ["PLACEHOLDER_ONE", "PLACEHOLDER_TWO", "PLACEHOLDER_THREE"]
    every_argv_token = [tok for args, _ in calls for tok in args]
    for value in got_values:
        assert value not in every_argv_token


def test_failure_gcloud_missing_from_path_fails_clean_not_a_winerror(monkeypatch, capsys):
    """The bug this task fixes: subprocess.run(["gcloud", ...]) on Windows raises
    WinError 2. After the fix, a missing gcloud must be reported as a clear message,
    and subprocess.run must never even be reached with an unresolved "gcloud"."""
    mod = load_set_secret()
    monkeypatch.setattr("shutil.which", lambda n: None)
    monkeypatch.setattr(mod.getpass, "getpass", lambda prompt="": "PLACEHOLDER_VALUE")
    reached_subprocess = []
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **kw: reached_subprocess.append(1))

    rc = mod.main(["set_secret.py", "some-secret"])

    assert rc != 0
    assert reached_subprocess == []
    err = capsys.readouterr().err
    assert "gcloud" in err and "not on PATH" in err
    assert "WinError" not in err
    assert "PLACEHOLDER_VALUE" not in err


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
