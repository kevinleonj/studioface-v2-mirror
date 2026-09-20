"""StudioFace v2 core domain logic.

No cloud SDKs here on purpose: every external system is a port (a callable or a
tiny protocol), so the whole money path is unit-testable offline and the same
code runs on Cloud Run with the real adapters injected.

State machine:
    paid -> generating -> delivered
                       -> failed_refunded        (refund confirmed by the provider)
                       -> failed_refund_pending  (refund requested, not yet confirmed)

Both terminal states are in the replay guard. A status outside it means a retried
Cloud Task refunds a second time.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import partial
from typing import Protocol

from app.guards import build_prompt

logger = logging.getLogger(__name__)


class ModelRefused(Exception):
    """The image model refused this input, and said why.

    Unit F2. Distinct from a model OUTAGE on purpose: a refusal is something the visitor
    can act on ("that is a cartoon, send a photograph of your face") and an outage is
    not. Both used to leave /api/preview as HTTP 500 with FastAPI's own body, which the
    frontend does not recognise, so both collapsed into one sentence.

    `detail` is a stable key the frontend maps to a Spanish sentence. It is derived from
    fal's `type` field, never from `msg`: fal's documentation says "Client code should
    not parse and rely on the msg field."
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


# Query form so the static export needs one /g/ page, not a route per order.
GALLERY_BASE = "https://studioface.app/g/"

# ---------------------------------------------------------------- utilities


def verify_stripe_signature(
    payload: bytes, header: str, secret: str, tolerance: int = 300, now: float | None = None
) -> bool:
    """Stripe 'Stripe-Signature' scheme: t=<ts>,v1=<hex hmac of "ts.payload">."""
    now = time.time() if now is None else now
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    ts, sig = parts.get("t"), parts.get("v1")
    if not ts or not sig:
        return False
    if abs(now - int(ts)) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def preview_token(batch: str, count: int, secret: str) -> str:
    """Binds a preview batch AND its file count to the server's secret, so the browser
    can hand the batch back at checkout without ever naming an object in the bucket."""
    return hmac.new(secret.encode(), f"{batch}:{count}".encode(), hashlib.sha256).hexdigest()[:32]


def delivery_token(order_id: str, secret: str) -> str:
    """Unguessable gallery URL. Replaces login/signup entirely."""
    return hmac.new(secret.encode(), order_id.encode(), hashlib.sha256).hexdigest()[:32]


# ---------------------------------------------------------------- ports


class ImageModel(Protocol):
    def edit(self, image_urls: list[str], prompt: str) -> str: ...  # returns image URL


class Storage(Protocol):
    def put(self, key: str, url: str) -> str: ...  # copies remote URL, returns own URL


@dataclass(frozen=True)
class Refund:
    """What the payment provider said when we asked for the money back. A refund is a
    request, not an outcome: Stripe returns "succeeded" for a card, but Bizum refunds
    are asynchronous and settle later on refund.updated / refund.failed."""

    id: str
    status: str


REFUND_CONFIRMED = "succeeded"
REFUND_FAILED = "failed"
# Terminal. Both must stay here: Cloud Tasks retries any non-2xx, and a status outside
# this tuple means the retry calls the refund a second time.
DONE_STATUSES = ("delivered", "failed_refunded", "failed_refund_pending")

# How long one worker may hold an order before another may take it over.
#
# "generating" is deliberately NOT a terminal status: an order stranded there by a
# killed container has to be recoverable, or the customer has paid and nothing ever
# delivers or refunds. But leaving it unguarded meant a Cloud Tasks retry arriving
# mid-run started a SECOND full generation — four more paid fal calls, and two runs
# each emailing the customer as they finished, so the first mail arrived while the
# other run was still going.
#
# A lease gets both: a fresh claim is left alone, a stale one is taken over. Four
# concurrent fal calls take one to three minutes, so ten leaves generous room without
# stranding an order for long.
LEASE_SECONDS = 600


@dataclass
class Order:
    id: str
    email: str
    source_image_urls: list[str]
    style: str
    amount_cents: int
    gclid: str | None = None
    status: str = "paid"
    outputs: list[str] = field(default_factory=list)
    attempts: int = 0
    refund_id: str | None = None
    refund_status: str | None = None
    # The garment the customer picked. None means "whatever the style always used",
    # so orders placed before the picker existed are unaffected. We never store, infer
    # or ask for their gender — see guards.WARDROBES.
    wardrobe: str | None = None
    # When a worker claimed this order. Read with LEASE_SECONDS to tell a run that is
    # still working from one whose container died.
    started_at: float | None = None


