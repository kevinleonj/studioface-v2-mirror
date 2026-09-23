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

from app.guards import Counter, DailyOrderCeiling, MemoryCounter, build_prompt
from app.logs import id_prefix

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


class BillingRefused(Exception):
    """fal has locked the account for lack of credit, or refused for some other
    billing reason. Distinct from ModelRefused on purpose: a content refusal is the
    VISITOR's to fix; this one is ours, and no amount of retrying fixes it — every
    other call to the same account fails identically until Kevin adds credit.
    app/adapters/fal.py raises this instead of ModelRefused for that case, and
    docs/verified.md (22 Sep 2026) records that fal documents no stable status code
    or error `type` for it, so the detection there is a heuristic."""


class TurnstileUnavailable(Exception):
    """Cloudflare's siteverify endpoint timed out or could not be reached at all.

    This guard sits on the money path (/api/preview, before a visitor can ever reach
    checkout), so a Turnstile outage must fail CLOSED — refuse the preview with a 503
    a real visitor can be told about — rather than either letting everyone through
    (fail open, the thing this whole check exists to stop) or falling through to an
    unhandled 500 (which is what an uncaught network error did before this)."""


# o= and t= are appended as a FRAGMENT (#o=...&t=...), not a query, so the static
# export needs one /g/ page and the key is never sent to any server (task 31).
GALLERY_BASE = "https://studioface.app/g/"

# app/emails.py maps these two exact strings back to an Email. Two constants, not one
# shared import, because core.py has never imported emails.py (it has "no cloud SDKs
# ... on purpose") and this task is not the place to start that.
REFUND_EMAIL_SENTINEL = "REFUND"
OWNER_ALERT_PREFIX = "OWNER_ALERT:"
# Task 42, daily-money-stops: two more unattended stops, same sentinel convention as
# OWNER_ALERT_PREFIX above (app/emails.py's for_body sniffs a prefix, never a shared
# import into this no-cloud-SDK module).
DAILY_CEILING_ALERT_PREFIX = "OWNER_ALERT_CEILING:"
REFUND_ALARM_PREFIX = "OWNER_ALERT_REFUNDS:"
# Task 71, daily-cap-alert: the free-preview ceiling (RateLimiter.daily_global) used
# to fire silently -- under paid ad traffic that means ads keep spending while the
# shop has quietly stopped serving previews, with nobody told. Same sentinel
# convention as the other two OWNER_ALERT_* prefixes above.
DAILY_PREVIEW_CAP_ALERT_PREFIX = "OWNER_ALERT_PREVIEW_CAP:"
# Refunded orders in one UTC day that pages Kevin once -- a signal to go look, not to
# stop selling (Pipeline._tally_refund below never touches the kill switch).
REFUND_ALARM_THRESHOLD = 3

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
    # Google Ads splits click ids across three parameters depending on the click's
    # path: gclid (Search/Display), gbraid (app-to-web, iOS), wbraid (web-to-app,
    # Android). Read once at page load in the browser (frontend/src/lib/track.ts) and
    # carried through checkout so a future ads import can match this sale to its ad
    # click by whichever id the click actually produced.
    gbraid: str | None = None
    wbraid: str | None = None
    # GA4's own visitor and visit numbers, read in the browser with
    # gtag('get', GA4_ID, 'client_id' / 'session_id', callback). Verified on
    # production (docs/verified.md): both are returned even when cookies are refused
    # and stay the same across the consent transition. Carrying the real ones lets the
    # server-sent `purchase` join the SAME visit GA4 already has, instead of the
    # synthetic id Ga4Purchase derives when neither arrived.
    ga_client_id: str | None = None
    ga_session_id: str | None = None
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
    # The Stripe PaymentIntent, used ONLY as GA4's transaction_id. order.id is the
    # Checkout Session id, which is also the gallery's public order id — it sits in
    # the /g/ link this app puts in the delivery email, so it is not this order's to
    # spend as an analytics key too. None for a no_payment_required (100%-off) order,
    # which never gets a PaymentIntent from Stripe.
    payment_intent: str | None = None
    # Task 95e. The customer's answer to "¿Cómo nos encontraste?", asked on the gallery
    # page only after delivery (app/found_us.py). One of app.found_us.FOUND_US, or None.
    found_us: str | None = None


