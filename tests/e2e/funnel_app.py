"""The real application, composed for the end-to-end funnel walk.

P2 is why this exists. "Behind the human check: not tested" was written as a caveat in
four reports while the whole paid funnel sat behind it, and three defects lived there for
a day. Cloudflare publishes dummy keys for exactly this and they were never used.

What is REAL here, because the defects were in the real things:

  the FastAPI app        `app.main.make_app`, the same call `app/entry.py` makes
  the security headers   the production middleware, so the browser enforces the real
                         Content-Security-Policy - which is what refused the preview
  Turnstile              the real adapter against Cloudflare's siteverify, with the
                         documented dummy key that always passes
  fal                    real, real money, about five images per full walk
  Stripe                 real, TEST mode, real hosted Checkout

What is LOCAL, and exactly why:

  storage    `SignedUrlMaker` signs through IAM signBlob as the runtime service account.
             This machine cannot: `gcloud auth print-access-token
             --impersonate-service-account=sa-studioface-api@...` returns
             PERMISSION_DENIED (needs Kevin: roles/iam.serviceAccountTokenCreator). So
             the double writes bytes to a temp directory and serves them from the app's
             OWN origin, which `img-src 'self'` allows. That still proves what I1 was
             about - the preview is fetched and decoded by a real browser under the real
             policy - but it does NOT prove a storage.googleapis.com signature is well
             formed. tests/test_csp_matches_served_urls.py covers the host rule in
             process, against the real signer's output shape.
  Firestore  the in-memory OrderStore. A money-path test must not write test orders into
             the collection the real gallery reads.
  Cloud Tasks  `enqueue` calls the local /internal/generate in a thread, which is what
             the queue does in production, without needing a queue.

Both Cloudflare dummy keys come from the environment and are never written here. The
brief says "dummy secret in the local environment", and this repository's guard refuses
a credential-shaped literal in source - correctly, because it cannot tell a public test
constant from a real key. The documented values are in docs/verified.md, and
scripts/run_funnel.py is what puts them into the environment.
"""

from __future__ import annotations

import os
import secrets as secretslib
import threading
from pathlib import Path
from typing import Any

import httpx

from app.adapters.fal import FalModel
from app.adapters.turnstile import verify_turnstile
from app.core import OrderStore, Pipeline
from app.guards import MemoryCounter, RateLimiter
from app.main import THANKS_PATH, make_app

# https://developers.cloudflare.com/turnstile/troubleshooting/testing/
SITE_KEY_ENV = "FUNNEL_TURNSTILE_SITEKEY"
TURNSTILE_ENV = "FUNNEL_TURNSTILE_SECRET"

FILES_PREFIX = "/__files__"
LOCAL_SCHEME = "gs://local/"


