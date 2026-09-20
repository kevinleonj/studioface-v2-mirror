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


def test_one_purchase_event_with_the_order_id_as_transaction_id():
    track, http = tracker()
    track(an_order())
    body = http.calls[0]["json"]
    assert len(body["events"]) == 1
    event = body["events"][0]
    assert event["name"] == "purchase"
    assert event["params"]["transaction_id"] == "cs_test_a1b2"


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
