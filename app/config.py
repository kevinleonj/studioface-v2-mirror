"""Every environment variable the service needs, in one place, read once.

Cloud Run gives you one chance to find out what you forgot: the container either
starts or it does not. So a missing variable raises a RuntimeError naming ALL the
missing variables, not the first one — one redeploy, not five.

Secret-bearing fields are repr=False so a Settings object in a log line or a
traceback cannot leak a key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

REQUIRED = (
    "GCP_PROJECT",
    "GCP_REGION",
    "PUBLIC_URL",
    "BUCKET_SRC",
    "BUCKET_OUT",
    "TASKS_QUEUE",
    "TASKS_TOKEN",
    "APP_TOKEN_SECRET",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "RESEND_API_KEY",
    "TURNSTILE_SECRET",
)


@dataclass(frozen=True)
class Settings:
    project: str
    region: str
    public_url: str
    api_url: str
    bucket_src: str
    bucket_out: str
    tasks_queue: str
    tasks_token: str = field(repr=False)
    app_token_secret: str = field(repr=False)
    stripe_secret_key: str = field(repr=False)
    stripe_webhook_secret: str = field(repr=False)
    resend_api_key: str = field(repr=False)
    turnstile_secret: str = field(repr=False)
    static_dir: str = "/srv/static"
    stripe_price_eur: str | None = None
    ga4_measurement_id: str | None = None
    ga4_api_secret: str | None = field(default=None, repr=False)
    # Who is allowed to push to /internal/budget, and the audience their token must
    # carry. Optional here so a local run still boots; app/adapters/pubsub_push.py
    # refuses everything when either is empty, so "unset" closes the endpoint.
    pubsub_push_sa: str | None = None
    pubsub_push_audience: str | None = None
    # F8. /docs, /redoc and /openapi.json. Off unless explicitly asked for.
    enable_docs: bool = False

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        e = os.environ if env is None else env
        missing = [name for name in REQUIRED if not str(e.get(name, "")).strip()]
        if missing:
            raise RuntimeError("missing required environment variables: " + ", ".join(missing))
        public_url = e["PUBLIC_URL"].strip()
        return cls(
            project=e["GCP_PROJECT"].strip(),
            region=e["GCP_REGION"].strip(),
            public_url=public_url,
            api_url=e.get("API_URL", "").strip() or "https://api." + _host(public_url),
            bucket_src=e["BUCKET_SRC"].strip(),
            bucket_out=e["BUCKET_OUT"].strip(),
            tasks_queue=e["TASKS_QUEUE"].strip(),
            tasks_token=e["TASKS_TOKEN"],
            app_token_secret=e["APP_TOKEN_SECRET"],
            stripe_secret_key=e["STRIPE_SECRET_KEY"],
            stripe_webhook_secret=e["STRIPE_WEBHOOK_SECRET"],
            resend_api_key=e["RESEND_API_KEY"],
            turnstile_secret=e["TURNSTILE_SECRET"],
            static_dir=e.get("STATIC_DIR", "/srv/static"),
            stripe_price_eur=e.get("STRIPE_PRICE_EUR") or None,
            ga4_measurement_id=e.get("GA4_MEASUREMENT_ID") or None,
            ga4_api_secret=e.get("GA4_API_SECRET") or None,
            pubsub_push_sa=e.get("PUBSUB_PUSH_SA") or None,
            pubsub_push_audience=e.get("PUBSUB_PUSH_AUDIENCE") or None,
            enable_docs=str(e.get("ENABLE_DOCS", "")).strip().lower() in ("1", "true", "yes"),
        )


def _host(url: str) -> str:
    return url.removeprefix("https://").removeprefix("http://").rstrip("/")


def stripe_mode(key: str | None) -> str:
    """test, live, or unknown — derived only from the key's PREFIX, never the rest of
    it. docs/verified.md, 2026-09-17 and 2026-09-18: test keys are
    pk_test_/rk_test_/sk_test_, live are pk_live_/rk_live_/sk_live_."""
    prefix = key or ""
    if prefix.startswith("sk_test_") or prefix.startswith("rk_test_"):
        return "test"
    if prefix.startswith("sk_live_") or prefix.startswith("rk_live_"):
        return "live"
    return "unknown"