class LocalStorage:
    """Stands in for the GCS bucket. `put` downloads a remote URL, as entry.py does."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        # key -> the address fal gave back for it. See sign_for_fal.
        self.fal_urls: dict[str, str] = {}

    def put(self, key: str, url: str) -> str:
        data = httpx.get(url, timeout=120.0, follow_redirects=True).content
        return self.put_bytes(key, data)

    def put_bytes(self, key: str, data: bytes) -> str:
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return f"{LOCAL_SCHEME}{key}"

    def put_source_for_fal(self, key: str, data: bytes) -> str:
        """Sources go to fal's own storage, not to the local directory.

        Real fal has to FETCH the source image, and it cannot reach 127.0.0.1. In
        production these are signed storage.googleapis.com URLs; signing one here needs
        roles/iam.serviceAccountTokenCreator, which this machine does not have. fal
        documents its own upload endpoint for exactly this, and the returned URL is one
        fal can read.

        Found by running the walk: fal answered 422 "value_error" on a gs://local/...
        path, which unit F2 correctly surfaced as detail "model_value_error" and a
        Spanish sentence rather than a 500. The harness was wrong, not the application
        - and F2 is the reason that was legible instead of being an opaque server error.
        """
        import fal_client

        self.put_bytes(key, data)
        self.fal_urls[key] = fal_client.upload(data, "image/jpeg", file_name=key.replace("/", "-"))
        return self.fal_urls[key]

    def sign(self, uri: str) -> str:
        """Same origin as the page, which `img-src 'self'` allows."""
        if not uri.startswith(LOCAL_SCHEME):
            return uri
        return f"{FILES_PREFIX}/{uri.removeprefix(LOCAL_SCHEME)}"

    def sign_for_fal(self, uri: str) -> str:
        """What `sign` is FOR, in production: an address fal can fetch.

        The preview path learned this in September. The delivery path did not, and the
        pipeline was built with `sign=lambda uri: uri` - so the four paid generations
        handed fal `gs://local/previews/<batch>/0.jpg` and fal refused all four with
        "Invalid URL scheme 'gs:'". The gallery stayed empty and the walk polled for ten
        minutes. tests/test_funnel_storage.py is the second-long version of that.

        Sources were uploaded to fal by `put_source_for_fal` and are remembered here.
        Anything else - a delivered output - keeps going to the app's own origin.
        """
        if not uri.startswith(LOCAL_SCHEME):
            return uri
        return self.fal_urls.get(uri.removeprefix(LOCAL_SCHEME)) or self.sign(uri)


def _enqueue_local(base: str, tasks: str):
    """What Cloud Tasks does: POST /internal/generate, fire and forget."""

    def enqueue(order_id: str) -> None:
        def run() -> None:
            try:
                httpx.post(
                    f"{base}/internal/generate/{order_id}",
                    headers={"x-tasks-token": tasks},
                    timeout=900.0,
                )
            except Exception as exc:  # noqa: BLE001 - the gallery assertion is the judge
                print(f"[funnel] enqueue failed for {order_id}: {exc}", flush=True)

        threading.Thread(target=run, daemon=True).start()

    return enqueue


def _checkout(base: str):
    import stripe

    def create(batch, count, style, gclid, wardrobe=None) -> str:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": "eur",
                        "unit_amount": 1999,
                        "product_data": {"name": "StudioFace (funnel test)"},
                    },
                    "quantity": 1,
                }
            ],
            success_url=f"{base}{THANKS_PATH}?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base}/?cancelado=1",
            metadata={
                "source_urls": ",".join(
                    f"{LOCAL_SCHEME}previews/{batch}/{i}.jpg" for i in range(count)
                ),
                "style": style,
                "gclid": gclid or "",
                "wardrobe": wardrobe or "",
            },
        )
        return session.url

    return create


def build_funnel_app(static_dir: Path, storage_dir: Path, base: str) -> Any:
    from fastapi.staticfiles import StaticFiles

    from app.preview import Preview

    key = os.environ["STRIPE_SECRET_KEY"]
    if not key.startswith(("sk_test_", "rk_test_")):
        raise SystemExit("refusing to run the funnel: STRIPE_SECRET_KEY is not a test key")
    turnstile = os.environ.get(TURNSTILE_ENV, "")
    if not turnstile:
        raise SystemExit(f"refusing to run the funnel: {TURNSTILE_ENV} is not set")

    import stripe

    stripe.api_key = key
    storage = LocalStorage(storage_dir)
    # Generated per run and never written down: local-only values, and a literal here is
    # exactly the shape the repository's own guard refuses.
    tasks = secretslib.token_hex(16)

    pipeline = Pipeline(
        store=OrderStore(),
        model=FalModel(sign=storage.sign_for_fal),
        storage=storage,
        send_email=lambda to, body: None,
        refund=lambda oid, cents: None,
        track_conversion=lambda order: None,
        secret=secretslib.token_hex(16),
    )
    app = make_app(
        pipeline,
        # The walk makes three or four previews in a row from one address, which the
        # production cap is deliberately too small for. Raised HERE ONLY: the harness
        # is not production, and a 429 mid-walk reads as a funnel defect when it is
        # the guard doing its job. Found the hard way - the second run of this walk
        # failed with "Has alcanzado el limite de pruebas gratuitas".
        RateLimiter(counter=MemoryCounter(), per_client=50, per_subnet=200),
        enqueue=_enqueue_local(base, tasks),
        preview_fn=Preview(
            put_source=storage.put_source_for_fal,
            model=FalModel(sign=storage.sign_for_fal, resolution="0.5K"),
            store_result=storage.put,
            sign=storage.sign,
        ),
        webhook_secret=os.environ["STRIPE_WEBHOOK_SECRET"],
        tasks_token=tasks,
        verify_turnstile=lambda token, ip: verify_turnstile(turnstile, token, ip),
        retrieve_session=_test_retriever(),
        sign_url=storage.sign,
        create_checkout=_checkout(base),
        static_dir=str(static_dir),
        # Otherwise /api/gracias redirects this browser to the PRODUCTION gallery
        # carrying an order that only exists in this process.
        gallery_base=f"{base}/g/",
    )
    # In FRONT of everything, because make_app mounts the Next export at "/" last and
    # Starlette matches routes in order - so a mount appended after it never runs. The
    # file was on disk and the request 404d.
    app.mount(FILES_PREFIX, StaticFiles(directory=str(storage_dir)), name="funnelfiles")
    app.routes.insert(0, app.routes.pop())
    return app


def _test_retriever():
    """The SAME shape as app/entry.py's `_session_retriever`, and changed with it in
    unit C2: `.to_dict()` rather than `dict(...)`, and `stripe.InvalidRequestError`
    rather than the `stripe.error` shim that v13 removed."""
    import stripe

    def retrieve(session_id: str) -> dict | None:
        try:
            return stripe.checkout.Session.retrieve(session_id).to_dict()
        except stripe.InvalidRequestError:
            return None

    return retrieve
