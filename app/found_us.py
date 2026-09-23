"""Task 95e. "¿Cómo nos encontraste?": one optional answer, stored on a delivered order.

Asked on the gallery page after the photos are delivered, never earlier, so it can never
stand between a visitor and paying. The caller proves ownership with the same key the
gallery reads the order with (X-Gallery-Token), compared as bytes: hmac.compare_digest
raises on non-ASCII str, which would turn a forged header into a 500 (task 73).

The same answer twice leaves the same state; a different answer replaces the first.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from app.core import OrderStore, delivery_token
from app.logs import id_prefix

logger = logging.getLogger(__name__)

# The gallery offers exactly these, in this order (frontend/src/components/found-us.tsx);
# tests/test_found_us.py fails if the two lists drift.
FOUND_US = (
    "google",
    "chatgpt",
    "gemini",
    "claude",
    "copilot",
    "social",
    "recomendacion",
    "otro",
)


class FoundUsAnswer(BaseModel):
    answer: str


def register(app: FastAPI, store: OrderStore, signing: str) -> None:
    @app.post("/api/orders/{order_id}/found-us", status_code=204)
    def found_us(order_id: str, body: FoundUsAnswer, x_gallery_token: str = Header(default="")):
        expected = delivery_token(order_id, signing)
        if not hmac.compare_digest(x_gallery_token.encode(), expected.encode()):
            raise HTTPException(404)
        if body.answer not in FOUND_US:
            raise HTTPException(422, "unknown_answer")
        order = store.get(order_id)
        if order is None:
            raise HTTPException(404)
        if order.status != "delivered":
            raise HTTPException(409, "not_delivered")
        store.set_found_us(order_id, body.answer)
        logger.info("found_us stored order_id=%s answer=%s", id_prefix(order_id), body.answer)
