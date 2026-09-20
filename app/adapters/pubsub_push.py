"""Verify that a Pub/Sub push really came from our own subscription.

`/internal/budget` sets the kill switch, which closes `/api/checkout` and `/api/preview`
with 503. It had no authentication at all: measured on 19 September 2026, an anonymous
POST with a well-formed body returned `200 {"killswitch":false}`, meaning the handler ran.

The subscription was already sending a token — `infra/gcp.tf` configures
`oidc_token { service_account_email = ... }` on the push config. Nothing read it.

What the RECEIVING application must check, from Google's own page
(https://docs.cloud.google.com/pubsub/docs/authenticate-push-subscriptions, recorded in
docs/verified.md on 19 Sep): the JWT arrives in the `Authorization` header as
`Bearer <jwt>`; verify the signature against Google's public certificates, that the issuer
is `https://accounts.google.com`, that `aud` equals the audience configured on the
subscription, and that the token's email is the expected push service account with
`email_verified` true.

Cloud Run's own IAM could also gate this, but the service is publicly invocable because it
serves the website from the same container. So the check belongs here, in the application,
where it does not depend on an ingress setting that the front end needs left open.
"""

from __future__ import annotations

import logging

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

logger = logging.getLogger(__name__)

BEARER = "Bearer "
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")


def _claims(authorization: str, audience: str) -> dict | None:
    """Signature, expiry and audience, all checked by google-auth. None means no."""
    if not authorization.startswith(BEARER):
        return None
    token = authorization[len(BEARER) :].strip()
    if not token:
        return None
    try:
        return id_token.verify_oauth2_token(token, google_requests.Request(), audience=audience)
    except ValueError as exc:
        # google-auth raises ValueError for a bad signature, a wrong audience and an
        # expired token alike. Logged at info: an unverified caller is a fact about the
        # internet, not an error in this service.
        logger.info("pubsub push token rejected: %s", exc)
        return None


def _is_our_subscription(claims: dict, expected_email: str) -> bool:
    if claims.get("iss") not in GOOGLE_ISSUERS:
        logger.info("pubsub push token issuer rejected: %s", claims.get("iss"))
        return False
    if not claims.get("email_verified"):
        logger.info("pubsub push token email not verified")
        return False
    # The audience alone proves nothing: anyone with a Google account can mint a token for
    # any audience string. The email is what ties it to our own subscription.
    if claims.get("email") != expected_email:
        logger.info("pubsub push token from an unexpected account")
        return False
    return True


def pubsub_verifier(expected_email: str, audience: str):
    """Returns a callable taking the raw Authorization header.

    Both arguments must be non-empty. If either is missing the returned verifier refuses
    everything rather than skipping the check - a half-configured auth check that lets
    traffic through is worse than the one that was missing, because it looks present.
    """

    def verify(authorization: str) -> bool:
        if not expected_email or not audience:
            logger.error("pubsub push verification is not configured; refusing")
            return False
        claims = _claims(authorization, audience)
        return claims is not None and _is_our_subscription(claims, expected_email)

    return verify
