"""Task 06: the payment mode visible without exposing anything.

Derived only from the key's PREFIX (docs/verified.md, 2026-09-17 and 2026-09-18: test
keys are pk_test_/rk_test_/sk_test_, live are pk_live_/rk_live_/sk_live_). Never a
whole key, never anything past the prefix, in a log line or an HTTP response.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import stripe_mode  # noqa: E402


def test_sk_test_prefix_is_test():
    assert stripe_mode("sk_test_x") == "test"


def test_rk_test_prefix_is_test():
    assert stripe_mode("rk_test_x") == "test"


def test_sk_live_prefix_is_live():
    """The twin of the two tests above: identical shape, live prefix, live word — so
    the function cannot be hard-coded to always answer 'test' and still pass."""
    assert stripe_mode("sk_live_x") == "live"


def test_rk_live_prefix_is_live():
    assert stripe_mode("rk_live_x") == "live"


def test_an_unrecognised_prefix_is_unknown():
    assert stripe_mode("whsec_x") == "unknown"


def test_an_empty_key_is_unknown():
    assert stripe_mode("") == "unknown"
    assert stripe_mode(None) == "unknown"  # type: ignore[arg-type]


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