class OrderStore:
    """Stands in for one Firestore collection. Same three calls."""

    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}
        self._events: set[str] = set()
        self.killswitch: bool = False  # Firestore doc config/killswitch in prod
        # Task 42: today's refunded orders, keyed by UTC day, so the refund-rate
        # alarm can name which orders it is about. FirestoreOrderStore below keeps
        # the same shape in one Firestore transaction per call, same pattern as
        # claim_event's AlreadyExists gate just above.
        #
        # Task 71: this dict used to be paired with a `_refund_alarmed: set[str]`
        # here that decided "have I already emailed Kevin about today's refunds" --
        # a plain Python set living in ONE process. Cloud Run runs many instances and
        # replaces them freely, so that set was never shared and never survived a
        # restart: two instances could each independently reach the threshold and
        # each send its own alert, or a restart could forget the alert had already
        # fired. That decision now lives in Pipeline._alert_once, backed by the same
        # atomic, cross-instance Counter the ceilings already use -- this dict keeps
        # doing only what it is good at, remembering WHICH orders to name in the
        # email body, never WHETHER to send it.
        self._refund_tally: dict[str, list[tuple[str, str]]] = {}

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

    def set_found_us(self, order_id: str, answer: str) -> None:
        """Task 95e. One field only; the route has already checked the order exists."""
        self._orders[order_id].found_us = answer

    def record_refund(self, order_id: str, reason: str, day: str) -> list[tuple[str, str]]:
        """Append one refunded order to today's tally and hand back the day's first
        REFUND_ALARM_THRESHOLD entries, every time -- whether this is the 1st refund
        of the day or the 50th. This method only ever answers "what happened
        today"; whether THIS call is the one that pages Kevin is decided by the
        caller (Pipeline._tally_refund), atomically, via Pipeline._alert_once."""
        entries = self._refund_tally.setdefault(day, [])
        entries.append((order_id, reason))
        return list(entries[:REFUND_ALARM_THRESHOLD])

    def find_by_email(self, email: str) -> list[Order]:
        """Only used to resend a delivery link to the buyer's own address."""
        return [o for o in self._orders.values() if o.email.strip().lower() == email]


# ---------------------------------------------------------------- pipeline


