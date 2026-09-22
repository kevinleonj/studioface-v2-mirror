"""Windows and multi-account failures of 17 Sep 2026, pinned as tests."""

import importlib.util
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from _exec import resolve  # noqa: E402


def load_bootstrap():
    spec = importlib.util.spec_from_file_location("bootstrap", os.path.join(ROOT, "bootstrap.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def source() -> str:
    with open(os.path.join(ROOT, "bootstrap.py"), encoding="utf-8") as fh:
        return fh.read()


def test_resolve_uses_which_so_cmd_wrappers_are_found(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda n: r"C:\sdk\bin\gcloud.cmd")
    assert resolve(["gcloud", "auth", "list"]) == [r"C:\sdk\bin\gcloud.cmd", "auth", "list"]


def test_resolve_names_the_missing_tool(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda n: None)
    with pytest.raises(FileNotFoundError, match="'stripe' is not on PATH"):
        resolve(["stripe", "login"])


def test_bootstrap_sh_goes_through_resolve(monkeypatch):
    b = load_bootstrap()
    calls = []
    monkeypatch.setattr(b, "resolve", lambda a: ["/resolved/" + a[0], *a[1:]])
    fake = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})
    monkeypatch.setattr(b.subprocess, "run", lambda args, **kw: calls.append(args) or fake())
    b.DRY = False
    b.sh(["gcloud", "--version"], capture=True)
    assert calls == [["/resolved/gcloud", "--version"]]


def test_bootstrap_never_uses_exec_or_adc():
    src = source()
    assert "os.execv" not in src
    assert (
        "application-default" not in src
    )  # one Google account, token via GOOGLE_OAUTH_ACCESS_TOKEN


def test_ga4_secret_regex_rejects_measurement_id():
    rx = load_bootstrap().SECRETS["ga4_secret"][1]
    assert re.fullmatch(rx, "G-NLP25TBTRJ") is None
    assert re.fullmatch(rx, "AbCdEf123456-xyz") is not None


def test_stripe_key_regex_requires_secret_prefix():
    rx = load_bootstrap().SECRETS["stripe_key"][1]
    assert re.fullmatch(rx, "pk_test_123") is None
    assert re.fullmatch(rx, "sk_test_123") is not None


def test_terraform_env_carries_gcloud_token(monkeypatch):
    b = load_bootstrap()
    monkeypatch.setattr(
        b, "sh", lambda args, **kw: "TOKEN" if "print-access-token" in args else "gh"
    )
    env = b.tf_env({"cf_token": "c", "stripe_key": "s"})
    assert env["GOOGLE_OAUTH_ACCESS_TOKEN"] == "TOKEN"
    assert env["CLOUDFLARE_API_TOKEN"] == "c" and env["STRIPE_API_KEY"] == "s"


