"""scripts/check.py's stripe_live guard.

HANDOFF, 21 Sep: stripe_live was already green BEFORE the live switch, because it only
read stripe_mode off the key's prefix — a live key paired with a still-test price is
exactly the state in which checkout is broken, and the old check could not see it.
Task 21 makes /health answer stripe_price_live too (tests/test_health.py,
tests/test_entry_builds.py); this file is the outside-in guard's own test, proving it
now requires BOTH stripe_mode == "live" AND stripe_price_live is True.

One case that must be refused, one that must get through — both here, plus the two
partial-credit refusals in between.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check  # noqa: E402


def _health(body: dict):
    def fake_get(path: str) -> tuple[int, str]:
        assert path == "/health", f"stripe_live must only read /health, asked for {path}"
        return 200, json.dumps(body)

    return fake_get


def test_stripe_live_gets_through_when_mode_and_price_are_both_live(monkeypatch):
    """Must get through: the one state that actually means checkout works."""
    monkeypatch.setattr(check, "get", _health({"stripe_mode": "live", "stripe_price_live": True}))
    assert check.stripe_live() == []


def test_stripe_live_is_refused_when_the_price_is_not_live(monkeypatch):
    """Must be refused: the exact outage this task closes — a live key, a still-test
    price — which the old check (mode-only) reported green."""
    monkeypatch.setattr(check, "get", _health({"stripe_mode": "live", "stripe_price_live": False}))
    problems = check.stripe_live()
    assert problems, "a live key with a non-live price must be refused"


def test_stripe_live_is_refused_when_the_mode_is_not_live(monkeypatch):
    monkeypatch.setattr(check, "get", _health({"stripe_mode": "test", "stripe_price_live": True}))
    problems = check.stripe_live()
    assert problems, "a test-mode key must be refused even if the price checks out live"


def test_stripe_live_is_refused_when_neither_is_live(monkeypatch):
    monkeypatch.setattr(check, "get", _health({"stripe_mode": "test", "stripe_price_live": False}))
    assert check.stripe_live()


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
