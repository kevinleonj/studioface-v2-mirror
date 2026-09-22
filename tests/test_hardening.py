"""Task 73, small-hardening. Five independent changes, each with its own refused/passes
pair rather than one shared fixture standing in for all of them - a check that only
proves a marker exists in the source is not a check.

1. The task-token compare at /internal/generate is now hmac.compare_digest, encoded to
   bytes first so a header full of non-ASCII characters cannot turn a 403 into a 500 -
   compare_digest refuses two `str` unless both are ASCII-only, but bytes carries no
   such restriction.
2. app/adapters/turnstile.py now fails CLOSED (503 turnstile_unavailable) on a
   Cloudflare outage instead of raising an uncaught exception, and checks the
   `hostname` field siteverify returns so a token solved on someone else's site cannot
   be replayed here.
3. PAID_STATUS is gone from app/main.py - it was assigned once and read nowhere.
4. refund.updated / refund.failed now act only on Stripe's three TERMINAL refund
   statuses (succeeded, failed, canceled); `pending` and `requires_action` are left
   alone rather than being written into failed_refund_failed on the strength of not
   being `succeeded`. Source: https://docs.stripe.com/api/refunds/object, "status
   (string, nullable) ... This can be `pending`, `requires_action`, `succeeded`,
   `failed`, or `canceled`", read 2026-09-22 (see docs/verified.md).
"""

import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_guards_http import TASKS, build_client  # noqa: E402
from test_refund_reconciliation import deps_for, order_with_pending_refund  # noqa: E402
from test_refund_reconciliation import event as refund_event  # noqa: E402

import app.main as main_module  # noqa: E402
from app.adapters import turnstile as turnstile_module  # noqa: E402
from app.core import OrderStore, Pipeline, TurnstileUnavailable  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import make_app  # noqa: E402

# ---------------------------------------------------------------- 1. task-token compare


def test_the_task_token_compare_refuses_a_wrong_token():
    c, *_ = build_client()
    r = c.post("/internal/generate/cs_x", headers={"x-tasks-token": "not-the-real-token"})
    assert r.status_code == 403


