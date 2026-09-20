"""Config is one schema, read once, validated at startup.

Before this existed app/entry.py read os.environ at import time, so importing it
without a GCP project crashed with a bare KeyError and nothing in it could be tested.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings  # noqa: E402

FULL = {
    "GCP_PROJECT": "sf-prod",
    "GCP_REGION": "europe-west1",
    "PUBLIC_URL": "https://studioface.app",
    "BUCKET_SRC": "sf-src",
    "BUCKET_OUT": "sf-out",
    "TASKS_QUEUE": "generate",
    "TASKS_TOKEN": "tasks-token-9f3c",
    "APP_TOKEN_SECRET": "app-secret",
    "STRIPE_SECRET_KEY": "sk_test_x",
    "STRIPE_WEBHOOK_SECRET": "whsec_x",
    "RESEND_API_KEY": "re_x",
    "TURNSTILE_SECRET": "0x-secret",
}


def test_full_environment_parses():
    s = Settings.from_env(FULL)
    assert s.project == "sf-prod"
    assert s.bucket_src == "sf-src"
    assert s.static_dir == "/srv/static"  # default


def test_api_url_is_derived_from_public_url_when_not_set():
    assert Settings.from_env(FULL).api_url == "https://api.studioface.app"


def test_explicit_api_url_wins():
    s = Settings.from_env({**FULL, "API_URL": "https://api-staging.studioface.app"})
    assert s.api_url == "https://api-staging.studioface.app"


def test_one_missing_variable_names_that_variable():
    env = dict(FULL)
    del env["TASKS_TOKEN"]
    with pytest.raises(RuntimeError, match="TASKS_TOKEN"):
        Settings.from_env(env)


def test_every_missing_variable_is_reported_at_once_not_one_per_restart():
    """Held-out check: a cold start on Cloud Run should tell you all of them the
    first time, not make you redeploy once per missing name."""
    env = {"GCP_PROJECT": "p"}
    with pytest.raises(RuntimeError) as e:
        Settings.from_env(env)
    msg = str(e.value)
    for name in ("GCP_REGION", "PUBLIC_URL", "BUCKET_SRC", "TURNSTILE_SECRET"):
        assert name in msg
    assert "GCP_PROJECT" not in msg  # the one that was present is not blamed


def test_empty_environment_fails_loudly():
    with pytest.raises(RuntimeError, match="missing"):
        Settings.from_env({})


def test_blank_value_counts_as_missing():
    with pytest.raises(RuntimeError, match="APP_TOKEN_SECRET"):
        Settings.from_env({**FULL, "APP_TOKEN_SECRET": "   "})


def test_secrets_are_not_in_the_repr():
    """A Settings object reaching a log line or a traceback must not leak keys."""
    text = repr(Settings.from_env(FULL))
    for secret in ("sk_test_x", "whsec_x", "re_x", "0x-secret", "app-secret", "tasks-token-9f3c"):
        assert secret not in text
    assert "sf-prod" in text  # non-secret context is still useful


def test_ga4_is_optional_and_absent_by_default():
    s = Settings.from_env(FULL)
    assert s.ga4_measurement_id is None and s.ga4_api_secret is None
    s2 = Settings.from_env({**FULL, "GA4_MEASUREMENT_ID": "G-1", "GA4_API_SECRET": "sec"})
    assert s2.ga4_measurement_id == "G-1"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
