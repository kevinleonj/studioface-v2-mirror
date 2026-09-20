"""Task 07: prove log lines reach Cloud Run, at the composition root.

tests/test_logging.py already proves `configure_logging()` produces one JSON line per
record. It never proves `build()` actually calls it — that gap is exactly how F7
happened: the unit worked, nobody wired it in, and every `logger.info` in production
went nowhere until 5d781f6 added the call inside `build()`.

Reuses the faked-network `built` fixture from tests/test_entry_builds.py (CLAUDE.md
lesson 8: production wiring counts, only network boundaries faked) instead of
declaring the same Firestore/Storage/Stripe/Resend doubles a second time.
"""

import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from test_entry_builds import built  # noqa: E402,F401

from app.logs import JsonFormatter  # noqa: E402


def test_the_root_logger_has_the_json_handler_after_build(built):  # noqa: F811
    """Not just "any handler": pytest's own log-capture plugin attaches one to the
    root logger for every test regardless of what the application does, so that check
    alone would pass even with `configure_logging()` never called. Assert the actual
    handler `configure_logging()` installs is there instead."""
    root = logging.getLogger()
    assert any(isinstance(h.formatter, JsonFormatter) for h in root.handlers), (
        "no JSON-formatted handler on the root logger after build(); Cloud Run gets nothing"
    )


def test_the_root_logger_level_is_info_or_lower(built):  # noqa: F811
    """WARNING is the default level with no handler configured. INFO or lower is what
    lets the `log_call` and route-level `logger.info` lines through."""
    root = logging.getLogger()
    assert root.level <= logging.INFO, f"root logger level {root.level} drops INFO lines"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
