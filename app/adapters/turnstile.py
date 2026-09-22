"""Cloudflare Turnstile server-side verification. One token = one preview.
Endpoint per Cloudflare docs: https://challenges.cloudflare.com/turnstile/v0/siteverify

This guard sits on the money path (/api/preview, the gate before checkout), so it has
two failure modes to keep apart:
  - the TOKEN is wrong, spent, or for the wrong site: refuse this one visitor (False).
  - CLOUDFLARE is unreachable: refuse to guess. Letting everyone through would defeat
    the check; returning False here would be indistinguishable from a bad token and
    would also 403 every genuine visitor for as long as the outage lasts with no way
    to tell the two apart from the logs. `TurnstileUnavailable` lets app/main.py
    answer 503 turnstile_unavailable instead — an outage, not a rejection.
"""

from __future__ import annotations

import logging

import httpx

from app.core import TurnstileUnavailable

logger = logging.getLogger(__name__)

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def verify_turnstile(secret: str, token: str, remote_ip: str, expected_hostname: str) -> bool:
    """True only for a token solved on `expected_hostname`.

    Cloudflare's siteverify response carries `hostname`, documented as "Hostname where
    the challenge was served" (docs/verified.md, 2026-09-22, and Cloudflare's own
    server-side-validation page). Skipping this check means a token minted by solving
    the widget on a completely different site — anyone's, not just ours — verifies
    here just as well as one solved on studioface.app; `secret` alone does not tell
    Cloudflare which site solved the challenge, only which ACCOUNT owns the widget.
    `expected_hostname` is a parameter, not a literal, because the site this runs on
    is not always studioface.app. What that host is for the local funnel walk is NOT
    127.0.0.1, as this said until task 75: Cloudflare's dummy secret reports a constant
    "example.com" wherever the widget was really solved (measured 22 Sep 2026), so the
    walk's harness passes that instead - tests/e2e/funnel_app.expected_turnstile_hostname.
    """
    if not token:
        return False
    try:
        r = httpx.post(
            VERIFY_URL,
            data={"secret": secret, "response": token, "remoteip": remote_ip},
            timeout=5.0,
        )
    except httpx.RequestError as exc:
        logger.warning("turnstile siteverify unreachable error=%s", type(exc).__name__)
        raise TurnstileUnavailable(type(exc).__name__) from exc
    if r.status_code != 200:
        return False
    body = r.json()
    return bool(body.get("success")) and body.get("hostname") == expected_hostname
