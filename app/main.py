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
    # Task 29: the half of preview_fn that never calls the image model — store the
    # photos, nothing else. Defaults to a no-op so every test file that does not
    # exercise the storage-only path keeps working unmodified; app/entry.py always
    # wires the real one (the same Preview instance's `store_only`, so both paths
    # share one `put_source`).
    store_sources_fn: Callable[[list[bytes], str], None] = lambda files, batch: None
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
    # Task 30, preview-survives: gs://…/previews/{batch}/preview.jpg -> a fresh signed
    # https address, or None when this batch never produced one (store-only, or
    # unknown). Defaults to always-None so an unwired deployment fails closed — same
    # convention as retrieve_session and verify_pubsub above.
    resign_preview: Callable[[str], str | None] = lambda batch: None
    # Where this deployment's gallery lives. A constant until 20 September, when the
    # paid walk redirected a browser off loopback to the production gallery holding an
    # order that existed only locally (tests/test_after_payment.py).
    gallery_base: str = GALLERY_BASE
    # "test", "live" or "unknown" — app.config.stripe_mode(key), derived from the
    # configured Stripe key's PREFIX only. Never the key itself.
    stripe_mode: str = "unknown"
    # Task 21: what Stripe itself says about the configured price's livemode, read once
    # at startup by app.entry._price_is_live. False on any missing config or failure.
    stripe_price_live: bool = False


def make_app(
    pipeline: Pipeline,
    limiter: RateLimiter,
    enqueue: Callable[[str], None],
    preview_fn: Callable[[list[bytes], str], str],
    webhook_secret: str,
    tasks_token: str,
    store_sources_fn: Callable[[list[bytes], str], None] = lambda files, batch: None,
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
    stripe_price_live: bool = False,
    resign_preview: Callable[[str], str | None] = lambda batch: None,
) -> FastAPI:
    d = Deps(
        pipeline,
        limiter,
        enqueue,
        preview_fn,
        webhook_secret,
        tasks_token,
        store_sources_fn,
        verify_turnstile,
        verify_pubsub,
        retrieve_session,
        sign_url,
        create_checkout,
        resign_preview,
        gallery_base,
        stripe_mode,
        stripe_price_live,
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
    _register_preview_resign(app, d)
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
    logger.info("visitor_address xff shape=%s", xff_shape(x_forwarded_for))
    last = x_forwarded_for.split(",")[-1].strip()
    return last or _client_ip(request)


def _octet_pair(entry: str) -> str:
    """First two octets of an IPv4-looking entry, or "?" for anything else (a
    hostname, IPv6 literal, or empty string never has exactly four dot-separated
    parts). Never returns enough of an address to identify a visitor."""
    parts = entry.split(".")
    return ".".join(parts[:2]) if len(parts) == 4 else "?"


def xff_shape(x_forwarded_for: str) -> str:
    """A privacy-safe one-line summary of a raw X-Forwarded-For header.

    Task 20: `visitor_address` keys the preview and /api/recuperar caps on the LAST
    entry, on the inference (never measured before this task) that Google Front End
    appends its own observed peer address there. This line lets that inference be
    checked against Cloud Run's own request log, which carries the real
    httpRequest.remoteIp for the same request - without ever logging a full
    address: each entry, if it looks like an IPv4 address, is cut to its first two
    octets before it is logged.
    """
    entries = [e.strip() for e in x_forwarded_for.split(",")] if x_forwarded_for.strip() else []
    n = len(entries)
    first = _octet_pair(entries[0]) if n else "?"
    last = _octet_pair(entries[-1]) if n else "?"
    comparable = n > 0 and first != "?" and last != "?"
    return f"entries={n} first={first} last={last} first_eq_last={comparable and first == last}"


def _register_preview(app: FastAPI, d: Deps) -> None:
    @app.post("/api/preview")
    async def preview(request: Request, x_forwarded_for: str = Header(default="")):
        # Task 29, never-block-a-buyer: 21 September, Kevin's own shop hit the free
        # preview limit and from that moment held no signed handle at all, because
        # only a successful preview ever minted one — so there was no buy button for
        # an hour. Storing the photos and signing the handle is now possible WITHOUT
        # calling the image model, so a visitor at the limit can still pay.
        #
        # The human check still runs first, before anything else — unchanged from
        # task 28 — and only a file the server accepts can ever spend a try or a
        # stored batch, also unchanged.
        if d.pipeline.store.killswitch:
            raise HTTPException(503, "paused")
        ip = visitor_address(x_forwarded_for, request)
        form = await request.form()
        if not d.verify_turnstile(str(form.get("turnstile_token", "")), ip):
            raise HTTPException(403, "turnstile")
        files = [await f.read() for f in form.getlist("files")]
        try:
            v = validate_uploads(files)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        user_agent = request.headers.get("user-agent", "")
        # The batch id is minted here and signed the SAME way whether or not the
        # model ever runs: /api/checkout only ever checks `preview_token(batch, n,
        # secret)`, so a handle from the storage-only path is verified identically to
        # one from a real preview, and a made-up one is refused either way.
        batch, n = uuid4().hex, len(v.accepted)
        accepted = [b for _, b in v.accepted]

        # storeCurrentPhotosForBuy (frontend/src/components/upload-form.tsx): the buy
        # button must always sell the photos the visitor currently sees. Re-backing a
        # purchase with a changed set of photos never needs a new generation — the
        # visitor already saw one — so it goes straight to the storage-only path
        # without ever touching the preview budget.
        store_only = str(form.get("store_only", "")) == "1"
        if store_only:
            return _stored_handle(d, ip, user_agent, accepted, batch, n, False, "store_cap")

        ok, why = d.limiter.check(ip, user_agent)
        if not ok:
            # Storage is cheap but not free, so this fallback has its own ceiling
            # (RateLimiter.check_store, 10/visitor/hour) checked inside
            # _stored_handle. Only once THAT is also spent does a visitor at the
            # limit meet the real refusal — `why`, the original reason.
            return _stored_handle(d, ip, user_agent, accepted, batch, n, True, why)
        try:
            url = d.preview_fn(accepted, batch)
        except (ModelRefused, ValueError) as e:
            # F2. Both are the visitor's to fix, not a 500 with a body the frontend
            # cannot read. `normalise_all` raises ValueError inside preview_fn.
            detail = e.detail if isinstance(e, ModelRefused) else str(e)
            logger.info("preview refused batch=%s detail=%s", batch, detail)
            d.limiter.refund(ip, user_agent)  # task 28: not a spent try
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
            "limited": False,
        }


