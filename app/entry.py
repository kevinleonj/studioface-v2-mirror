"""Production wiring: adapters only. The logic they feed is the tested code in
core/guards/main. Import is side-effect free — every environment variable is read
inside build(), so this module can be imported (and tested) without a GCP project.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import asdict, fields

from google.cloud import firestore, storage, tasks_v2

from app import emails
from app.adapters.fal import FalModel
from app.adapters.firestore_counter import FirestoreCounter
from app.adapters.ga4 import Ga4Purchase
from app.adapters.gcs import preview_resigner, signed_url_maker, source_uploader
from app.adapters.pubsub_push import pubsub_verifier
from app.adapters.turnstile import verify_turnstile
from app.config import Settings, hostname_of, stripe_mode
from app.core import REFUND_ALARM_THRESHOLD, Order, OrderStore, Pipeline, Refund, threaded_batch
from app.guards import DailyOrderCeiling, RateLimiter
from app.logs import configure_logging, id_prefix, log_call
from app.main import THANKS_PATH, make_app
from app.preview import Preview

logger = logging.getLogger(__name__)
_ORDER_FIELDS = frozenset(f.name for f in fields(Order))
RECOVERY_MAX_ORDERS = 20


def _enqueue_factory(s: Settings):
    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(s.project, s.region, s.tasks_queue)

    def enqueue(order_id: str) -> None:
        client.create_task(
            parent=parent,
            task={
                "http_request": {
                    "http_method": tasks_v2.HttpMethod.POST,
                    "url": f"{s.api_url}/internal/generate/{order_id}",
                    "headers": {"X-Tasks-Token": s.tasks_token},
                }
            },
        )
        logger.info("enqueued order_id=%s queue=%s", id_prefix(order_id), s.tasks_queue)

    return enqueue


def _gcs_storage(client: storage.Client, s: Settings):
    import httpx

    bucket = client.bucket(s.bucket_out)

    class Gcs:
        def put(self, key: str, url: str) -> str:
            started = time.monotonic()
            data = httpx.get(url, timeout=60).content
            bucket.blob(key).upload_from_string(data, content_type="image/jpeg")
            log_call(logger, "storage.put", started, detail=key)
            return f"gs://{bucket.name}/{key}"  # signed at read time by the gallery endpoint

    return Gcs()


def _resend(s: Settings):
    import resend

    resend.api_key = s.resend_api_key

    def send(to: str, body: str) -> None:
        """Both parts, always. The body used to be the bare gallery URL as the entire
        plain-text message: phishing to a person, bulk to a spam filter, arriving at
        the moment the customer decides whether paying us was wise."""
        message = emails.for_body(body)
        sent = resend.Emails.send(
            {
                "from": "StudioFace <fotos@studioface.app>",
                "to": [to],
                "subject": message.subject,
                "html": message.html,
                "text": message.text,
            }
        )
        # The id is what makes a delivery claim checkable afterwards against
        # GET https://api.resend.com/emails/<id>; "accepted" is not "delivered".
        logger.info(
            "email sent subject=%s resend_id=%s",
            message.subject,
            (sent or {}).get("id", "unknown"),
        )

    return send


PRICE_RETRIEVE_TIMEOUT_S = 5.0


def _price_is_live(s: Settings) -> bool:
    """Read-only GET of the configured Stripe Price, once, at startup.

    Task 21: /health's stripe_mode only reads the key's PREFIX (app.config.stripe_mode),
    so it stayed green through the exact outage state — a live key paired with a price
    still in test mode, which is exactly when checkout is broken — because nothing had
    ever asked Stripe what the price itself is. Retrieving a Price is a read-only GET:
    it costs nothing and sends no email.

    Never allowed to stop the container booting: no STRIPE_PRICE_EUR configured, a
    timed-out or failed call, or any other error all answer False, logged with the
    reason and never the key or the exception's own text (which could echo request
    detail back). An explicit timeout bounds the one blocking network call composition
    makes at startup, so a hung Stripe API can delay a cold start by at most
    PRICE_RETRIEVE_TIMEOUT_S, never hang it.
    """
    if not s.stripe_price_eur:
        logger.warning("stripe_price_live=false reason=no_price_configured")
        return False
    import stripe

    started = time.monotonic()
    try:
        # Everything that can fail lives inside this one try: setting up the client is
        # part of "the retrieval", and a test double or a future stripe-python release
        # missing RequestsClient must land on the same safe False as a network failure,
        # not raise past this function and take the container down with it.
        stripe.api_key = s.stripe_secret_key
        stripe.default_http_client = stripe.RequestsClient(timeout=PRICE_RETRIEVE_TIMEOUT_S)
        price = stripe.Price.retrieve(s.stripe_price_eur)
    except Exception as exc:  # noqa: BLE001 - a startup probe must never crash the container
        logger.warning("stripe_price_live=false reason=%s", type(exc).__name__)
        return False
    log_call(logger, "stripe.price.retrieve", started)
    live = bool(price.livemode)
    logger.info("stripe_price_live=%s", live)
    return live


def _session_retriever(s: Settings):
    """Ask Stripe whether a Checkout Session exists and was paid.

    Returns a plain dict so the HTTP layer never holds a Stripe object, and None when
    Stripe does not know the id - which is what /api/gracias turns into a 404.
    """
    import stripe

    stripe.api_key = s.stripe_secret_key

    def retrieve(session_id: str) -> dict | None:
        started = time.monotonic()
        try:
            # `.to_dict()`, not `dict(...)`. THIS LINE IS I2. stripe-python 15.0.0:
            # "StripeObject no longer inherits from dict, so any dict methods will no
            # longer exist", so `dict(session)` raises TypeError, which the except below
            # does not catch, which /api/gracias turned into a 404 for every paying
            # customer. The supported call is `.to_dict()`.
            found = stripe.checkout.Session.retrieve(session_id).to_dict()
            log_call(logger, "stripe.session.retrieve", started, order=id_prefix(session_id))
            return found
        except stripe.InvalidRequestError:
            # Stripe's answer for "no such session", including an id from the other mode:
            # test and live are separate object spaces (docs/verified.md, 19 Sep).
            return None

    return retrieve


def _checkout_factory(s: Settings):
    """Creates the hosted Checkout Session. The browser never names an object: the
    server rebuilds the gs:// keys from the batch id it signed at preview time."""
    import stripe

    stripe.api_key = s.stripe_secret_key

    def create(
        batch: str,
        count: int,
        style: str,
        gclid: str | None,
        wardrobe: str | None = None,
        gbraid: str | None = None,
        wbraid: str | None = None,
        ga_client_id: str | None = None,
        ga_session_id: str | None = None,
    ) -> str:
        if not s.stripe_price_eur:
            # Ships before STRIPE_PRICE_EUR reaches a Cloud Run revision; the route
            # turns this into a 503 rather than the container failing to start.
            raise RuntimeError("checkout_not_configured")
        sources = ",".join(f"gs://{s.bucket_src}/previews/{batch}/{i}.jpg" for i in range(count))
        started = time.monotonic()
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": s.stripe_price_eur, "quantity": 1}],
            # NOT the gallery directly: it also needs the HMAC delivery token, and
            # {CHECKOUT_SESSION_ID} is the only thing Stripe can substitute. THANKS_PATH
            # mints the token and redirects. See tests/test_after_payment.py.
            success_url=f"{s.public_url}{THANKS_PATH}?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{s.public_url}/?cancelado=1",
            metadata={
                "source_urls": sources,
                "style": style,
                "gclid": gclid or "",
                # The garment the customer picked, never anything about the customer.
                "wardrobe": wardrobe or "",
                # Read once at page load (gbraid/wbraid) or at checkout via gtag('get',
                # ...) (ga_client_id/ga_session_id), and carried through Stripe metadata
                # because the webhook that turns this session into an Order runs with
                # no browser in sight. See app/main.py:_order_from_session.
                "gbraid": gbraid or "",
                "wbraid": wbraid or "",
                "ga_client_id": ga_client_id or "",
                "ga_session_id": ga_session_id or "",
            },
        )
        logger.info("checkout session created batch=%s style=%s sources=%d", batch, style, count)
        log_call(logger, "stripe.checkout.create", started, batch=batch)
        return session.url

    return create


