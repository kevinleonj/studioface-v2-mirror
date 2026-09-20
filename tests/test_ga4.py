"""GA4 Measurement Protocol purchase event — the tracking backstop.

Contract verified 2026-09-17 (docs/verified.md): POST to /mp/collect with
measurement_id and api_secret in the QUERY STRING, client_id and events in the body,
and purchase requires currency (ISO 4217), value (a number), transaction_id, items.

The protocol answers 2xx even for a malformed payload and never says what was wrong,
so nothing downstream can detect a mistake here. These tests are the only check the
payload shape has, which is exactly why they are this specific.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.adapters.ga4 import COLLECT_URL, Ga4Purchase  # noqa: E402
from app.core import Order  # noqa: E402


class FakeHttp:
    def __init__(self, status=204, error=None):
        self.calls, self.status, self.error = [], status, error

    def __call__(self, url, params=None, json=None, timeout=None):
        self.calls.append(dict(url=url, params=params, json=json, timeout=timeout))
        if self.error:
            raise self.error
        return type("R", (), {"status_code": self.status, "text": ""})()


def an_order(**kw):
    base = dict(
        id="cs_test_a1b2",
        email="k@example.com",
        source_image_urls=["gs://src/a.jpg"],
        style="corporativo",
        amount_cents=1999,
        status="delivered",
        outputs=["gs://out/0.jpg"] * 4,
    )
    return Order(**{**base, **kw})


def tracker(**kw):
    http = kw.pop("post", None) or FakeHttp()
    return Ga4Purchase(measurement_id="G-ABC123", api_secret="sek", post=http, **kw), http


# ---------------------------------------------------------------- the request


def test_credentials_go_in_the_query_string_not_the_body():
    track, http = tracker()
    track(an_order())
    call = http.calls[0]
    assert call["url"] == COLLECT_URL == "https://www.google-analytics.com/mp/collect"
    assert call["params"] == {"measurement_id": "G-ABC123", "api_secret": "sek"}
    assert "api_secret" not in call["json"]


def test_the_outbound_call_has_an_explicit_timeout():
    track, http = tracker()
    track(an_order())
    assert http.calls[0]["timeout"] is not None


# ---------------------------------------------------------------- the payload


def test_exactly_one_purchase_event_carrying_a_transaction_id():
    track, http = tracker()
    track(an_order())
    body = http.calls[0]["json"]
    assert len(body["events"]) == 1
    event = body["events"][0]
    assert event["name"] == "purchase"
    assert event["params"]["transaction_id"]


def test_value_is_euros_as_a_number_not_cents_and_not_a_string():
    """1999 cents is 19.99 EUR. Sending 1999 would report a thousandfold revenue."""
    track, http = tracker()
    track(an_order(amount_cents=1999))
    params = http.calls[0]["json"]["events"][0]["params"]
    assert params["value"] == 19.99
    assert isinstance(params["value"], float)
    assert params["currency"] == "EUR"


def test_items_are_present_and_carry_the_style():
    track, http = tracker()
    track(an_order(style="linkedin"))
    items = http.calls[0]["json"]["events"][0]["params"]["items"]
    assert len(items) == 1
    assert items[0]["item_id"] == "linkedin"
    assert items[0]["price"] == 19.99


def test_client_id_is_present_and_stable_for_the_same_order():
    """A web stream requires client_id. There is no browser here, so it is derived
    from the order id — stable across retries, so a replay cannot look like a new user."""
    track, http = tracker()
    track(an_order())
    track(an_order())
    ids = [c["json"]["client_id"] for c in http.calls]
    assert ids[0] == ids[1]
    assert ids[0]


def test_different_orders_get_different_client_ids():
    track, http = tracker()
    track(an_order(id="cs_1"))
    track(an_order(id="cs_2"))
    assert http.calls[0]["json"]["client_id"] != http.calls[1]["json"]["client_id"]


# ------------------------------------------------------- tying the sale to the visit


def test_transaction_id_is_never_the_gallery_order_id():
    """The gallery link (/g/?o=<order.id>) and the delivery email both carry order.id
    verbatim. Reusing it as the GA4 transaction_id would file the sale in Ads under an
    id anyone who ever saw that link also holds."""
    track, http = tracker()
    track(an_order(id="cs_test_a1b2", payment_intent="pi_realmoney"))
    txn = http.calls[0]["json"]["events"][0]["params"]["transaction_id"]
    assert txn != "cs_test_a1b2"
    assert txn == "pi_realmoney"


def test_transaction_id_falls_back_when_stripe_reported_no_payment_intent():
    """no_payment_required orders (a 100%-off coupon) have no PaymentIntent. The
    fallback still must not be the gallery order id, and must be stable so a Cloud
    Tasks retry of the same order reports the same transaction twice, not two sales."""
    track, http = tracker()
    track(an_order(id="cs_test_free", payment_intent=None))
    track(an_order(id="cs_test_free", payment_intent=None))
    first, second = (c["json"]["events"][0]["params"]["transaction_id"] for c in http.calls)
    assert first == second
    assert first != "cs_test_free"


def test_the_visitor_number_is_used_as_client_id_when_the_browser_reported_one():
    """order.ga_client_id is what gtag('get', ..., 'client_id') read in the browser
    that actually bought — using it instead of the server-derived id joins this
    purchase to the SAME visit GA4 already has, rather than inventing a new visitor."""
    track, http = tracker()
    track(an_order(ga_client_id="1122334455.6677889900"))
    assert http.calls[0]["json"]["client_id"] == "1122334455.6677889900"


def test_client_id_falls_back_to_the_derived_one_when_the_browser_reported_none():
    """gtag('get', ..., 'client_id') can come back undefined (docs/verified.md
    MP-5b) — an order placed with JavaScript blocked must still report a client_id,
    since a web stream MP event requires one."""
    track, http = tracker()
    track(an_order(ga_client_id=None))
    assert http.calls[0]["json"]["client_id"]


def test_the_visit_number_is_sent_as_the_session_id_event_param_when_present():
    """MP-2: session_id is an EVENT PARAM, not a top-level field."""
    track, http = tracker()
    track(an_order(ga_session_id="1758300000"))
    params = http.calls[0]["json"]["events"][0]["params"]
    assert params["session_id"] == "1758300000"


def test_no_session_id_param_when_the_browser_never_reported_one():
    """MP-5b: never send a value we do not have."""
    track, http = tracker()
    track(an_order(ga_session_id=None))
    params = http.calls[0]["json"]["events"][0]["params"]
    assert "session_id" not in params


# ---------------------------------------------------------------- when NOT to send


def test_nothing_is_sent_for_an_order_that_was_refunded():
    """GOAL.md: only on status delivered. Reporting a refunded order as revenue would
    teach Google Ads to buy more of the traffic that fails."""
    track, http = tracker()
    track(an_order(status="failed_refunded"))
    assert http.calls == []


def test_nothing_is_sent_while_the_order_is_still_generating():
    track, http = tracker()
    track(an_order(status="generating"))
    assert http.calls == []


def test_disabled_when_not_configured():
    """GA4_MEASUREMENT_ID is not in the Cloud Run environment yet."""
    track, http = tracker()
    track_off = Ga4Purchase(measurement_id="", api_secret="sek", post=http)
    track_off(an_order())
    assert http.calls == []


# ---------------------------------------------------------------- failure


def test_a_network_failure_never_breaks_delivery():
    """Held-out check: track_conversion runs AFTER the customer has been emailed. If
    it raised, /internal/generate would 500 and Cloud Tasks would retry a delivered
    order forever. Analytics is a backstop; it may not break the money path."""
    track, http = tracker(post=FakeHttp(error=RuntimeError("connection reset")))
    track(an_order())  # must not raise
    assert len(http.calls) == 1


def test_a_non_2xx_response_is_swallowed_too():
    track, http = tracker(post=FakeHttp(status=500))
    track(an_order())


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