def _register_preview_resign(app: FastAPI, d: Deps) -> None:
    @app.get("/api/preview/{batch}")
    async def resign_preview(batch: str, n: int = 0, t: str = ""):
        """Task 30, preview-survives. The signed picture address dies in 15 minutes
        (GALLERY_TTL, app/adapters/gcs.py), so a reload or a return from Stripe's
        cancel redirect needs a FRESH one for the SAME stored result — never a new
        generation, never a new try spent. Verified with the exact same
        `preview_token` comparison /api/checkout uses, imported from app.core, not a
        re-implementation: a made-up signature is refused here exactly as it would
        be at checkout. 404, not 403 — this route names no object the caller does
        not already hold a valid handle for, so a wrong guess gets the same answer
        as an unknown one, never a different one that would confirm it was close.
        """
        expected = preview_token(batch, n, d.pipeline.secret)
        if not batch or not hmac.compare_digest(expected, t):
            raise HTTPException(404)
        url = d.resign_preview(batch)
        if url is None:
            raise HTTPException(404)
        return {"preview_url": url}


def _stored_handle(
    d: Deps,
    ip: str,
    user_agent: str,
    accepted: list[bytes],
    batch: str,
    n: int,
    limited: bool,
    refused_reason: str,
) -> dict:
    """Store the photos, sign a handle, call nothing that costs money. Bound by
    `RateLimiter.check_store` (10/visitor/hour): once that is also spent, the real
    429 carries `refused_reason` — the original preview-limit reason when this was
    reached because the free previews ran out, or `store_cap` when the visitor asked
    to store outright (storeCurrentPhotosForBuy)."""
    if not d.limiter.check_store(ip, user_agent):
        raise HTTPException(429, refused_reason)
    d.store_sources_fn(accepted, batch)
    logger.info("stored batch without generating batch=%s limited=%s", batch, limited)
    return {
        "preview_url": None,
        "batch": batch,
        "n": n,
        "wardrobe": default_wardrobe_key(PREVIEW_STYLE),
        "t": preview_token(batch, n, d.pipeline.secret),
        "limited": limited,
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
            # Fragment, not a query: see GALLERY_BASE's comment in app/core.py.
            d.pipeline.send_email(order.email, f"{d.gallery_base}#o={order.id}&t={token}")
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
            302 -> /g/#o=cs_test_fake&t=REDACTED

        (Task 31: the redirect now carries the fragment shape, never a query — see
        GALLERY_BASE's comment in app/core.py. This docstring is not re-verified from
        outside every run, so the literal token above is only an example.)

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
        return RedirectResponse(f"{d.gallery_base}#o={session_id}&t={token}", status_code=302)


def _download_url(d: Deps, uri: str, n: int) -> str:
    """The same object, signed to be saved as studioface-<n>.jpg."""
    try:
        return d.sign_url(uri, f"studioface-{n}.jpg")
    except TypeError:
        # A one-argument signer: keep today's behaviour rather than failing the gallery.
        return d.sign_url(uri)


def _order_status_payload(d: Deps, order_id: str, token: str) -> dict:
    """Shared by both order-status routes below. Never logs `order_id` or `token`:
    whoever can read a log line carrying either can open this customer's gallery
    (app/logs.py's own rule; tests/test_log_ids.py enforces it for every logger call
    in app/, and this function adds none)."""
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


def _register_public(app: FastAPI, d: Deps) -> None:
    @app.get(HEALTH_PATH)
    def health():
        return {
            "ok": True,
            "killswitch": d.pipeline.store.killswitch,
            "stripe_mode": d.stripe_mode,
            "stripe_price_live": d.stripe_price_live,
        }

    @app.post("/api/stripe/webhook")
    async def webhook(request: Request, stripe_signature: str = Header(default="")):
        body = await request.body()
        if not verify_stripe_signature(body, stripe_signature, d.webhook_secret):
            raise HTTPException(400, "bad_signature")
        event = await request.json()
        return _handle_event(d, event)

    @app.get("/api/orders/{order_id}")
    def status_by_header(order_id: str, x_gallery_token: str = Header(default="")):
        """Task 31's new shape: the key travels in a request header, never the
        address, so it can never reach an access log or an analytics request that
        watches the page's URL. This is the only shape the current frontend
        (frontend/src/app/g/page.tsx) ever calls."""
        return _order_status_payload(d, order_id, x_gallery_token)

    @app.get("/api/orders/{order_id}/{token}")
    def status(order_id: str, token: str):
        """The old shape, with the key in the path. Kept only for links already sent
        to a customer's inbox before task 31 - nothing in this codebase produces this
        shape any more; see status_by_header above."""
        return _order_status_payload(d, order_id, token)


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

    Task 42: this is also the ONE place, shared by the webhook and the redirect, where
    a paid Stripe session becomes an Order - so it is where the daily order ceiling has
    to be checked. Not at /api/checkout: a checkout attempt there is free to make and
    Stripe may never complete it, so counting there would cap browser visits, not paid
    orders. Pipeline.admit runs before the order is stored or generation is enqueued;
    when it refuses, it has already refunded the order itself (Stripe already took the
    money) and stored it as failed_refunded, so this still returns True - the session
    IS fulfilled, in the sense that nothing else should try again.
    """
    if d.pipeline.store.get(session["id"]) is not None:
        return False
    if not d.pipeline.store.claim_event(f"{FULFIL_PREFIX}{session['id']}"):
        return False
    order = _order_from_session(session)
    if not d.pipeline.admit(order):
        return True
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