def _stripe_refund(s: Settings):
    import stripe

    stripe.api_key = s.stripe_secret_key

    def refund(order_id: str, amount_cents: int) -> Refund:
        """Returns what Stripe said, never None. A card refund comes back "succeeded";
        a Bizum one comes back "pending" and settles minutes later, so the caller has
        to be told which it got rather than assuming the money moved."""
        sess = stripe.checkout.Session.retrieve(order_id)
        # metadata.order_id is what lets the refund.updated / refund.failed webhook find
        # this order again. A Bizum refund settles minutes later and the event carries the
        # Refund, not the Session, so without this there is nothing tying the two together
        # short of a Firestore query and index on refund_id.
        r = stripe.Refund.create(
            payment_intent=sess.payment_intent,
            amount=amount_cents,
            metadata={"order_id": order_id},
        )
        logger.info(
            "refund requested order_id=%s refund_id=%s status=%s cents=%s",
            id_prefix(order_id),
            r.id,
            r.status,
            amount_cents,
        )
        return Refund(id=r.id, status=r.status)

    return refund


class FirestoreOrderStore(OrderStore):
    """Same interface as the tested in-memory store, backed by Firestore."""

    def __init__(self, client: firestore.Client) -> None:
        # Deliberately NOT super().__init__(): the parent seeds in-memory dicts this
        # class does not use, and its `self.killswitch = False` lands on the setter
        # below — which crashed before self.db existed, and on every later cold start
        # would have switched off a kill switch the budget alert had just switched on.
        self.db = client

    def claim_event(self, event_id: str) -> bool:
        from google.api_core.exceptions import AlreadyExists

        try:
            self.db.collection("events").document(event_id).create(
                {"at": firestore.SERVER_TIMESTAMP}
            )
            return True
        except AlreadyExists:
            return False

    @property
    def killswitch(self) -> bool:  # type: ignore[override]
        d = self.db.collection("config").document("killswitch").get()
        return bool(d.exists and d.to_dict().get("on"))

    @killswitch.setter
    def killswitch(self, on: bool) -> None:
        self.db.collection("config").document("killswitch").set({"on": on})

    def put(self, order: Order) -> None:
        """Whole-document write: the pipeline mutates one Order and re-puts it, and a
        replayed Cloud Task must land on the same document, not a second one."""
        self.db.collection("orders").document(order.id).set(asdict(order))
        logger.info(
            "order stored order_id=%s status=%s outputs=%d",
            id_prefix(order.id),
            order.status,
            len(order.outputs),
        )

    def find_by_email(self, email: str) -> list[Order]:
        """Equality on one field, so Firestore's single-field index covers it; no
        composite index to create. Bounded, because /api/recuperar mails every hit."""
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = (
            self.db.collection("orders")
            .where(filter=FieldFilter("email", "==", email))
            .limit(RECOVERY_MAX_ORDERS)
        )
        return [self._to_order(snap.to_dict() or {}) for snap in query.stream()]

    def get(self, order_id: str) -> Order | None:
        snap = self.db.collection("orders").document(order_id).get()
        if not snap.exists:
            return None
        return self._to_order(snap.to_dict() or {})

    @staticmethod
    def _to_order(data: dict) -> Order:
        # Only known fields: during a rollout an older revision reads documents a
        # newer one wrote, and an unexpected key must not take the service down.
        return Order(**{k: v for k, v in data.items() if k in _ORDER_FIELDS})

    def record_refund(self, order_id: str, reason: str, day: str) -> list[tuple[str, str]]:
        """Same contract as OrderStore.record_refund: read today's tally, append,
        and hand back the day's first REFUND_ALARM_THRESHOLD entries — every call,
        not only the one that first reaches the threshold.

        Read-then-write, same as the `killswitch` property above, not a Firestore
        transaction like FirestoreCounter's: two refunds landing in the same instant
        on two instances could under-count this list by one entry. That is still an
        acceptable race for task 41's original reason — this only decides WHICH
        orders the email names, never WHETHER to send it. Task 71 moved the
        "whether" decision (the part an under-count could double-send) off this
        read-then-write and onto Pipeline._alert_once's atomic Counter transaction —
        the fix this method used to promise (an `alarmed` flag read and written in
        two separate steps) but could not actually keep, because two instances can
        both read "not alarmed yet" before either one writes.
        """
        ref = self.db.collection("config").document(f"refund_tally_{day}")
        snap = ref.get()
        data = snap.to_dict() if snap.exists else {}
        entries = list(data.get("entries", [])) + [{"id": order_id, "reason": reason}]
        ref.set({"entries": entries[:REFUND_ALARM_THRESHOLD]})
        return [(e["id"], e["reason"]) for e in entries[:REFUND_ALARM_THRESHOLD]]


