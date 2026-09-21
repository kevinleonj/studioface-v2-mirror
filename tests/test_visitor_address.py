"""app/main.py keyed the per-visitor preview cap and the /api/recuperar cap on the
FIRST entry of X-Forwarded-For (`x_forwarded_for.split(",")[0].strip()`). That entry
is whatever the connecting client put in its own request - visitors set arbitrary
headers freely (curl, fetch, a script) - so a script could prepend a fresh fake
address on every call and dodge both ceilings entirely.

Cloud Run's own front door, Google Front End (GFE), is the single hop between the
public internet and this container (docs/verified.md 13c: "GFE -> HTTP proxy -> app
server", the same ingress fact task 13 already researched and cited - not
re-researched here). Standard X-Forwarded-For handling has each hop APPEND the
address it observed the connection from, so the LAST entry is the one GFE itself
appended: the actual peer address of the TCP connection into Google's edge, which a
visitor can pad the header in front of but cannot forge. docs/verified.md 13c is
explicit that no Cloud Run page states outright that Cloud Run sets X-Forwarded-For -
using the trailing entry is this task's own inference from the documented single-hop
ingress path, not a vendor claim, same honesty level task 13 held.

Both call sites (the preview cap in `_register_preview` and the recovery cap in
`_register_recovery`) now share one small function, `visitor_address`, tested here
directly so the fix is pinned once rather than duplicated per route.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import OrderStore, Pipeline  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import make_app, visitor_address, xff_shape  # noqa: E402


class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeRequest:
    """Stands in for the one field `visitor_address` reads on fallback: the raw
    socket peer, exactly what `_client_ip` reads from a real Request."""

    def __init__(self, host):
        self.client = _FakeClient(host) if host else None


# ---------------------------------------------------------------- the pure function


def test_a_spoofed_first_entry_does_not_change_the_key():
    """The exact attack this task closes: a script rotates the entry IT controls
    (the first one) while the entry GFE appends (the last one) stays fixed, because
    it names the same real connection. The key must not move."""
    request = _FakeRequest("10.0.0.1")
    first_call = visitor_address("9.9.9.9, 203.0.113.7", request)
    second_call = visitor_address("1.2.3.4, 203.0.113.7", request)
    third_call = visitor_address("not-even-an-ip, 203.0.113.7", request)
    assert first_call == second_call == third_call == "203.0.113.7"


def test_the_trailing_entry_is_used_not_the_leading_one():
    request = _FakeRequest("10.0.0.1")
    assert visitor_address("198.51.100.9, 203.0.113.7", request) == "203.0.113.7"


def test_a_single_entry_header_is_used_as_is():
    """No proxy chain at all (e.g. a direct test client) still works: one entry is
    both the first and the last."""
    request = _FakeRequest("10.0.0.1")
    assert visitor_address("203.0.113.7", request) == "203.0.113.7"


def test_a_missing_header_falls_back_to_the_socket_peer():
    request = _FakeRequest("10.0.0.1")
    assert visitor_address("", request) == "10.0.0.1"


def test_a_malformed_trailing_comma_falls_back_to_the_socket_peer():
    """'1.2.3.4,' splits to ['1.2.3.4', ''] - the last entry is empty, which is not
    a usable key, so this falls back rather than rate-limiting every malformed
    request together under the empty string."""
    request = _FakeRequest("10.0.0.1")
    assert visitor_address("1.2.3.4,", request) == "10.0.0.1"


def test_a_header_of_only_whitespace_falls_back_to_the_socket_peer():
    request = _FakeRequest("10.0.0.1")
    assert visitor_address("   ", request) == "10.0.0.1"


def test_no_socket_peer_either_gives_an_empty_string():
    """Matches `_client_ip`'s own contract (request.client is None -> ""); this
    function never raises just because both sources are absent."""
    request = _FakeRequest(None)
    assert visitor_address("", request) == ""


# ---------------------------------------------- task 20: measuring the assumption


def test_xff_shape_counts_entries_and_never_prints_a_full_address():
    """Task 20's one INFO line: enough to compare the last entry against Cloud
    Run's own httpRequest.remoteIp (first two octets each), never a full IP."""
    shape = xff_shape("198.51.100.9, 203.0.113.7")
    assert shape == "entries=2 first=198.51 last=203.0 first_eq_last=False"
    assert "198.51.100.9" not in shape
    assert "203.0.113.7" not in shape


def test_xff_shape_flags_when_the_only_entry_is_both_first_and_last():
    assert xff_shape("203.0.113.7") == "entries=1 first=203.0 last=203.0 first_eq_last=True"


def test_xff_shape_handles_a_non_ipv4_entry_without_raising():
    """A hostname or v6 literal never has exactly four dot-separated parts, so it is
    reported as unknown rather than mis-sliced into something that looks like an
    octet pair."""
    assert xff_shape("not-an-ip") == "entries=1 first=? last=? first_eq_last=False"


def test_xff_shape_of_an_empty_header_has_zero_entries():
    assert xff_shape("") == "entries=0 first=? last=? first_eq_last=False"


# ---------------------------------------------------------------- through the API


def build_preview_client(**limiter_kwargs):
    store = OrderStore()
    pipeline = Pipeline(
        store=store,
        model=type("M", (), {"edit": lambda self, u, p: "x"})(),
        storage=type("S", (), {"put": lambda self, k, u: k})(),
        send_email=lambda t, b: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret="sfx",
    )
    limiter = RateLimiter(
        counter=MemoryCounter(), per_subnet=1000, daily_global=1000, **limiter_kwargs
    )
    app = make_app(
        pipeline,
        limiter,
        enqueue=lambda i: None,
        preview_fn=lambda files, batch: "https://storage.googleapis.com/x",
        webhook_secret="whsec",
        tasks_token="tt",
    )
    return TestClient(app)


JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100


def _preview(client, forwarded_for):
    files = [("files", ("a.jpg", JPEG, "image/jpeg"))]
    return client.post(
        "/api/preview",
        files=files,
        data={"turnstile_token": "good"},
        headers={"x-forwarded-for": forwarded_for},
    )


def test_a_visitor_cannot_dodge_the_preview_cap_by_prepending_addresses():
    client = build_preview_client(per_client=1)
    first = _preview(client, "1.1.1.1, 203.0.113.7")
    assert first.status_code == 200
    second = _preview(client, "2.2.2.2, 203.0.113.7")
    # Task 29: being capped no longer means a 429 — /api/preview stores the photos
    # and signs a handle instead (`limited: true`), which can only be true if
    # RateLimiter.check keyed this request the same as the first one.
    assert second.status_code == 200
    assert second.json()["limited"] is True, (
        "rotating the visitor-controlled leading entry must not lift the cap"
    )


def test_two_real_visitors_sharing_a_spoofed_leading_entry_are_not_merged():
    client = build_preview_client(per_client=1)
    first_visitor = _preview(client, "1.1.1.1, 203.0.113.7")
    assert first_visitor.status_code == 200
    second_visitor = _preview(client, "1.1.1.1, 203.0.113.9")
    assert second_visitor.status_code == 200, (
        "a different real connection (different trailing, GFE-appended entry) "
        "must not inherit another visitor's cap just because they share a leading "
        "entry"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
