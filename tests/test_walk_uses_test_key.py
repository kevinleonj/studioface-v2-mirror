"""Failing-test-first for walk-after-live.

scripts/run_funnel.py used to read stripe-secret-key at version "latest". Now that
Kevin's live key is the newest version, "latest" hands the walk a live key and its own
guard correctly refuses to run at all. The fix pins the read to the TEST version number
recorded in docs/stripe-test-objects.md, and stops reading stripe-webhook-secret from
Secret Manager entirely — the walk signs and verifies its own webhook locally and never
needs the production signing secret, so a fresh one is minted per run instead.

Four cases: empty (no pin recorded at all would silently fall back to "latest"), one
(the pinned version is actually requested), many (two runs mint two different local
webhook secrets, and neither run asks Secret Manager for it), failure (the guard still
refuses a live key even if the pinned version were ever wrong).
"""

from __future__ import annotations

import pytest

from scripts import run_funnel


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "FAL_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_the_pinned_version_is_recorded_in_the_test_objects_doc() -> None:
    """Empty: nothing pins the walk to a test version unless this doc and this constant
    agree — a version that only exists in one place is a version that will drift."""
    doc = (run_funnel.ROOT / "docs" / "stripe-test-objects.md").read_text(encoding="utf-8")
    assert f"Test key version number: {run_funnel.STRIPE_TEST_KEY_VERSION}" in doc
    assert run_funnel.STRIPE_TEST_KEY_VERSION != "latest"


def test_the_stripe_key_is_requested_at_the_pinned_version_not_latest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One: stripe-secret-key must be requested at the pinned version, never "latest"."""
    requested: list[tuple[str, str]] = []

    def fake_read_secret(name: str, version: str = "latest") -> str:
        requested.append((name, version))
        return "sk_test_pinned" if name == "stripe-secret-key" else "fal-key-value"

    monkeypatch.setattr(run_funnel, "read_secret", fake_read_secret)

    run_funnel.load_environment()

    assert ("stripe-secret-key", run_funnel.STRIPE_TEST_KEY_VERSION) in requested
    assert ("stripe-secret-key", "latest") not in requested


def test_two_runs_mint_two_local_webhook_secrets_and_never_ask_secret_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Many: the webhook secret is generated per run, not fetched, across two runs."""
    requested_names: list[str] = []

    def fake_read_secret(name: str, version: str = "latest") -> str:
        requested_names.append(name)
        return "sk_test_x" if name == "stripe-secret-key" else "fal-key-value"

    monkeypatch.setattr(run_funnel, "read_secret", fake_read_secret)

    run_funnel.load_environment()
    first = run_funnel.os.environ["STRIPE_WEBHOOK_SECRET"]

    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("FAL_KEY", raising=False)

    run_funnel.load_environment()
    second = run_funnel.os.environ["STRIPE_WEBHOOK_SECRET"]

    assert "stripe-webhook-secret" not in requested_names
    assert first and second and first != second


def test_the_guard_still_refuses_a_live_key_even_at_the_pinned_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure: the live-key guard is not weakened by pinning a version number."""

    def fake_read_secret(name: str, version: str = "latest") -> str:
        return "sk_live_should_never_run" if name == "stripe-secret-key" else "fal-key-value"

    monkeypatch.setattr(run_funnel, "read_secret", fake_read_secret)

    with pytest.raises(SystemExit, match="not a test key"):
        run_funnel.load_environment()