def test_the_task_token_compare_lets_the_real_token_through():
    """The twin of the refusal above: same route, same shape of call, the one real
    token. `test_task_endpoint_requires_token` in test_guards_http.py already proves a
    MISSING header is refused before the compare ever runs; this proves the compare
    itself is not just refusing everything."""
    c, store, *_ = build_client()
    body = (
        b'{"id":"evt_h","type":"checkout.session.completed","data":{"object":'
        b'{"id":"cs_h","amount_total":1999,"customer_details":{"email":"k@example.com"},'
        b'"metadata":{"source_urls":"https://cdn/a.jpg,https://cdn/b.jpg","style":"linkedin"}}}}'
    )
    import hashlib
    import hmac
    import time

    ts = int(time.time())
    sig = hmac.new(b"whsec_test", f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    c.post("/api/stripe/webhook", content=body, headers={"stripe-signature": f"t={ts},v1={sig}"})
    r = c.post("/internal/generate/cs_h", headers={"x-tasks-token": TASKS})
    assert r.status_code == 200
    assert r.json()["status"] == "delivered"


def test_the_task_token_compare_does_not_500_on_a_hostile_non_ascii_header():
    """One check nobody asked for, aimed at the likeliest break: hmac.compare_digest
    raises TypeError comparing two `str` unless both are ASCII-only. A header is
    attacker-controlled input, so a visitor sending a non-ASCII header must still get
    a clean 403, never an unhandled 500. Sent as raw Latin-1 bytes (HTTP header bytes
    on the wire, and what ASGI hands the app) rather than a Python str, because
    httpx's own client-side encoder refuses to construct a request carrying a
    non-ASCII str header at all — the attacker is not limited to what httpx permits."""
    c, *_ = build_client()
    r = c.post(
        "/internal/generate/cs_x",
        headers={"x-tasks-token": "tökén-not-real".encode("latin-1")},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------- 2. turnstile adapter


class _FakeResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body

    def json(self) -> dict:
        return self._body


def test_turnstile_outage_raises_unavailable_not_an_uncaught_error(monkeypatch):
    def boom(*_args, **_kwargs):
        raise httpx.ConnectTimeout("connect timed out")

    monkeypatch.setattr(turnstile_module.httpx, "post", boom)
    with pytest.raises(TurnstileUnavailable):
        turnstile_module.verify_turnstile("secret", "sometoken", "1.2.3.4", "studioface.app")


def test_turnstile_outage_reaches_the_visitor_as_503_not_500():
    """The adapter-level exception above has to actually change the HTTP answer at
    /api/preview - a guard sits on the money path, so an outage must fail CLOSED
    (refuse this preview, 503) rather than fail open (let it through) or fail loud
    (an unhandled 500 the frontend cannot read)."""

    def outage(token, ip):
        raise TurnstileUnavailable("timeout")

    c = _preview_client(outage)
    r = c.post("/api/preview", data={"turnstile_token": "tok"})
    assert r.status_code == 503
    assert r.json()["detail"] == "turnstile_unavailable"


def test_turnstile_refuses_a_token_solved_on_a_different_site(monkeypatch):
    """The hostname check itself: a token minted by solving the real widget on a
    stranger's site must not verify here. `secret` alone does not prove which SITE
    solved the challenge, only which account owns the widget - Cloudflare's own
    siteverify response carries `hostname` for exactly this reason."""
    monkeypatch.setattr(
        turnstile_module.httpx,
        "post",
        lambda *a, **kw: _FakeResponse(200, {"success": True, "hostname": "attacker.example"}),
    )
    ok = turnstile_module.verify_turnstile("secret", "sometoken", "1.2.3.4", "studioface.app")
    assert ok is False


def test_turnstile_passes_a_token_solved_on_the_expected_host(monkeypatch):
    """Twin of the refusal above: same response shape, the one hostname that must
    pass. `expected_hostname` is a parameter precisely so this is 127.0.0.1 for the
    local funnel walk and studioface.app in production - never a literal in the
    adapter that would make one of the two environments unable to ever pass."""
    monkeypatch.setattr(
        turnstile_module.httpx,
        "post",
        lambda *a, **kw: _FakeResponse(200, {"success": True, "hostname": "127.0.0.1"}),
    )
    ok = turnstile_module.verify_turnstile("secret", "sometoken", "1.2.3.4", "127.0.0.1")
    assert ok is True


def _preview_client(verify_turnstile) -> TestClient:
    store = OrderStore()
    pipeline = Pipeline(
        store=store,
        model=type("M", (), {"edit": lambda self, u, p: "x"})(),
        storage=type("S", (), {"put": lambda self, k, u: k})(),
        send_email=lambda t, b: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret="app",
    )
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter()),
        enqueue=lambda i: None,
        preview_fn=lambda files, batch: "https://cdn/preview.png",
        webhook_secret="whsec",
        tasks_token="tt",
        verify_turnstile=verify_turnstile,
    )
    return TestClient(app)


# ---------------------------------------------------------------- 3. PAID_STATUS gone


def test_paid_status_constant_is_gone():
    """It was assigned once (app/main.py) and read nowhere - dead code the clutter
    rules ask to delete, not carry forward."""
    assert not hasattr(main_module, "PAID_STATUS")


# ---------------------------------------------------------------- 4. refund.updated


def test_a_pending_refund_update_is_left_alone_not_marked_failed():
    """The defect: `pending` is not `succeeded`, so the old `else` branch wrote
    failed_refund_failed - telling a customer their refund had failed while Stripe was
    still moving the money. `pending` is not terminal (Stripe's own five-value status
    enum), so nothing should be written at all."""
    store = OrderStore()
    order_with_pending_refund(store)
    out = main_module._handle_event(deps_for(store), refund_event("refund.updated", "pending"))
    order = store.get("cs_test_refund")
    assert order.status == "failed_refund_pending"
    assert order.refund_status == "pending"
    assert out == {"settling": "pending"}


def test_a_requires_action_refund_update_is_also_left_alone():
    """Twin of the pending case: the other non-terminal status Stripe documents."""
    store = OrderStore()
    order_with_pending_refund(store)
    main_module._handle_event(deps_for(store), refund_event("refund.updated", "requires_action"))
    assert store.get("cs_test_refund").status == "failed_refund_pending"


def test_a_succeeded_refund_still_reconciles_immediately():
    """The twin that must get through: a TERMINAL status is unaffected by the new
    gate. test_refund_reconciliation.py already pins this end to end; this is the
    same behaviour asserted right next to the new gate that could have broken it."""
    store = OrderStore()
    order_with_pending_refund(store)
    out = main_module._handle_event(deps_for(store), refund_event("refund.updated", "succeeded"))
    assert store.get("cs_test_refund").status == "failed_refunded"
    assert out["reconciled"] == "cs_test_refund"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
