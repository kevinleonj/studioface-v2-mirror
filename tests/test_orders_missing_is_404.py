"""U3: the gallery reported `pending` for an order that does not exist.

Measured against production on 19 September, before the fix:

    $ curl "https://studioface.app/api/orders/cs_test_fake/44daae73dc96b181d5a7ff2cfc5af963"
    HTTP 200 {"status":"pending","images":[]}

A person who never paid saw an endless pending gallery. The token came from U2's oracle,
which is now closed — so from OUTSIDE this is no longer reachable, and that is why this
file is in-process: forging a valid token needs the signing secret.

## Why this was not a one-line change

The code that returned `pending` carried a real reason:

    # Stripe redirects the browser before it delivers the webhook, so for a few
    # seconds a good link points at an order that does not exist yet.

That is true, and making the route 404 without doing anything else hands a paying
customer "Este enlace no es válido o ha caducado" — a bug this repository has already
fixed once. The gallery's poller treats 404 as terminal and stops for good.

So the API tells the truth and the CLIENT absorbs the race: 404 means no such order, and
`/g/` keeps polling through 404s for a bounded window before it believes one. The
alternative — having `/api/gracias` write a placeholder order — was rejected because it
races the webhook for the same document and could overwrite a `generating` order with a
fresh `paid` one, which is a far worse failure than a slow spinner.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core import Order, OrderStore, Pipeline, delivery_token  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import make_app  # noqa: E402

SECRET = "app"
KNOWN = "cs_test_known"


def build():
    store = OrderStore()
    pipeline = Pipeline(
        store=store,
        model=type("M", (), {"edit": lambda self, u, p: "x"})(),
        storage=type("S", (), {"put": lambda self, k, u: k})(),
        send_email=lambda t, b: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret=SECRET,
    )
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter()),
        enqueue=lambda i: None,
        preview_fn=lambda f, batch: "",
        webhook_secret="whsec",
        tasks_token="tt",
        sign_url=lambda url: f"https://signed/{url}",
    )
    from fastapi.testclient import TestClient

    return TestClient(app), store


def url(order_id: str) -> str:
    return f"/api/orders/{order_id}/{delivery_token(order_id, SECRET)}"


def test_a_valid_token_for_an_order_that_does_not_exist_is_404():
    """The production defect, with the one token an outside caller cannot forge."""
    c, _ = build()
    r = c.get(url("cs_test_never_existed"))
    assert r.status_code == 404, f"{r.status_code} {r.text}"


def test_a_wrong_token_is_still_404_and_indistinguishable():
    """Both failures answer the same way, so the route cannot be used to ask whether an
    order id exists."""
    c, store = build()
    store.put(Order(KNOWN, "k@example.com", ["gs://a"], "corporativo", 1999))
    same = c.get(f"/api/orders/{KNOWN}/deadbeefdeadbeefdeadbeefdeadbeef")
    other = c.get(url("cs_test_never_existed"))
    assert same.status_code == other.status_code == 404
    assert same.json() == other.json(), "the two failures are distinguishable"


def test_a_real_order_still_reports_its_status():
    """Held-out check: 404 for everything would pass both tests above and break every
    real gallery."""
    c, store = build()
    store.put(Order(KNOWN, "k@example.com", ["gs://a"], "corporativo", 1999))
    r = c.get(url(KNOWN))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "paid"


def test_a_delivered_order_still_signs_its_images():
    c, store = build()
    order = Order(KNOWN, "k@example.com", ["gs://a"], "corporativo", 1999)
    order.status, order.outputs = "delivered", ["gs://out/1.jpg", "gs://out/2.jpg"]
    store.put(order)
    body = c.get(url(KNOWN)).json()
    assert body["status"] == "delivered"
    assert body["images"] == ["https://signed/gs://out/1.jpg", "https://signed/gs://out/2.jpg"]


def test_the_gallery_page_keeps_polling_through_a_404_for_a_bounded_window():
    """The client half, and the reason the server half is safe.

    Stripe redirects before the webhook lands, so a genuine buyer can meet a 404 for a
    few seconds. The poller must not treat the first one as final — and must not poll
    forever either, or a forged link spins on somebody's phone until they close it."""
    sys.path.insert(0, str(ROOT / "tests"))
    from source_scan import strip_comments

    page = strip_comments(
        (ROOT / "frontend" / "src" / "app" / "g" / "page.tsx").read_text(encoding="utf-8"),
        language="tsx",
    )
    assert "NOTFOUND_GRACE_MS" in page, "404 is still treated as terminal on the first one"
    assert "res.status === 404" in page
    import re

    grace = re.search(r"NOTFOUND_GRACE_MS\s*=\s*([\d_]+)", page)
    assert grace, "the grace window is not a named constant"
    assert 30_000 <= int(grace.group(1).replace("_", "")) <= 180_000, grace.group(1)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
