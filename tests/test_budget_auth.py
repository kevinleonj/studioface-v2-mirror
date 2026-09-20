"""U1: `/internal/budget` had no authentication of any kind.

Measured against production on 19 September, before the fix:

    $ curl -X POST https://studioface.app/internal/budget \
        -H "Content-Type: application/json" -d '{}'
    HTTP 200
    {"killswitch":false}

The external review reported 500. It is 200 — the 500 was only an empty body failing
`await request.json()` one line earlier. With a well-formed body the handler runs, and
three lines further on it sets `killswitch = True`, which closes `/api/checkout` and
`/api/preview` with 503. An anonymous caller could take the funnel down.

The handler's own docstring asserted "Cloud Run verifies the OIDC token before this
handler runs". It does not: the service is publicly invocable, which is the same ingress
every other route uses.

The subscription was already sending a token — `infra/gcp.tf:304` configures
`oidc_token { service_account_email = ... }`. Nothing was reading it.

What the receiving application must check, from Google's own page (docs/verified.md,
19 Sep): the JWT arrives in the `Authorization` header as `Bearer <jwt>`; verify the
signature against Google's public certificates, the issuer, the `aud` claim against the
configured audience, and that the token's email is the expected push service account with
`email_verified` true.

**The verifier defaults to refusing.** An auth check that defaults to allowing is how this
endpoint got here.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core import OrderStore, Pipeline  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import make_app  # noqa: E402

BUDGET = "/internal/budget"
AT_LIMIT = {"message": {"data": ""}}


def build(verify_pubsub=None):
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
    kwargs = {} if verify_pubsub is None else {"verify_pubsub": verify_pubsub}
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter()),
        enqueue=lambda i: None,
        preview_fn=lambda f, batch: "",
        webhook_secret="whsec",
        tasks_token="tt",
        **kwargs,
    )
    from fastapi.testclient import TestClient

    return TestClient(app), store


def test_an_anonymous_post_is_refused():
    """The production defect, in one line."""
    c, _ = build(verify_pubsub=lambda auth: False)
    r = c.post(BUDGET, json={})
    assert r.status_code in (401, 403), f"{r.status_code} {r.text}"


def test_it_is_refused_before_the_body_is_parsed():
    """A body that would crash the parser must still produce 401/403, not 500.

    This is the difference between the review's finding and mine: they sent an empty body
    and saw a 500, which looks like a hardened endpoint failing safely and is in fact an
    unauthenticated one failing late."""
    c, _ = build(verify_pubsub=lambda auth: False)
    r = c.post(BUDGET, content=b"not json at all", headers={"content-type": "application/json"})
    assert r.status_code in (401, 403), f"{r.status_code} {r.text}"


def test_the_default_is_to_refuse():
    """No verifier wired at all — a misconfiguration — must close the endpoint, not open
    it. An auth check that defaults to allowing is how this endpoint got here."""
    c, _ = build()
    assert c.post(BUDGET, json={}).status_code in (401, 403)


def test_a_verified_caller_still_flips_the_switch():
    """Held-out check: refusing everything would also pass every test above. The budget
    alarm is the only thing standing between a runaway fal bill and the card."""
    c, store = build(verify_pubsub=lambda auth: True)
    import base64
    import json

    note = base64.b64encode(json.dumps({"alertThresholdExceeded": 1.0}).encode()).decode()
    r = c.post(BUDGET, json={"message": {"data": note}})
    assert r.status_code == 200, r.text
    assert r.json() == {"killswitch": True}
    assert store.killswitch is True


def test_a_verified_caller_below_the_threshold_leaves_it_alone():
    c, store = build(verify_pubsub=lambda auth: True)
    import base64
    import json

    note = base64.b64encode(json.dumps({"alertThresholdExceeded": 0.5}).encode()).decode()
    assert c.post(BUDGET, json={"message": {"data": note}}).json() == {"killswitch": False}
    assert store.killswitch is False


def test_the_authorization_header_is_what_gets_verified():
    """Google puts the JWT in `Authorization: Bearer <jwt>`. Passing anything else to the
    verifier means the real one will never see a token."""
    seen = []
    c, _ = build(verify_pubsub=lambda auth: seen.append(auth) or False)
    c.post(BUDGET, json={}, headers={"authorization": "Bearer abc.def.ghi"})
    assert seen == ["Bearer abc.def.ghi"], seen


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
