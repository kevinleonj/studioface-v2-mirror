"""GA4 Measurement Protocol purchase event: the tracking backstop.

Backstop, because the browser's gtag purchase on the gallery page is the primary
signal and ad blockers eat a large share of it. This one leaves the server, so it
arrives whatever the browser did.

Contract verified 2026-09-17 (docs/verified.md): measurement_id and api_secret go in
the query string; client_id and events go in the body; purchase requires currency,
value, transaction_id and items. The endpoint answers 2xx even for a malformed
payload and never reports what was wrong, so nothing here can detect its own
mistakes at runtime — tests/test_ga4.py is the only check on the shape.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core import Order

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
            logger.info("ga4 not configured, purchase not reported order_id=%s", order.id)
            return
        value = round(order.amount_cents / 100, 2)
        payload = {
            "client_id": self._client_id(order.id),
            "events": [
                {
                    "name": "purchase",
                    "params": {
                        "transaction_id": order.id,
                        "value": value,
                        "currency": CURRENCY,
                        "items": [{"item_id": order.style, "price": value, "quantity": 1}],
                    },
                }
            ],
        }
        self._send(order, payload, value)

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
            logger.exception("ga4 purchase failed order_id=%s", order.id)
            return
        logger.info(
            "ga4 purchase sent order_id=%s value=%s status=%s",
            order.id,
            value,
            getattr(response, "status_code", "?"),
        )

    def _client_id(self, order_id: str) -> str:
        """No browser here, and a web stream requires a client_id. Derived from the
        order id so a retry is the same 'user', never a second one."""
        digest = hashlib.sha256(order_id.encode()).hexdigest()
        return f"{int(digest[:8], 16)}.{int(digest[8:16], 16)}"