def build(settings: Settings | None = None) -> object:
    # F7/O10 first, before anything else can want to say something. Nothing configured
    # logging, so every logger.info in this repository went nowhere - which is why I2
    # was "cause unknown from outside".
    configure_logging()
    s = settings or Settings.from_env()
    # F/task 06: the payment mode visible without exposing anything else about the
    # key. logger.info, not print — module-level named logger, one line, once.
    mode = stripe_mode(s.stripe_secret_key)
    logger.info("stripe_mode=%s", mode)
    # Task 21: the check the key prefix alone cannot make — what Stripe itself says
    # about the configured price, retrieved once with an explicit timeout so a hung
    # call bounds a cold start rather than blocking it.
    price_live = _price_is_live(s)
    db = firestore.Client(project=s.project)
    gcs = storage.Client(project=s.project)
    sign_url = signed_url_maker(gcs)
    # Named, because unit C1 gave it a second caller: the preview stores its result
    # through the same bucket adapter the gallery's outputs go through. It was inline
    # before, and `storage.put` then resolved to the imported google.cloud.storage
    # MODULE, which has no `put` - the container would not start.
    out_bucket = _gcs_storage(gcs, s)
    pipeline = Pipeline(
        store=FirestoreOrderStore(db),
        model=FalModel(sign=sign_url),
        storage=out_bucket,
        send_email=_resend(s),
        refund=_stripe_refund(s),
        track_conversion=Ga4Purchase(
            measurement_id=s.ga4_measurement_id or "",
            api_secret=s.ga4_api_secret or "",
        ),
        run_batch=threaded_batch,  # four fal calls at once, not one after another
        secret=s.app_token_secret,
        owner_email=s.owner_alert_email,
        # Task 42: 20 paid orders per UTC day. Its own Firestore counter document
        # (key "orders:<day>"), never RateLimiter's own daily key below - a preview
        # costs nothing and this counts money actually taken.
        order_ceiling=DailyOrderCeiling(counter=FirestoreCounter(db)),
        # Task 71: once-per-UTC-day gate for every owner alert (the two ceilings
        # above and the refund-rate alarm), atomic across every Cloud Run instance
        # the same way order_ceiling's counter is — a separate FirestoreCounter
        # instance, but the same Firestore "counters" collection, so a key claimed
        # through this one is claimed for every other one too.
        alert_counter=FirestoreCounter(db),
    )
    limiter = RateLimiter(counter=FirestoreCounter(db), salt=s.app_token_secret)
    # Named so task 29's storage-only path (store_sources_fn=preview.store_only) shares
    # this exact `put_source` with the full preview (preview_fn=preview) — one adapter,
    # never two bucket writers that could drift apart.
    preview = Preview(
        put_source=source_uploader(gcs, s.bucket_src),
        model=FalModel(sign=sign_url, resolution="0.5K"),  # the free one is the cheap one
        # C1: the same two collaborators the gallery uses. `storage.put` downloads
        # fal's result into the private bucket; `sign_url` reads it back as a
        # short-lived storage.googleapis.com address, which img-src allows.
        store_result=out_bucket.put,
        sign=sign_url,
    )
    return make_app(
        pipeline,
        limiter,
        enqueue=_enqueue_factory(s),
        preview_fn=preview,
        store_sources_fn=preview.store_only,
        webhook_secret=s.stripe_webhook_secret,
        tasks_token=s.tasks_token,
        verify_turnstile=lambda token, ip: verify_turnstile(
            s.turnstile_secret, token, ip, hostname_of(s.public_url)
        ),
        # /internal/budget sets the kill switch. Unset config refuses everything.
        verify_pubsub=pubsub_verifier(s.pubsub_push_sa or "", s.pubsub_push_audience or ""),
        retrieve_session=_session_retriever(s),
        sign_url=sign_url,
        create_checkout=_checkout_factory(s),
        static_dir=s.static_dir,
        docs=s.enable_docs,
        stripe_mode=mode,
        stripe_price_live=price_live,
        # Task 30, preview-survives: the OUTPUT bucket, same as `out_bucket` above —
        # `Preview.__call__` writes the free-preview result there, never to bucket_src.
        resign_preview=preview_resigner(gcs, s.bucket_out, sign_url),
        # Task 51: OWNER_ALERT_EMAIL is wired through to Terraform and Cloud Run by
        # task 41; this is the only place that turns "is it configured" into a
        # reported fact for /health, and it never reports the address itself.
        owner_alerts=bool(s.owner_alert_email),
    )


app = build() if os.environ.get("GCP_PROJECT") else None