class OrderStore:
    """Stands in for one Firestore collection. Same three calls."""

    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}
        self._events: set[str] = set()
        self.killswitch: bool = False  # Firestore doc config/killswitch in prod

    def claim_event(self, event_id: str) -> bool:
        """Idempotency gate. Firestore: create() on doc id -> AlreadyExists."""
        if event_id in self._events:
            return False
        self._events.add(event_id)
        return True

    def put(self, order: Order) -> None:
        self._orders[order.id] = order

    def get(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def find_by_email(self, email: str) -> list[Order]:
        """Only used to resend a delivery link to the buyer's own address."""
        return [o for o in self._orders.values() if o.email.strip().lower() == email]


# ---------------------------------------------------------------- pipeline


def _attempt(job: Callable[[], str]) -> str | None:
    """One fal call. A dead provider must burn the retry budget, not the order, so the
    failure is logged with its traceback and reported as None rather than raised."""
    try:
        return job()
    except Exception:
        logger.exception("image generation attempt failed")
        return None


def sequential_batch(jobs: list[Callable[[], str]]) -> list[str | None]:
    return [_attempt(j) for j in jobs]


def threaded_batch(jobs: list[Callable[[], str]], max_workers: int = 4) -> list[str | None]:
    """Production runner: fal calls are blocking HTTP, so four threads turn four
    ~40 s generations into one. Executor.map keeps the results in submission order."""
    if not jobs:
        return []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(_attempt, jobs))


@dataclass
class Pipeline:
    store: OrderStore
    model: ImageModel
    storage: Storage
    send_email: Callable[[str, str], None]
    refund: Callable[[str, int], Refund | None]
    track_conversion: Callable[[Order], None]
    secret: str
    run_batch: Callable[[list[Callable[[], str]]], list[str | None]] = sequential_batch
    now: Callable[[], float] = time.time
    n_images: int = 4
    extra_attempts: int = 4  # order-level retry budget, NOT per image
    min_deliverable: int = 4

    def run(self, order_id: str) -> Order:
        order = self.store.get(order_id)
        if order is None:
            raise KeyError(order_id)
        if order.status in DONE_STATUSES:
            return order  # replay safety: never generate, email or refund twice
        if self._lease_held(order):
            # Another worker is on it and has not run out of time. Do nothing at all —
            # no fal calls, no email. The route turns this into a non-2xx so Cloud
            # Tasks backs off and comes again, by which point this order is either
            # finished (early return above) or the lease has expired and we take over.
            logger.info(
                "generation already claimed order_id=%s age=%.0fs",
                order.id,
                self.now() - (order.started_at or 0.0),
            )
            return order

        order.status = "generating"
        order.started_at = self.now()
        self.store.put(order)
        self._generate(order)

        if len(order.outputs) >= self.min_deliverable:
            order.status = "delivered"
            self.store.put(order)
            token = delivery_token(order.id, self.secret)
            self.send_email(order.email, f"{GALLERY_BASE}?o={order.id}&t={token}")
            self.track_conversion(order)
        else:
            self._refund(order)
            self.send_email(order.email, "REFUND")
        return order

    def _lease_held(self, order: Order) -> bool:
        """True while another worker is still plausibly working on this order."""
        if order.status != "generating" or order.started_at is None:
            return False
        return (self.now() - order.started_at) < LEASE_SECONDS

    def _refund(self, order: Order) -> None:
        """Ask for the money back and record what the provider actually said.

        Writing "failed_refunded" on the strength of the request alone was a lie for
        any asynchronous method: a Bizum refund that ends "failed" left the order
        claiming the customer had been paid back, with nothing in the log.
        """
        result = self.refund(order.id, order.amount_cents)
        if result is None:
            # A port that reports nothing gets the old behaviour. Production's adapter
            # always reports; tests/test_refund_status.py pins that.
            order.status = "failed_refunded"
            self.store.put(order)
            return
        order.refund_id, order.refund_status = result.id, result.status
        order.status = (
            "failed_refunded" if result.status == REFUND_CONFIRMED else "failed_refund_pending"
        )
        if result.status == REFUND_FAILED:
            # Nobody is watching this path: the pipeline refunds by itself.
            logger.error(
                "refund FAILED order_id=%s refund_id=%s cents=%s status=%s",
                order.id,
                result.id,
                order.amount_cents,
                result.status,
            )
        elif result.status != REFUND_CONFIRMED:
            logger.warning(
                "refund not confirmed order_id=%s refund_id=%s status=%s",
                order.id,
                result.id,
                result.status,
            )
        self.store.put(order)

    def _generate(self, order: Order) -> None:
        """Fill order.outputs in waves. Each wave asks for exactly the images still
        missing, capped by what is left of the order-level retry budget, and runs them
        through run_batch — concurrently in production, one at a time in tests."""
        budget = self.n_images + self.extra_attempts
        while len(order.outputs) < self.n_images and order.attempts < budget:
            wave = min(self.n_images - len(order.outputs), budget - order.attempts)
            order.attempts += wave
            jobs = [
                partial(
                    self.model.edit,
                    order.source_image_urls,
                    build_prompt(order.style, i, wardrobe=order.wardrobe),
                )
                for i in range(len(order.outputs), len(order.outputs) + wave)
            ]
            for got in self.run_batch(jobs):
                if got is None:
                    continue
                # Key assigned here, in the main thread, so parallel results cannot
                # race to the same object name and overwrite each other.
                key = f"{order.id}/{len(order.outputs)}.jpg"
                order.outputs.append(self.storage.put(key, got))
            self.store.put(order)
