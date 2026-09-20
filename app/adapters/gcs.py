"""Cloud Storage adapters: read-time signing for the gallery, write for sources.

Signing on Cloud Run is the awkward part. The credentials the metadata server hands
out carry an access token and no private key, so blob.generate_signed_url() reaches
google.cloud.storage._signing.ensure_signed_credentials and raises AttributeError
("you need a private key to sign credentials"). Passing service_account_email AND
access_token switches the library to the IAM signBlob API, which signs with the key
Google holds for the service account. That needs iam.serviceAccounts.signBlob on the
runtime service account (see MORNING-REPORT.md — the self-binding is unverified).
"""

from __future__ import annotations

import datetime as dt
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.logs import log_call

logger = logging.getLogger(__name__)

GALLERY_TTL = dt.timedelta(minutes=15)

# A quoted header value containing a quote, a newline or a backslash is a
# header-injection primitive. The route builds these names itself, and this is what
# keeps that true if anyone ever passes one through from a request.
SAFE_FILENAME = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _disposition(filename: str | None) -> str | None:
    if filename is None:
        return None
    if not SAFE_FILENAME.match(filename):
        raise ValueError(f"bad_filename:{filename!r}")
    return f'attachment; filename="{filename}"'


@dataclass
class SignedUrlMaker:
    """Callable: gs://bucket/key -> a signed https URL that dies in 15 minutes."""

    client: Any
    credentials: Any
    blob_factory: Callable[[str], Any]
    request_factory: Callable[[], Any] | None = None
    ttl: dt.timedelta = GALLERY_TTL
    _email: str = field(default="", repr=False)

    def __call__(self, uri: str, filename: str | None = None) -> str:
        """Sign `uri`. With `filename`, sign it as a download.

        Unit F3. "Descargar" did not download: the link was `<a download>` pointing at
        storage.googleapis.com, and the `download` attribute is ignored on a
        cross-origin link, so the browser navigated to the raw JPEG and the customer
        lost the page. Only the server can set the response header, and
        `response_disposition` is the documented parameter for it.
        """
        if not uri.startswith("gs://"):
            return uri  # an order stored before gs:// keys, or a test double
        if "/" not in uri.removeprefix("gs://"):
            raise ValueError(f"bad_gs_uri:{uri}")
        email, token = self._identity()
        return self.blob_factory(uri).generate_signed_url(
            version="v4",
            expiration=self.ttl,
            method="GET",
            service_account_email=email,
            access_token=token,
            response_disposition=_disposition(filename),
        )

    def all(self, uris: list[str]) -> list[str]:
        return [self(u) for u in uris]

    def _identity(self) -> tuple[str, str]:
        """Refresh only when the token is actually stale: the gallery polls every 3 s
        and four images per poll would otherwise be four metadata round trips each."""
        if not getattr(self.credentials, "valid", False):
            self.credentials.refresh(self._request())
            self._email = self.credentials.service_account_email
            logger.info("signing credentials refreshed service_account=%s", self._email)
        return self._email or self.credentials.service_account_email, self.credentials.token

    def _request(self) -> Any:
        if self.request_factory is not None:
            return self.request_factory()
        import google.auth.transport.requests

        return google.auth.transport.requests.Request()


def signed_url_maker(client: Any, ttl: dt.timedelta = GALLERY_TTL) -> SignedUrlMaker:
    """Production factory: ambient Cloud Run credentials, real Blob parsing."""
    import google.auth
    from google.cloud.storage import Blob

    credentials, _ = google.auth.default()
    return SignedUrlMaker(
        client=client,
        credentials=credentials,
        blob_factory=lambda uri: Blob.from_uri(uri, client=client),
        ttl=ttl,
    )


def source_uploader(client: Any, bucket_name: str) -> Callable[[str, bytes], str]:
    """Store a normalised selfie and return its gs:// URI. Always JPEG by the time it
    gets here (app/images.normalise), and never made public — readers get a signed URL.
    """
    bucket = client.bucket(bucket_name)

    def put(key: str, data: bytes) -> str:
        started = time.monotonic()
        bucket.blob(key).upload_from_string(data, content_type="image/jpeg")
        log_call(logger, "storage.put_source", started, detail=key)
        logger.info("source stored bucket=%s key=%s bytes=%d", bucket_name, key, len(data))
        return f"gs://{bucket_name}/{key}"

    return put