def _attempt(job: Callable[[], str]) -> str | None:
    """One fal call. A dead provider must burn the retry budget, not the order, so the
    failure is logged with its traceback and reported as None rather than raised.

    BillingRefused is the one exception that is NOT swallowed here: every other call
    to a locked account fails identically, so burning the rest of the retry budget on
    it would only delay the refund. It propagates through run_batch to Pipeline._generate,
    which stops the order rather than counting this as one more wasted attempt.
    """
    try:
        return job()
    except BillingRefused:
        raise
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
    # Who to tell when fal locks the account for lack of credit. None is valid (an
    # unconfigured OWNER_ALERT_EMAIL skips the alert, same convention as ga4 in
    # app/config.py) — the refund and the kill switch happen either way.
    owner_email: str | None = None
    # Task 42: the daily-order-ceiling guard, shared across every Cloud Run instance
    # (its Counter is Firestore in production). None is valid — an unwired deployment
    # (or any test that does not care about this stop) simply never refuses an order
    # for being over a ceiling, same convention as owner_email=None above.
    order_ceiling: DailyOrderCeiling | None = None
    # Task 71: the once-per-UTC-day gate for every owner alert below (the paid-order
    # ceiling, the free-preview ceiling, the refund-rate alarm) -- the same shared
    # Counter type order_ceiling uses above, atomic across every Cloud Run instance
    # in production (Firestore transaction). Defaults to a fresh, process-local
    # MemoryCounter rather than None: unlike owner_email/order_ceiling, "no gate at
    # all" is never a safe default for something that decides whether Kevin gets
    # paged once or many times, so a deployment that forgets to wire this still gets
    # correct once-per-day behaviour for its own instance, and app/entry.py wires the
    # real Firestore-backed one shared with order_ceiling and the preview limiter.
    alert_counter: Counter = field(default_factory=MemoryCounter)

    def _alert_once(self, key: str) -> bool:
        """True the first, and only the first, time this key is claimed today.

        Backed by `Counter.increment_if_below(key, limit=1, ttl_s)` -- a
        check-and-increment inside one Firestore transaction in production, the
        exact mechanism DailyOrderCeiling and RateLimiter already trust for money.
        Of any number of Cloud Run instances racing on the same key in the same
        instant, exactly one call returns True; every other one, on this instance or
        any other, returns False. This is why it replaces a read-then-write: a read
        and a later write are two separate operations, and two instances can each do
        the read half before either does the write half, so a check like "does this
        document already say alarmed" can still be True for both of them.
        """
        return self.alert_counter.increment_if_below(key, 1, 86400)

    def note_daily_preview_cap(self, limit: int) -> None:
        """RateLimiter.check (app/guards.py) just refused a free preview for
        `daily_global` -- called from app/main.py's /api/preview the moment that
        happens. Under paid ad traffic this is the alert that matters most: the shop
        has quietly stopped serving previews while the ads that sent the traffic
        keep spending, and until now nothing told Kevin. Pages him once per UTC day,
        with the count, so he can pause ads; never touches the kill switch -- a
        preview costs nothing, so this is not a money stop like the order ceiling.
        """
        if not self.owner_email:
            return
        day = str(int(self.now() // 86400))
        if not self._alert_once(f"alert:preview_cap:{day}"):
            return
        self.send_email(self.owner_email, f"{DAILY_PREVIEW_CAP_ALERT_PREFIX}{limit}")

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
                id_prefix(order.id),
                self.now() - (order.started_at or 0.0),
            )
            return order

        order.status = "generating"
        order.started_at = self.now()
        self.store.put(order)
        if self._generate(order):
            self._handle_credit_exhausted(order)
            return order

        if len(order.outputs) >= self.min_deliverable:
            order.status = "delivered"
            self.store.put(order)
            token = delivery_token(order.id, self.secret)
            # Fragment, never a query: a fragment is a browser-only concept and is
            # never sent to any server, so it cannot reach an access log, a Referer or
            # an analytics request the way a query string does (task 31).
            self.send_email(order.email, f"{GALLERY_BASE}#o={order.id}&t={token}")
            self.track_conversion(order)
        else:
            self._refund(order)
            self.send_email(order.email, REFUND_EMAIL_SENTINEL)
        return order

    def _lease_held(self, order: Order) -> bool:
        """True while another worker is still plausibly working on this order."""
        if order.status != "generating" or order.started_at is None:
            return False
        return (self.now() - order.started_at) < LEASE_SECONDS

    def _refund(self, order: Order, reason: str = "undeliverable") -> None:
        """Ask for the money back and record what the provider actually said.

        Writing "failed_refunded" on the strength of the request alone was a lie for
        any asynchronous method: a Bizum refund that ends "failed" left the order
        claiming the customer had been paid back, with nothing in the log.

        `reason` is task 42's addition: every caller below names why (an ordinary
        undeliverable order, fal's credit lockout, the daily order ceiling), and
        `_tally_refund` is what turns today's reasons into Kevin's one refund-rate
        email — never a second mechanism, the same choke point every refund path
        already runs through.
        """
        result = self.refund(order.id, order.amount_cents)
        if result is None:
            # A port that reports nothing gets the old behaviour. Production's adapter
            # always reports; tests/test_refund_status.py pins that.
            order.status = "failed_refunded"
            self.store.put(order)
            self._tally_refund(order, reason)
            return
        order.refund_id, order.refund_status = result.id, result.status
        order.status = (
            "failed_refunded" if result.status == REFUND_CONFIRMED else "failed_refund_pending"
        )
        if result.status == REFUND_FAILED:
            # Nobody is watching this path: the pipeline refunds by itself.
            logger.error(
                "refund FAILED order_id=%s refund_id=%s cents=%s status=%s",
                id_prefix(order.id),
                result.id,
                order.amount_cents,
                result.status,
            )
        elif result.status != REFUND_CONFIRMED:
            logger.warning(
                "refund not confirmed order_id=%s refund_id=%s status=%s",
                id_prefix(order.id),
                result.id,
                result.status,
            )
        self.store.put(order)
        self._tally_refund(order, reason)

    def _tally_refund(self, order: Order, reason: str) -> None:
        """Task 42, refund-rate alarm. Counts every refund regardless of cause — the
        alarm is about the RATE of money going back out, not any one reason — and
        pages Kevin once, the moment the day's count first reaches
        REFUND_ALARM_THRESHOLD. Never touches the kill switch: three refunds is
        worth a look, not proof the shop should stop selling.

        Task 71: "the day's count first reaches the threshold" used to be decided by
        `store.record_refund` itself, with an in-process set (OrderStore's old
        `_refund_alarmed`) that a second Cloud Run instance never saw. The tally
        (which orders to name) still lives on the store; whether THIS call is the
        one that emails Kevin is now `_alert_once`, atomic across instances.
        """
        day = str(int(self.now() // 86400))
        entries = self.store.record_refund(order.id, reason, day)
        if len(entries) < REFUND_ALARM_THRESHOLD or not self.owner_email:
            return
        if not self._alert_once(f"alert:refunds:{day}"):
            return
        named = ",".join(f"{id_prefix(oid)}:{r}" for oid, r in entries)
        self.send_email(self.owner_email, f"{REFUND_ALARM_PREFIX}{named}")

    def _handle_credit_exhausted(self, order: Order) -> None:
        """fal has locked the account for lack of credit (docs/verified.md, 22 Sep
        2026: fal's own FAQ says outright "your account is locked and API requests
        will be rejected"). Nothing left in the retry budget would ever succeed, so
        _generate stops before spending it: refund THIS order through the exact same
        path and customer email as any other undeliverable one, then close the shop
        until Kevin restocks the balance and resets the switch by hand — there is no
        code path that turns it off again. The owner alert fires only on the
        transition from off to on, so a second order caught by the same outage
        refunds silently instead of paging Kevin twice for one incident.
        """
        self._refund(order, reason="fal_credit")
        self.send_email(order.email, REFUND_EMAIL_SENTINEL)
        already_on = self.store.killswitch
        self.store.killswitch = True
        logger.error(
            "fal credit exhausted order_id=%s status=%s killswitch_was_already_on=%s",
            id_prefix(order.id),
            order.status,
            already_on,
        )
        if not already_on and self.owner_email:
            self.send_email(self.owner_email, f"{OWNER_ALERT_PREFIX}1")

    def admit(self, order: Order) -> bool:
        """Task 42, daily order ceiling. Called from app/main.py's _fulfil_session —
        the one place a paid Stripe session becomes an Order — BEFORE the order is
        stored and generation is enqueued.

        True: a normal paid order, at or under order_ceiling.limit for today. The
        caller stores it and enqueues generation exactly as before this task.

        False: today's ceiling is already spent. Stripe has already taken this
        order's money, so there is nothing left to "refuse" except generating it:
        this refunds it through the exact same path and customer email as any other
        undeliverable order, then kills the switch (closing /api/checkout and
        /api/preview to every order after this one) and pages Kevin once per UTC
        day, so a human raises the ceiling or resets the switch on purpose rather
        than the shop grinding through the rest of the day on someone's ad budget.

        Task 71: the owner alert used to be gated on the kill switch's own
        off-to-on transition (`self.store.killswitch`, a plain Firestore read then a
        plain write in production, not a transaction) — two instances racing the
        21st order in the same instant could both read it "off" and both email
        Kevin. It is now `_alert_once`, the same atomic Counter every other alert in
        this file uses; the kill switch itself is unchanged, still set True every
        time so the shop stays closed until Kevin resets it by hand.

        No order_ceiling configured (None, the default): always admits — same
        convention as owner_email=None.
        """
        if self.order_ceiling is None or self.order_ceiling.admit():
            return True
        self._refund(order, reason="daily_ceiling")
        self.send_email(order.email, REFUND_EMAIL_SENTINEL)
        already_on = self.store.killswitch
        self.store.killswitch = True
        logger.error(
            "daily order ceiling reached order_id=%s limit=%s killswitch_was_already_on=%s",
            id_prefix(order.id),
            self.order_ceiling.limit,
            already_on,
        )
        day = str(int(self.now() // 86400))
        if self.owner_email and self._alert_once(f"alert:daily_ceiling:{day}"):
            self.send_email(
                self.owner_email, f"{DAILY_CEILING_ALERT_PREFIX}{self.order_ceiling.limit}"
            )
        return False

    def _generate(self, order: Order) -> bool:
        """Fill order.outputs in waves. Each wave asks for exactly the images still
        missing, capped by what is left of the order-level retry budget, and runs them
        through run_batch — concurrently in production, one at a time in tests.

        Returns True the moment fal refuses for lack of credit. Every other call to
        the same account would fail identically, so no further wave runs — the
        caller (Pipeline.run) refunds and stops selling instead of burning the rest
        of the retry budget finding that out four more times.
        """
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
            try:
                results = self.run_batch(jobs)
            except BillingRefused:
                self.store.put(order)
                return True
            for got in results:
                if got is None:
                    continue
                # Key assigned here, in the main thread, so parallel results cannot
                # race to the same object name and overwrite each other.
                key = f"{order.id}/{len(order.outputs)}.jpg"
                order.outputs.append(self.storage.put(key, got))
            self.store.put(order)
        return False
