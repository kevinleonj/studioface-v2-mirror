"""Task 32: the server's own access line still carried a customer's gallery key.

Task 31 stopped the app from ever producing a link that puts the key where a
browser sends it to a server (docs: the key now travels in the URL fragment, or in
the `X-Gallery-Token` header). But two things still put the key on the wire into
THIS app's own request line, in `uvicorn.access` records:

1. A link already sent before task 31 (query-string shape: `?o=...&t=...`) keeps
   arriving in inboxes for weeks. Loading it makes the browser send that query
   string to the server, and uvicorn logs the full request line verbatim.
2. `/api/orders/{order_id}/{token}` (app/main.py, kept only for those old links)
   puts the delivery token in the PATH, and uvicorn logs that too.

Cloud Run's own copy of the request (the platform's own request log, separate from
this app's stdout) cannot be redacted from inside the app at all - that one only
empties out as task 31's fragment/header links replace the old ones in the wild.
This test is only about the line this app itself writes to stdout.

Both sides, with obviously fake values - a real key never appears in this file:
- a request carrying the old query-string shape or the old path-token shape is
  logged with the key gone;
- an ordinary request - including a plain `/api/orders/{order_id}` call, which
  carries no token at all - is logged with nothing changed except the order
  number, which app/logs.py already shortens everywhere else.

Every guard here gets one case that must be refused (the key must not survive)
and one case that must get through untouched, so the redaction cannot be so eager
that it eats an ordinary line - craft.md's log line is worthless if it lies.
"""

from __future__ import annotations

import io
import json
import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.logs import configure_logging  # noqa: E402

FAKE_TOKEN = "44daae73dc96b181d5a7ff2cfc5af96FAKE"  # obviously fake, never a real key
FAKE_ORDER = "cs_test_REDACTED"


@pytest.fixture
def captured():
    root = logging.getLogger()
    saved, saved_level = root.handlers[:], root.level
    buffer = io.StringIO()
    root.handlers = []
    configure_logging(stream=buffer)
    yield buffer
    root.handlers, root.level = saved, saved_level


def _access_line(buffer, path: str, status: int = 200) -> str:
    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d',
        "127.0.0.1:54321",
        "GET",
        path,
        "1.1",
        status,
    )
    raw = buffer.getvalue().splitlines()[-1]
    return json.loads(raw)["message"]


def test_the_old_query_string_gallery_key_is_redacted(captured):
    """Guard 1, refused case: an old-shape link (?o=...&t=...) still hits the
    server before any client-side rewrite runs, and must not park the key in the
    access line."""
    message = _access_line(captured, f"/g/?o={FAKE_ORDER}&t={FAKE_TOKEN}")
    assert FAKE_TOKEN not in message
    assert "t=redacted" in message


def test_an_ordinary_query_parameter_that_starts_with_t_is_untouched(captured):
    """Guard 1, pass case: `type=` must not be mistaken for `t=` just because it
    contains the letter. Over-eager redaction here would hide real query data."""
    message = _access_line(captured, "/g/?type=jpg&count=3")
    assert "type=jpg" in message
    assert "count=3" in message


def test_the_old_path_token_route_is_redacted(captured):
    """Guard 2, refused case: /api/orders/{order}/{token}, the old path-token
    shape kept alive only for links already sent, must not print the token."""
    message = _access_line(captured, f"/api/orders/{FAKE_ORDER}/{FAKE_TOKEN}")
    assert FAKE_TOKEN not in message
    assert "/api/orders/cs_test_FAKE/redacted" in message


def test_an_unrelated_path_that_merely_contains_orders_is_untouched(captured):
    """Guard 2, pass case: a path that is not /api/orders/ at all must not be
    mangled just because it shares a substring."""
    message = _access_line(captured, "/api/orders-export/report.csv")
    assert '"GET /api/orders-export/report.csv HTTP/1.1" 200' in message


def test_the_header_route_order_id_alone_is_shortened_not_erased(captured):
    """The new shape (app/main.py's status_by_header) carries no token in the
    path at all, only the order id - which app/logs.py already shortens
    everywhere else. One segment, no trailing token, so no "/redacted" marker
    should appear."""
    message = _access_line(captured, f"/api/orders/{FAKE_ORDER}")
    assert FAKE_ORDER not in message
    assert "/api/orders/cs_test_FAKE" in message
    assert "redacted" not in message


def test_an_ordinary_request_is_logged_unchanged(captured):
    """The overall pass case: a plain request that touches neither guard must
    come out byte-for-byte identical to what uvicorn would have written."""
    message = _access_line(captured, "/health")
    assert message == '127.0.0.1:54321 - "GET /health HTTP/1.1" 200'


def test_a_non_access_log_line_mentioning_t_equals_is_left_alone(captured):
    """Redaction is scoped to uvicorn.access records only. An ordinary app log
    line that happens to contain the text "t=" must not be touched - this is not
    an access line and was never carrying a URL."""
    logging.getLogger("app.main").info("retry scheduled at t=5s")
    entry = json.loads(captured.getvalue().splitlines()[-1])
    assert entry["message"] == "retry scheduled at t=5s"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
