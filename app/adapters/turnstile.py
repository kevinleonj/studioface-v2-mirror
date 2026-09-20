"""Cloudflare Turnstile server-side verification. One token = one preview.
Endpoint per Cloudflare docs: https://challenges.cloudflare.com/turnstile/v0/siteverify
"""

from __future__ import annotations

import httpx

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def verify_turnstile(secret: str, token: str, remote_ip: str) -> bool:
    if not token:
        return False
    r = httpx.post(
        VERIFY_URL,
        data={"secret": secret, "response": token, "remoteip": remote_ip},
        timeout=5.0,
    )
    return r.status_code == 200 and bool(r.json().get("success"))