def test_inputs_remember_plain_answers(monkeypatch, tmp_path):
    b = load_bootstrap()
    b.ANSWERS = str(tmp_path / "a.json")
    b.DRY = False
    answers = iter(["studio-face-fresh-start", "", "kevinleonj", "0" * 32, "1" * 32, "", "2"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(b, "sh", lambda a, **kw: "kevin@limeralda.com\nOWNER_EMAIL_REDACTED")
    monkeypatch.setattr(b, "keyring_or_none", lambda: None)
    monkeypatch.setattr(
        b, "ask_secret", lambda key: "sk_test_x" if key == "stripe_key" else "unset"
    )
    c = b.inputs(reset=False)
    assert c["project"] == "studio-face-fresh-start" and c["domain"] == "studioface.app"
    assert c["ga4_id"] == "unset"
    assert c["gcp_account"] == "OWNER_EMAIL_REDACTED"  # picked by number, never typed
    # second run: Enter keeps every saved value
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    assert b.inputs(reset=False)["gh_owner"] == "kevinleonj"


def test_inputs_reject_bad_project_id_then_accept(monkeypatch, tmp_path):
    b = load_bootstrap()
    b.ANSWERS = str(tmp_path / "a.json")
    b.DRY = False
    answers = iter(["Bad_ID", "studio-face-fresh-start"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    c = {}
    b.ask_plain(c, "project")
    assert c["project"] == "studio-face-fresh-start"


def test_google_account_is_picked_from_gcloud_list_not_typed(monkeypatch):
    b = load_bootstrap()
    b.DRY = False
    calls = []
    monkeypatch.setattr(
        b, "sh", lambda a, **kw: calls.append(a) or "kevin@limeralda.com\nOWNER_EMAIL_REDACTED"
    )
    answers = iter(
        ["9", "kevinlenjouvin@gmail.com", "2"]
    )  # out of range, a typo, then a valid pick
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    c = {"gcp_account": "kevinlenjouvin@gmail.com"}  # a saved typo must not survive
    b.pick_google_account(c)
    assert c["gcp_account"] == "OWNER_EMAIL_REDACTED"
    assert all("auth login" not in " ".join(a) for a in calls)


def test_existing_api_dns_record_is_imported_not_recreated(monkeypatch):
    b = load_bootstrap()
    b.DRY = False
    calls = []
    monkeypatch.setattr(b, "sh", lambda a, **kw: calls.append(a) or "")  # state list: empty
    fake = type("R", (), {"json": lambda self: {"result": [{"id": "rec123", "type": "CNAME"}]}})

    class FakeHttpx:
        @staticmethod
        def get(*a, **kw):
            return fake()

    monkeypatch.setitem(sys.modules, "httpx", FakeHttpx)
    b.import_existing_dns({"cf_zone": "z" * 32, "domain": "studioface.app", "cf_token": "t"}, {})
    assert calls[-1][:4] == ["terraform", "import", "-input=false", "cloudflare_dns_record.api"]
    assert calls[-1][4] == "z" * 32 + "/rec123"


def test_dns_import_skipped_when_already_in_state(monkeypatch):
    b = load_bootstrap()
    b.DRY = False
    calls = []
    monkeypatch.setattr(b, "sh", lambda a, **kw: calls.append(a) or "cloudflare_dns_record.api")
    b.import_existing_dns({"cf_zone": "z", "domain": "d", "cf_token": "t"}, {})
    assert all(a[:2] != ["terraform", "import"] for a in calls)


def test_phase_a_creates_everything_cloud_run_needs_first():
    b = load_bootstrap()
    for must in (
        "google_secret_manager_secret.s",
        "stripe_webhook_endpoint.api",
        "cloudflare_turnstile_widget.preview",
        "google_project_service.svc",
    ):
        assert must in b.PHASE_A
    assert "google_cloud_run_v2_service.api" not in b.PHASE_A


def test_tainted_cloud_run_is_untainted_before_full_apply(monkeypatch):
    b = load_bootstrap()
    b.DRY = False
    calls = []

    def fake_sh(a, **kw):
        calls.append(a)
        return "resource ... (tainted)" if "show" in a else "google_cloud_run_v2_service.api"

    monkeypatch.setattr(b, "sh", fake_sh)
    b.untaint_cloud_run({})
    assert calls[-1][:3] == ["terraform", "untaint", "google_cloud_run_v2_service.api"]


def test_untaint_skipped_when_service_not_in_state(monkeypatch):
    b = load_bootstrap()
    b.DRY = False
    calls = []
    monkeypatch.setattr(b, "sh", lambda a, **kw: calls.append(a) or "")
    b.untaint_cloud_run({})
    assert all(a[:2] != ["terraform", "untaint"] for a in calls)


def test_put_secret_skips_when_an_enabled_version_exists(monkeypatch):
    b = load_bootstrap()
    b.DRY = False
    calls = []
    monkeypatch.setattr(
        b, "sh", lambda a, **kw: calls.append(a) or "projects/1/secrets/x/versions/4"
    )
    b.put_secret("p", "fal-key", "value")
    assert all("add" not in a for a in calls)


def test_put_secret_adds_when_no_version(monkeypatch):
    b = load_bootstrap()
    b.DRY = False
    calls = []
    monkeypatch.setattr(b, "sh", lambda a, **kw: calls.append(a) or "")
    b.put_secret("p", "fal-key", "value")
    assert calls[-1][:4] == ["gcloud", "secrets", "versions", "add"]


def test_apex_reconcile_deletes_only_foreign_records(monkeypatch):
    b = load_bootstrap()
    b.DRY = False
    deleted = []
    records = [
        {"id": "1", "type": "A", "content": "20.50.1.1"},  # old Azure
        {"id": "2", "type": "A", "content": "216.239.32.21"},  # already Google
        {"id": "3", "type": "TXT", "content": "google-site-verification=abc"},
    ]

    class FakeHttpx:
        @staticmethod
        def get(*a, **kw):
            return type("R", (), {"json": lambda self: {"result": records}})()

        @staticmethod
        def delete(url, **kw):
            deleted.append(url.rsplit("/", 1)[1])

    monkeypatch.setitem(sys.modules, "httpx", FakeHttpx)
    b.reconcile_apex_dns({"cf_zone": "z", "cf_token": "t", "domain": "studioface.app"})
    assert deleted == ["1"]


def test_bootstrap_really_runs_the_command_that_attaches_the_hook(monkeypatch):
    """tests/test_pre_push_hook.py greps bootstrap.py for "core.hooksPath", and the
    comment explaining the line contains that string too. Measured: delete the
    `sh(["git", "config", ...])` call, keep the comment, and that test still passes —
    so the held-out check cannot tell an attached gate from a described one. This one
    asserts the argv is actually handed to `sh`, which a comment cannot satisfy.
    """
    b = load_bootstrap()
    b.DRY = False
    calls = []
    monkeypatch.setattr(b, "sh", lambda a, **kw: calls.append(a) or "")
    monkeypatch.setattr(b, "ok", lambda a, **kw: True)
    monkeypatch.setattr(b, "write", lambda p, t: None)
    b.git_push({"github_repo_https": "https://github.com/kevinleonj/studioface-v2.git"})
    assert ["git", "config", "core.hooksPath", ".githooks"] in calls


def test_git_remote_is_https_with_gh_credential_helper(monkeypatch):
    b = load_bootstrap()
    b.DRY = False
    calls = []
    monkeypatch.setattr(b, "sh", lambda a, **kw: calls.append(a) or "")
    monkeypatch.setattr(b, "ok", lambda a, **kw: True)
    monkeypatch.setattr(b, "write", lambda p, t: None)
    b.git_push({"github_repo_https": "https://github.com/kevinleonj/studioface-v2.git"})
    assert ["gh", "auth", "setup-git"] in calls
    assert [
        "git",
        "remote",
        "set-url",
        "origin",
        "https://github.com/kevinleonj/studioface-v2.git",
    ] in calls
