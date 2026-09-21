"""GA4 Measurement Protocol purchase event: the ONLY sender of `purchase`.

There is no browser-side `purchase` (docs/verified.md, line Ge / MP-6d and
docs/CONVERSION.md): a client-side event fired from the gallery page after a Stripe
redirect would be sent by the browser of someone who has just paid and is most likely
to close the tab, and Google does not document that GA4 deduplicates a gtag purchase
against a Measurement Protocol one sharing a transaction_id. One sender, from the
Stripe webhook, is the only way this number cannot be double-counted.

Contract verified 2026-09-17/19/20 (docs/verified.md): measurement_id and api_secret go
in the query string; client_id and events go in the body; purchase requires currency,
value, transaction_id and items. The endpoint answers 2xx even for a malformed
payload and never reports what was wrong, so nothing here can detect its own
mistakes at runtime — tests/test_ga4.py is the only check on the shape.

No `consent` object is sent (MP-6d, docs/verified.md, 2026-09-20): Google documents
omitting it as the default path — GA4 falls back to "the consent settings from
corresponding online interactions for the client... instance" — and nowhere
recommends building one for a server-sent event. That fallback is correct here
specifically because client_id now prefers the real browser id (order.ga_client_id)
over a synthetic one, so it resolves to the SAME client GA4 already holds a consent
state for.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core import Order
from app.logs import id_prefix

logger = logging.getLogger(__name__)

COLLECT_URL = "https://www.google-analytics.com/mp/collect"
TIMEOUT_S = 5.0
CURRENCY = "EUR"


def _default_post(url: str, params: dict, json: dict, timeout: float) -> Any:
    import httpx

    return httpx.post(url, params=params, json=json, timeout=timeout)


@dataclass
class Ga4Purchase:
    """Implements the track_conversion port: called once, only on delivery."""

    measurement_id: str
    api_secret: str = field(repr=False)
    post: Callable[..., Any] = field(default=_default_post)

    def __call__(self, order: Order) -> None:
        if order.status != "delivered":
            return  # a refunded order is not revenue
        if not self.measurement_id or not self.api_secret:
            logger.info(
                "ga4 not configured, purchase not reported order_id=%s", id_prefix(order.id)
            )
            return
        value = round(order.amount_cents / 100, 2)
        params = {
            "transaction_id": self._transaction_id(order),
            "value": value,
            "currency": CURRENCY,
            "items": [{"item_id": order.style, "price": value, "quantity": 1}],
        }
        # The visit number. MP-2 (docs/verified.md): session_id is an EVENT PARAM, not
        # a top-level field, and it is sent only when the browser actually reported
        # one (MP-5b: gtag can come back undefined under denied consent).
        if order.ga_session_id:
            params["session_id"] = order.ga_session_id
        payload = {
            # The visitor number. Prefers what the browser that bought actually
            # reported (gtag('get', ..., 'client_id')) over the synthetic id derived
            # below, so this purchase joins the SAME visit GA4 already has rather than
            # inventing a new visitor for a sale that happened in a real one.
            "client_id": order.ga_client_id or self._client_id(order.id),
            "events": [{"name": "purchase", "params": params}],
        }
        self._send(order, payload, value)

    def _transaction_id(self, order: Order) -> str:
        """Never order.id: that string is also the gallery's public order id, sitting
        in the /g/ link this app puts in the delivery email, so it is not free to
        spend as an analytics key too (docs/verified.md). Stripe's PaymentIntent is a
        different object naming the same payment; a no_payment_required order (a
        100%-off coupon) never gets one, so the fallback is a stable, non-reversible
        derivation of the order id — never the id itself."""
        if order.payment_intent:
            return order.payment_intent
        return f"txn_{hashlib.sha256(order.id.encode()).hexdigest()[:24]}"

    def _send(self, order: Order, payload: dict, value: float) -> None:
        """Analytics may never break the money path: this runs after the customer has
        already been emailed, so a raise here would make Cloud Tasks retry a delivered
        order. Failures are logged with their traceback and go no further."""
        try:
            response = self.post(
                COLLECT_URL,
                params={"measurement_id": self.measurement_id, "api_secret": self.api_secret},
                json=payload,
                timeout=TIMEOUT_S,
            )
        except Exception:
            logger.exception("ga4 purchase failed order_id=%s", id_prefix(order.id))
            return
        logger.info(
            "ga4 purchase sent order_id=%s value=%s status=%s",
            id_prefix(order.id),
            value,
            getattr(response, "status_code", "?"),
        )

    def _client_id(self, order_id: str) -> str:
        """No browser here, and a web stream requires a client_id. Derived from the
        order id so a retry is the same 'user', never a second one."""
        digest = hashlib.sha256(order_id.encode()).hexdigest()
        return f"{int(digest[:8], 16)}.{int(digest[8:16], 16)}"
