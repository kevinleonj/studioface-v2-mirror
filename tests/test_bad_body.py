"""Task 81: a body that is not a JSON object answers 422, never 500.

Measured from outside on 22 September 2026, 23:40 UTC: POST /api/checkout and
POST /api/recuperar with an unparsable body returned 500. Two ways in, both through
`await request.json()`:

  - the body will not parse at all       -> json.JSONDecodeError escapes  -> 500
  - the body parses but is not an object -> [].get / "x".get -> AttributeError -> 500

A 500 on a request a stranger fully controls is an error page for something that is not
an error on our side, and it buries the real 500s in the logs. Both answer 422 bad_body.

Every guard gets its pair: one case that must be refused, one that must get through.
"""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import OrderStore, Pipeline  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import make_app  # noqa: E402

APP_SECRET = "app_secret"

# A body that parses as JSON but is not an object. `5` and `"x"` and `[]` all reach
# body.get and all used to raise AttributeError.
NOT_OBJECTS = ("[]", '"x"', "5", "null", "true")
# A body that does not parse at all.
UNPARSABLE = ("", "{", "not json", "{'single': 'quotes'}")


def client():
    pipeline = Pipeline(
        store=OrderStore(),
        model=type("M", (), {"edit": lambda self, u, p: "https://fal/1.jpg"})(),
        storage=type("S", (), {"put": lambda self, k, u: f"gs://out/{k}"})(),
        send_email=lambda to, body: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret=APP_SECRET,
    )
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter()),
        enqueue=lambda i: None,
        preview_fn=lambda files, batch: "",
        webhook_secret="whsec",
        tasks_token="tt",
        retrieve_session=lambda session_id: {},
        sign_url=lambda url: url,
        create_checkout=lambda **kw: "https://checkout.stripe.com/x",
    )
    return TestClient(app, follow_redirects=False)


def _post(c, path, raw):
    return c.post(path, content=raw, headers={"content-type": "application/json"})


def test_checkout_refuses_an_unparsable_body_with_422():
    c = client()
    for raw in UNPARSABLE:
        r = _post(c, "/api/checkout", raw)
        assert r.status_code == 422, (raw, r.status_code, r.text)
        assert r.json()["detail"] == "bad_body", (raw, r.text)


def test_checkout_refuses_a_json_value_that_is_not_an_object():
    c = client()
    for raw in NOT_OBJECTS:
        r = _post(c, "/api/checkout", raw)
        assert r.status_code == 422, (raw, r.status_code, r.text)
        assert r.json()["detail"] == "bad_body", (raw, r.text)


def test_recuperar_refuses_an_unparsable_body_with_422():
    c = client()
    for raw in UNPARSABLE:
        r = _post(c, "/api/recuperar", raw)
        assert r.status_code == 422, (raw, r.status_code, r.text)
        assert r.json()["detail"] == "bad_body", (raw, r.text)


def test_recuperar_refuses_a_json_value_that_is_not_an_object():
    c = client()
    for raw in NOT_OBJECTS:
        r = _post(c, "/api/recuperar", raw)
        assert r.status_code == 422, (raw, r.status_code, r.text)
        assert r.json()["detail"] == "bad_body", (raw, r.text)


def test_a_real_object_still_reaches_the_handler_on_checkout():
    """Must get through: a proper object is judged on its contents, not its shape. A
    wrong handle is 403 bad_handle - the guard that was always there - not bad_body."""
    r = client().post("/api/checkout", json={"batch": "b", "n": 1, "t": "wrong"})
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "bad_handle", r.text


def test_a_real_object_still_reaches_the_handler_on_recuperar():
    """Must get through: bad_email, which only the handler can decide."""
    r = client().post("/api/recuperar", json={"email": "not-an-email"})
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == "bad_email", r.text


def test_an_empty_object_is_not_bad_body():
    """Nobody asked for this one. `{}` IS an object, so it must pass the shape guard and
    be refused by the handler's own rules - otherwise the guard is really a required-field
    check wearing the wrong name, and the 422 would say the wrong thing."""
    r = client().post("/api/recuperar", json={})
    assert r.json()["detail"] == "bad_email", r.text
