"""HTTP layer. Thin on purpose: every route delegates to core/guards.

Generation is NOT a FastAPI BackgroundTask. On Cloud Run with request-based
billing the CPU is throttled after the response is sent, so work started in a
BackgroundTask stalls. The webhook enqueues a Cloud Task instead; the task
calls POST /internal/generate, which runs inside a normal request and gets
retried by Cloud Tasks with backoff if it returns non-2xx.
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from app.core import (
    GALLERY_BASE,
    REFUND_CONFIRMED,
    ModelRefused,
    Order,
    Pipeline,
    delivery_token,
    preview_token,
    verify_stripe_signature,
)
from app.guards import (
    STYLES,
    WARDROBES,
    RateLimiter,
    default_wardrobe_key,
    validate_uploads,
)
from app.logs import id_prefix
from app.preview import PREVIEW_STYLE

# Module-level named logger, lazy %s formatting. The refund path is the one place this
# service moves money and then waits minutes to find out whether it worked, so its log
# line is the only account of what happened when somebody asks later.
logger = logging.getLogger(__name__)

# Resending a link mails an address the caller typed, so it gets its own ceiling.
RECOVER_PER_HOUR = 5
RECOVER_WINDOW_S = 3600

# NOT /healthz. Google Front End answers that exact path itself on every *.run.app
# host, before the request reaches the container, so a perfectly healthy revision
# fails its own smoke test. Sibling paths are untouched. See docs/verified.md.
HEALTH_PATH = "/health"

# Where Stripe sends the browser after payment. It cannot be the gallery directly:
# Stripe only substitutes {CHECKOUT_SESSION_ID}, and the gallery also needs the HMAC
# delivery token, which only this service can compute. So the redirect lands here.
THANKS_PATH = "/api/gracias"

# Stripe Checkout Session ids. Minting a token for anything else would widen this
# route from "the order namespace" to "any string".
SESSION_ID_PREFIX = "cs_"

# The only Stripe value that proves this one-time session was paid. Its siblings are
# `unpaid` and `no_payment_required`; the latter belongs to `setup` mode and to
# billing-cycle anchors, neither of which this product uses, so accepting it here would
# be a free gallery. Stripe's own object reference, docs/verified.md 19 Sep.
PAID_STATUS = "paid"

# Cache policy. Starlette's StaticFiles sets etag and last-modified and nothing else —
# it has no code path that emits cache-control — and production was measured serving
# both the HTML and the hashed JavaScript with no cache-control at all.
#
# RFC 9111 4.2.2 is what makes that a defect: with last-modified and no explicit
# freshness, "caches are encouraged to use a heuristic expiration value ... A typical
# setting of this fraction might be 10%". So any cache could keep serving a pre-deploy
# index.html without asking us.
#
# `no-cache` does not mean "do not store"; it means "revalidate before reuse", which
# with an etag costs a 304 rather than a re-download.
# ---------------------------------------------------------------- security headers
#
# The site served NONE of these. Measured with `curl -I https://studioface.app/`: the
# whole response carried content-type, accept-ranges, last-modified, etag, cache-control,
# a trace id, content-length, date and server. Nothing else.
#
# Every origin below comes from the vendor's own CSP documentation or from a measurement
# of what our pages actually request, both cited in docs/verified.md. Nothing is here
# "to be safe".
#
# STRIPE IS DELIBERATELY ABSENT. Stripe publishes a long list of CSP hosts and not one of
# them applies: Checkout runs as a REDIRECT, so the browser leaves this origin before any
# Stripe code runs, and no Stripe script is loaded on our pages at all. Copying their list
# would widen the policy for something that never executes here.
#
# 'unsafe-inline' in script-src is the known weak point and is not hidden. Next emits
# inline scripts - the RSC flight payload and the Consent Mode default - and this is a
# static export, so there is no per-request nonce to give them. The policy still refuses
# script from any origin not named below, which is the exfiltration path that matters.
TURNSTILE = "https://challenges.cloudflare.com"
GA_SCRIPT = "https://www.googletagmanager.com"
GA_COLLECT = ("https://*.google-analytics.com", "https://*.analytics.google.com")
SIGNED_IMAGES = "https://storage.googleapis.com"

# Google's CSP guide, https://developers.google.com/tag-platform/security/guides/csp,
# read 19 Sep 2026 (docs/verified.md). GA4 with Ads features, plus a Google Ads
# conversion tag. The guide writes `script-src-elem`; we send no `script-src-elem`, so
# CSP Level 3 falls these back to `script-src`.
ADS_SCRIPT = "https://www.googleadservices.com"
DOUBLECLICK = "https://*.g.doubleclick.net"  # covers googleads.g.doubleclick.net
DOUBLECLICK_AD = "https://ad.doubleclick.net"  # NOT covered by the wildcard above
# Ads serves part of the conversion tag from the search domain itself. The guide
# names this host literally in script-src-elem, so it stays literal here: a wildcard
# would be a wider script source than Google asks for.
ADS_SEARCH = "https://www.google.com"
SYNDICATION = "https://pagead2.googlesyndication.com"
# `https://*.google.<TLD>` in the guide is prose. `<TLD>` is not a domain; written
# literally it is a source that can never match and that fails silently. Ads sends the
# conversion ping via the visitor's local Google property, so we name the ones we serve.
GOOGLE_TLDS = ("https://*.google.com", "https://*.google.es")
GOOGLE_PIXELS = (GA_SCRIPT, ADS_SCRIPT, DOUBLECLICK, SYNDICATION, *GOOGLE_TLDS)

CSP = {
    "default-src": ["'self'"],
    "base-uri": ["'self'"],
    "object-src": ["'none'"],
    "frame-ancestors": ["'none'"],
    "form-action": ["'self'"],
    "script-src": ["'self'", "'unsafe-inline'", TURNSTILE, GA_SCRIPT, ADS_SCRIPT, ADS_SEARCH],
    "style-src": ["'self'", "'unsafe-inline'"],
    # Fonts are self-hosted: next/font/google inlines them at build time, so there is no
    # fonts.gstatic.com to allow. Measured, not assumed.
    "font-src": ["'self'"],
    # `blob:` is the upload thumbnails: URL.createObjectURL gives the visitor a picture
    # of each file they chose, and without this the browser refuses all four. Images
    # only - blob: in script-src would let the page run code it assembled itself.
    "img-src": [
        "'self'",
        "data:",
        "blob:",
        TURNSTILE,
        SIGNED_IMAGES,
        *GA_COLLECT,
        *GOOGLE_PIXELS,
    ],
    "connect-src": [
        "'self'",
        TURNSTILE,
        f"https://*.{TURNSTILE.split('//')[1]}",
        *GA_COLLECT,
        *GOOGLE_PIXELS,
        DOUBLECLICK_AD,
    ],
    "frame-src": [TURNSTILE, GA_SCRIPT],
}


def csp() -> str:
    return "; ".join(f"{name} {' '.join(values)}" for name, values in CSP.items())


SECURITY_HEADERS = {
    # MDN's recommended value. includeSubDomains is not decoration: api.studioface.app
    # is a subdomain and carries the Stripe webhook. No `preload` - that is a promise to
    # a hard-coded browser list that takes months to leave, not a header to add on spec.
    "strict-transport-security": "max-age=31536000; includeSubDomains",
    "x-content-type-options": "nosniff",
    "referrer-policy": "strict-origin-when-cross-origin",
    "content-security-policy": csp(),
}


REVALIDATE = "no-cache"
# Next names these with a SHA of their contents, so the URL changes whenever the bytes
# do. Anything NOT under this prefix — /muestras/ photographs, for instance — keeps its
# filename across a replacement and must never be pinned for a year.
HASHED_PREFIX = "/_next/static/"
IMMUTABLE = "public, max-age=31536000, immutable"
# /muestras/* and the share image: no hash in the filename, so not immutable, but a
# crawler fetches og:image once and a search engine re-crawls on its own schedule, so
# a full day of caching is free bandwidth (page-head unit).
ONE_DAY = "public, max-age=86400"
DAY_CACHED_PREFIXES = ("/muestras/", "/share.jpg")


class CachedStatic(StaticFiles):
    """StaticFiles that states its caching intent instead of leaving it to heuristics."""

    async def get_response(self, path, scope):  # type: ignore[override]
        response = await super().get_response(path, scope)
        if isinstance(response, RedirectResponse):
            # Starlette's own directory-to-trailing-slash redirect (starlette/
            # staticfiles.py) is a 307, TEMPORARY, by construction: no browser or CDN
            # may cache it, so every visit to a bare directory path such as
            # /legal/privacidad paid for it again. The address always means the same
            # thing, so this is a single 308 PERMANENT redirect. 308 over 301: RFC
            # 9110 15.4.9 guarantees the method and body replay unchanged, which 301
            # does not - free here since this route only ever serves GET/HEAD.
            return RedirectResponse(response.headers["location"], status_code=308)
        return response

    def file_response(self, *args, **kwargs):  # type: ignore[override]
        response = super().file_response(*args, **kwargs)
        path = args[2].get("path", "") if len(args) > 2 else ""
        if not path.startswith("/"):
            path = f"/{path}"
        prefix = HASHED_PREFIX.strip("/")
        if path.startswith(f"/{prefix}"):
            response.headers["cache-control"] = IMMUTABLE
        elif path.startswith(DAY_CACHED_PREFIXES):
            response.headers["cache-control"] = ONE_DAY
        else:
            response.headers["cache-control"] = REVALIDATE
        return response


# batch, count, style, gclid, wardrobe, gbraid, wbraid, ga_client_id, ga_session_id -> url
CreateCheckout = Callable[
    [str, int, str, str | None, str | None, str | None, str | None, str | None, str | None], str
]


@dataclass
class Deps:
    pipeline: Pipeline
    limiter: RateLimiter
    enqueue: Callable[[str], None]  # Cloud Tasks client in prod
    preview_fn: Callable[[list[bytes], str], str]
    webhook_secret: str
    tasks_token: str
    verify_turnstile: Callable[[str, str], bool] = lambda token, ip: True
    # Takes the raw Authorization header. Defaults to REFUSING: this endpoint sets the
    # kill switch, and an auth check that defaults to allowing is exactly how it came to
    # have none at all. A misconfiguration must close it, not open it.
    verify_pubsub: Callable[[str], bool] = lambda authorization: False
    # Returns the Checkout Session as Stripe has it, or None. Defaults to None so an
    # unwired or broken Stripe client CLOSES /api/gracias rather than opening it.
    retrieve_session: Callable[[str], dict | None] = lambda session_id: None
    sign_url: Callable[[str], str] = lambda url: url
    create_checkout: CreateCheckout | None = None
    # Where this deployment's gallery lives. A constant until 20 September, when the
    # paid walk redirected a browser off loopback to the production gallery holding an
    # order that existed only locally (tests/test_after_payment.py).
    gallery_base: str = GALLERY_BASE
    # "test", "live" or "unknown" — app.config.stripe_mode(key), derived from the
    # configured Stripe key's PREFIX only. Never the key itself.
    stripe_mode: str = "unknown"


def make_app(
    pipeline: Pipeline,
    limiter: RateLimiter,
    enqueue: Callable[[str], None],
    preview_fn: Callable[[list[bytes], str], str],
    webhook_secret: str,
    tasks_token: str,
    verify_turnstile: Callable[[str, str], bool] = lambda token, ip: True,
    verify_pubsub: Callable[[str], bool] = lambda authorization: False,
    retrieve_session: Callable[[str], dict | None] = lambda session_id: None,
    sign_url: Callable[..., str] = lambda url, filename=None: url,
    create_checkout: CreateCheckout | None = None,
    static_dir: str | None = None,
    gallery_base: str = GALLERY_BASE,
    # F8. Fail closed: a composition root that forgets this flag gets no published
    # schema. scripts/demo_server.py asks for it explicitly, and app/entry.py passes
    # Settings.enable_docs, which is False unless ENABLE_DOCS is set.
    docs: bool = False,
    stripe_mode: str = "unknown",
) -> FastAPI:
    d = Deps(
        pipeline,
        limiter,
        enqueue,
        preview_fn,
        webhook_secret,
        tasks_token,
        verify_turnstile,
        verify_pubsub,
        retrieve_session,
        sign_url,
        create_checkout,
        gallery_base,
        stripe_mode,
    )
    # F8/O9. /docs, /redoc and /openapi.json publish every route, parameter and
    # response shape of the money path - including /internal/generate/{order_id} and
    # the exact query parameter /api/gracias reads. Off unless asked, so the one place
    # nobody sets the flag is the one place it stays shut.
    app = FastAPI() if docs else FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    # Neither Cloud Run nor StaticFiles compresses anything by itself, so the JS and
    # CSS of the static export went over the wire raw: Lighthouse mobile measured
    # 2.1 s of savings. Clients that do not send accept-encoding are unaffected.
    app.add_middleware(GZipMiddleware, minimum_size=500)

    @app.middleware("http")
    async def security_headers(request, call_next):
        """On every response, including the static export and every error.

        A header set only on the API would leave the page a visitor actually loads
        unprotected, which is where a CSP does its work."""
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    _register_preview(app, d)
    _register_checkout(app, d)
    _register_recovery(app, d)
    _register_thanks(app, d)
    _register_public(app, d)
    _register_internal(app, d)
    _register_budget(app, d)
    if static_dir and os.path.isdir(static_dir):
        # The Next.js static export. Mounted LAST so /api, /internal and /health win.
        # html=True serves index.html for "/" and for directory paths like /g/.
        app.mount("/", CachedStatic(directory=static_dir, html=True), name="web")
    return app


def visitor_address(x_forwarded_for: str, request: Request) -> str:
    """The address to key a per-visitor limit on.

    X-Forwarded-For grows client-first: "visitor, hop1, hop2, ...". The FIRST entry
    is whatever the connecting client put in its own request - any script can set
    that header freely - so keying on it let a visitor prepend a fresh fake address
    on every call and dodge the cap entirely. Google Front End (GFE) is the single
    hop between the public internet and this container (docs/verified.md 13c: "GFE
    -> HTTP proxy -> app server") and, per the ordinary X-Forwarded-For convention,
    appends the address it actually observed the connection from - so the LAST
    entry is the one no visitor can forge, only pad in front of. (docs/verified.md
    13c is explicit that no Cloud Run page states outright that Cloud Run sets this
    header; using the trailing entry is this task's own inference from the
    documented single-hop ingress path, not a vendor claim.)

    An absent, empty, or malformed (e.g. trailing-comma) header falls back to the
    raw socket peer, same as before this function existed.
    """
    last = x_forwarded_for.split(",")[-1].strip()
    return last or _client_ip(request)


def _register_preview(app: FastAPI, d: Deps) -> None:
    @app.post("/api/preview")
    async def preview(request: Request, x_forwarded_for: str = Header(default="")):
        if d.pipeline.store.killswitch:
            raise HTTPException(503, "paused")
        ip = visitor_address(x_forwarded_for, request)
        form = await request.form()
        if not d.verify_turnstile(str(form.get("turnstile_token", "")), ip):
            raise HTTPException(403, "turnstile")
        ok, why = d.limiter.check(ip, request.headers.get("user-agent", ""))
        if not ok:
            raise HTTPException(429, why)
        files = [await f.read() for f in form.getlist("files")]
        try:
            v = validate_uploads(files)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        # The batch id is minted here and signed: it is the only thing the browser is
        # allowed to hand back at checkout, so it can never name an object itself.
        batch, n = uuid4().hex, len(v.accepted)
        try:
            url = d.preview_fn([b for _, b in v.accepted], batch)
        except (ModelRefused, ValueError) as e:
            # F2. Both of these are things the VISITOR got wrong and can fix, and both
            # used to leave here as HTTP 500 with FastAPI's own body - which the frontend
            # does not recognise, so both read as "No hemos podido generar la prueba."
            # `normalise_all` raises ValueError from inside preview_fn, outside the
            # try/except above, which is why a corrupt file was a 500 as well.
            detail = e.detail if isinstance(e, ModelRefused) else str(e)
            logger.info("preview refused batch=%s detail=%s", batch, detail)
            raise HTTPException(422, detail) from e
        return {
            "preview_url": url,
            "batch": batch,
            "n": n,
            # F6. The preview is always made with the style's own garment, because the
            # wardrobe selector does not exist until this response arrives. Saying which
            # one lets the page tell the customer when their choice differs, instead of
            # showing them one outfit and selling them another.
            "wardrobe": default_wardrobe_key(PREVIEW_STYLE),
            "t": preview_token(batch, n, d.pipeline.secret),
        }


def _register_checkout(app: FastAPI, d: Deps) -> None:
    @app.post("/api/checkout")
    async def checkout(request: Request):
        if d.pipeline.store.killswitch:
            # Generation is paused; taking more money for it would be fraud.
            raise HTTPException(503, "paused")
        if d.create_checkout is None:
            raise HTTPException(503, "checkout_not_configured")
        body = await request.json()
        batch, count = str(body.get("batch", "")), int(body.get("n", 0))
        expected = preview_token(batch, count, d.pipeline.secret)
        if not batch or not hmac.compare_digest(expected, str(body.get("t", ""))):
            raise HTTPException(403, "bad_handle")
        style = str(body.get("style", "corporativo"))
        if style not in STYLES:
            raise HTTPException(422, "unknown_style")
        # The garment, never the person. An unknown key is refused here rather than
        # falling back, because the alternative is selling someone clothes they did not
        # choose and letting them find out after paying.
        wardrobe = body.get("wardrobe") or None
        if wardrobe is not None and wardrobe not in WARDROBES:
            raise HTTPException(422, "unknown_wardrobe")
        try:
            url = d.create_checkout(
                batch,
                count,
                style,
                body.get("gclid") or None,
                wardrobe,
                body.get("gbraid") or None,
                body.get("wbraid") or None,
                body.get("ga_client_id") or None,
                body.get("ga_session_id") or None,
            )
        except RuntimeError as e:
            raise HTTPException(503, str(e)) from e
        return {"url": url}


def _register_recovery(app: FastAPI, d: Deps) -> None:
    @app.post("/api/recuperar")
    async def recuperar(request: Request, x_forwarded_for: str = Header(default="")):
        body = await request.json()
        email = str(body.get("email", "")).strip().lower()
        if "@" not in email or "." not in email.split("@")[-1]:
            raise HTTPException(422, "bad_email")
        ip = visitor_address(x_forwarded_for, request)
        if not d.limiter.check_named("rec", ip, RECOVER_PER_HOUR, RECOVER_WINDOW_S):
            raise HTTPException(429, "recover_cap")
        for order in d.pipeline.store.find_by_email(email):
            if order.status != "delivered":
                continue
            token = delivery_token(order.id, d.pipeline.secret)
            d.pipeline.send_email(order.email, f"{d.gallery_base}?o={order.id}&t={token}")
        # Always the same answer: a different one would reveal whether this address
        # ever bought anything.
        return {"sent": True}


PAID_BUT_BROKEN = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Tu pago se ha recibido — StudioFace</title></head>
<body style="font-family:system-ui,sans-serif;max-width:34rem;margin:3rem auto;padding:0 1rem">
<h1>Tu pago se ha recibido</h1>
<p>No hemos podido abrir tu galer&iacute;a en este momento. Tus fotos se est&aacute;n
preparando y te enviaremos el enlace por correo en cuanto est&eacute;n listas.</p>
<p>Si no te llega, puedes recuperarlo aqu&iacute;:
<a href="/recuperar/">Recuperar mis fotos</a>.</p>
<p>Escr&iacute;benos a <a href="mailto:hola@studioface.app">hola@studioface.app</a> si
necesitas ayuda.</p>
</body></html>"""


def _paid_but_broken() -> HTMLResponse:
    """C2(c). 502, HTML, in Spanish, with a way out.

    Somebody who has just paid must never meet `{"detail":"Not Found"}`. 502 rather than
    404 because the payment happened and this is our failure, not a missing thing, and
    because a 404 here is indistinguishable from the refusal above - which is exactly how
    I2 hid for a day.
    """
    return HTMLResponse(PAID_BUT_BROKEN, status_code=502)


def _register_thanks(app: FastAPI, d: Deps) -> None:
    @app.get(THANKS_PATH)
    def gracias(session_id: str = ""):
        """Stripe's success_url. Turns the one identifier Stripe can hand back into the
        gallery link, which needs the delivery token too.

        This used to mint that token for ANY string starting `cs_`, deterministically,
        without asking Stripe anything. Measured 19 Sep:

            GET /api/gracias?session_id=cs_test_fake
            302 -> /g/?o=cs_test_fake&t=REDACTED

        Since `delivery_token` is what gates /api/orders, the route was a token-minting
        oracle for the whole order namespace: supply an id, receive its token. The old
        docstring said it "gives nothing to a caller who does not already hold the session
        id", which was true and beside the point - the caller chooses the id.

        Now Stripe decides. The prefix check stays as a cheap first gate so a string that
        cannot be a session id never costs a network call."""
        if not session_id.startswith(SESSION_ID_PREFIX):
            raise HTTPException(404)
        try:
            session = d.retrieve_session(session_id)
        except Exception:
            # I2: this used to be `raise HTTPException(404)`. A TypeError from the Stripe
            # client became "no such session", and the person who had just paid got
            # `{"detail":"Not Found"}`. A refusal and a breakage are different answers.
            logger.exception("gracias: session lookup failed for %s", id_prefix(session_id))
            return _paid_but_broken()
        if not session or session.get("payment_status") not in FULFILLABLE:
            logger.info(
                "gracias: refused session_id=%s payment_status=%s",
                id_prefix(session_id),
                (session or {}).get("payment_status"),
            )
            raise HTTPException(404)
        try:
            # Stripe redirects before it delivers the webhook, so the order often does
            # not exist yet and the gallery 404s. Fulfilling here as well is what Stripe
            # asks for, and the claim guard makes the later webhook a no-op.
            _fulfil_session(d, session)
        except Exception:
            logger.exception("gracias: fulfilment failed for %s", id_prefix(session_id))
            # Only a dead end if there is nothing behind the door. If the webhook already
            # created the order, this customer's gallery is waiting for them and the
            # failure is ours to read in the log, not theirs to look at.
            if d.pipeline.store.get(session_id) is None:
                return _paid_but_broken()
        token = delivery_token(session_id, d.pipeline.secret)
        return RedirectResponse(f"{d.gallery_base}?o={session_id}&t={token}", status_code=302)


def _download_url(d: Deps, uri: str, n: int) -> str:
    """The same object, signed to be saved as studioface-<n>.jpg."""
    try:
        return d.sign_url(uri, f"studioface-{n}.jpg")
    except TypeError:
        # A one-argument signer: keep today's behaviour rather than failing the gallery.
        return d.sign_url(uri)


def _register_public(app: FastAPI, d: Deps) -> None:
    @app.get(HEALTH_PATH)
    def health():
        return {
            "ok": True,
            "killswitch": d.pipeline.store.killswitch,
            "stripe_mode": d.stripe_mode,
        }

    @app.post("/api/stripe/webhook")
    async def webhook(request: Request, stripe_signature: str = Header(default="")):
        body = await request.body()
        if not verify_stripe_signature(body, stripe_signature, d.webhook_secret):
            raise HTTPException(400, "bad_signature")
        event = await request.json()
        return _handle_event(d, event)

    @app.get("/api/orders/{order_id}/{token}")
    def status(order_id: str, token: str):
        if not hmac.compare_digest(token, delivery_token(order_id, d.pipeline.secret)):
            raise HTTPException(404)
        order = d.pipeline.store.get(order_id)
        if order is None:
            # This used to answer `pending`, so somebody who never paid saw an endless
            # pending gallery (measured 19 Sep, with a token /api/gracias handed out for
            # free). The route now says what is true: there is no such order.
            #
            # Stripe still redirects the browser BEFORE it delivers the webhook, so a
            # genuine buyer can meet this 404 for a few seconds. That race is absorbed by
            # the client, which polls through 404s for a bounded window - see
            # NOTFOUND_GRACE_MS in frontend/src/app/g/page.tsx. Writing a placeholder
            # order here instead would race the webhook for the same document and could
            # overwrite a `generating` order with a fresh `paid` one, which is far worse
            # than a few seconds of spinner.
            raise HTTPException(404)
        # Signed only on delivery: the objects are private, the links live 15 minutes,
        # and signing earlier would hand out URLs for objects that do not exist yet.
        delivered = order.status == "delivered"
        images = [d.sign_url(u) for u in order.outputs] if delivered else []
        # F3. A second address per image, signed to be SAVED rather than displayed.
        # `attachment` tells the browser not to render, so it cannot be the same address
        # the gallery shows - and a signer that takes one argument (every existing test
        # double) degrades to today's behaviour instead of crashing.
        downloads = (
            [_download_url(d, u, i) for i, u in enumerate(order.outputs, 1)] if delivered else []
        )
        return {"status": order.status, "images": images, "downloads": downloads}


def _register_internal(app: FastAPI, d: Deps) -> None:
    @app.post("/internal/generate/{order_id}")
    def generate(order_id: str, x_tasks_token: str = Header(default="")):
        if x_tasks_token != d.tasks_token:
            raise HTTPException(403)
        order = d.pipeline.run(order_id)
        if order.status == "generating":  # should not happen; make Tasks retry
            raise HTTPException(500, "incomplete")
        return {"status": order.status}


def _register_budget(app: FastAPI, d: Deps) -> None:
    @app.post("/internal/budget")
    async def budget(request: Request, authorization: str = Header(default="")):
        """Pub/Sub push from the Cloud Billing budget. Flips the kill switch at 100%.

        The docstring here used to say "Cloud Run verifies the OIDC token before this
        handler runs (push auth)". It does not. The service is publicly invocable — the
        same ingress every other route uses — and measured on 19 Sep an anonymous POST
        with a well-formed body returned 200 and reached the kill switch three lines
        below. The subscription was already SENDING a token (infra/gcp.tf configures
        oidc_token); nothing was reading it.

        Verified BEFORE the body is parsed, deliberately: the review saw a 500 here and
        read it as an endpoint failing safely, when it was an unauthenticated endpoint
        failing late on an empty body."""
        if not d.verify_pubsub(authorization):
            raise HTTPException(403, "pubsub_token")
        body = await request.json()
        raw = base64.b64decode(body.get("message", {}).get("data", "")).decode() or "{}"
        note = json.loads(raw)
        if float(note.get("alertThresholdExceeded", 0)) >= 1.0:
            d.pipeline.store.killswitch = True
        return {"killswitch": d.pipeline.store.killswitch}


# Every event type this handler branches on. infra/stripe.tf subscribes to exactly this
# set and tests/test_refund_reconciliation.py compares the two in BOTH directions: an
# event we receive and do not handle looks like coverage and is not; one we handle and do
# not receive is a branch that never runs.
PAID = "checkout.session.completed"
REFUND_SETTLED = "refund.updated"
REFUND_FAILED_EVENT = "refund.failed"

# The dispatch table, as data. infra/stripe.tf subscribes to exactly these keys and
# tests/test_refund_reconciliation.py compares the two sets in BOTH directions, reading
# this dict rather than grepping the function body - which broke the moment the literals
# became constants.
HANDLERS = {
    PAID: "_handle_paid",
    REFUND_SETTLED: "_handle_refund",
    REFUND_FAILED_EVENT: "_handle_refund",
}


def _handle_event(d: Deps, event: dict) -> dict:
    name = HANDLERS.get(event.get("type"))
    if name is None:
        return {"ignored": True}
    return globals()[name](d, event)


# Unit C2. Fulfilment is claimed per SESSION, not per event, because two different
# things now fulfil: the webhook and the success redirect. Stripe asks for both -
# "trigger fulfillment from your landing page as well", because "webhooks can sometimes
# be delayed" - and then requires the work to happen once: "Perform fulfillment only
# once per payment... your `fulfill_checkout` function might be called multiple times,
# possibly concurrently, for the same Checkout Session."
#
# Keying the claim on the event id could not do that: the redirect has no event id, so
# the two paths would claim different keys and generate four images twice.
FULFIL_PREFIX = "fulfil:"

# Stripe's own fulfilment gate is `payment_status != "unpaid"`; its reference
# implementation fulfils for `paid` AND `no_payment_required`. Written as an allowlist
# rather than a not-equals so an unrecognised future value fails closed, which a
# money path should.
FULFILLABLE = ("paid", "no_payment_required")


def _fulfil_session(d: Deps, session: dict) -> bool:
    """Create the order and queue generation, once per session, whoever asks first.

    Returns False when somebody already did it, which is a success for the caller: it
    means the gallery has an order behind it.

    THE ORDER DOCUMENT IS THE FULFILMENT RECORD, and it is checked before the claim key.
    Stripe asks for exactly that - "Record/save fulfillment status for this Checkout
    Session" - and the claim key alone is not enough: orders created before this function
    existed were claimed under their EVENT id, so their session key is free. Measured in
    production on 19 September, after the first version of C2 shipped: re-requesting the
    success URL for an order that was already `delivered` with four images overwrote it
    with a fresh one and queued generation again. Four fal images for a press of the back
    button.

    The claim key stays, one line below, as the guard against two callers arriving at the
    same moment - the case an existence check alone cannot cover.
    """
    if d.pipeline.store.get(session["id"]) is not None:
        return False
    if not d.pipeline.store.claim_event(f"{FULFIL_PREFIX}{session['id']}"):
        return False
    order = _order_from_session(session)
    d.pipeline.store.put(order)
    d.enqueue(order.id)  # Cloud Tasks -> /internal/generate
    return True


def _handle_paid(d: Deps, event: dict) -> dict:
    session = event["data"]["object"]
    if not _fulfil_session(d, session):
        return {"duplicate": True}  # 200 so Stripe stops retrying
    return {"queued": session["id"]}


def _handle_refund(d: Deps, event: dict) -> dict:
    """Bizum refunds settle asynchronously — stripe.Refund.create returns `pending` and
    the money moves minutes later. Without this the order sits at failed_refund_pending
    forever, telling a customer their refund is on its way with nothing left to confirm
    it arrived, and a refund that FAILED looks identical to one still settling.

    Order looked up by metadata.order_id, which entry.py sets when it creates the refund.
    The alternative is a Firestore query and index on refund_id for something the payload
    already carries."""
    refund = event["data"]["object"]
    order_id = (refund.get("metadata") or {}).get("order_id", "")
    order = d.pipeline.store.get(order_id) if order_id else None
    if order is None:
        # Never 500 here: Stripe retries a 500 forever, and an event about an order we
        # have never seen is not an error on our side.
        logger.info("refund event for an unknown order refund_id=%s", refund.get("id"))
        return {"ignored": True}
    if not d.pipeline.store.claim_event(event["id"]):
        return {"duplicate": True}
    order.refund_status = refund.get("status")
    order.status = (
        "failed_refunded" if order.refund_status == REFUND_CONFIRMED else "failed_refund_failed"
    )
    d.pipeline.store.put(order)
    logger.info(
        "refund settled order_id=%s refund_id=%s status=%s order_status=%s",
        id_prefix(order.id),
        refund.get("id"),
        order.refund_status,
        order.status,
    )
    return {"reconciled": order.id, "status": order.status}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _order_from_session(s: dict) -> Order:
    meta = s["metadata"]
    return Order(
        id=s["id"],
        email=s["customer_details"]["email"],
        source_image_urls=meta["source_urls"].split(","),
        style=meta.get("style", "corporativo"),
        wardrobe=meta.get("wardrobe") or None,
        amount_cents=int(s["amount_total"]),
        gclid=meta.get("gclid") or None,
        gbraid=meta.get("gbraid") or None,
        wbraid=meta.get("wbraid") or None,
        ga_client_id=meta.get("ga_client_id") or None,
        ga_session_id=meta.get("ga_session_id") or None,
        # Real Stripe sessions carry a string PaymentIntent id in "payment_intent" for
        # mode=payment; absent for no_payment_required. Ga4Purchase falls back when
        # this is None rather than ever reusing s["id"], the gallery's own order id.
        payment_intent=s.get("payment_intent") or None,
    )
