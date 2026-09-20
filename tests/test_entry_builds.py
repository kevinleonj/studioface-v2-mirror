"""`app.entry.build()` is run, with only the network boundaries faked.

CLAUDE.md lesson 8: "Production wiring counts: entry.py must be exercised with only
network boundaries faked." This file is that, and it exists because the absence of it
cost a deploy on 19 September.

Unit C1 gave the preview a second collaborator and wired it as `store_result=storage.put`.
`storage` in that module is the imported `google.cloud.storage` MODULE - the bucket
adapter was built inline and never named - so the container died on startup with

    AttributeError: module 'google.cloud.storage' has no attribute 'put'
    Default STARTUP TCP probe failed 1 time consecutively for container "api-1"

609 unit tests passed, the gate was green, and nothing noticed, because every one of them
builds the app through `make_app` with its own doubles and never through `build()`.
Composition is code. This runs it.

Everything faked here is a thing that opens a socket, and nothing else: Firestore, Cloud
Storage, Cloud Tasks, Stripe, Resend. The wiring between them is real.
"""

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ENV = {
    "GCP_PROJECT": "sf",
    "GCP_REGION": "europe-west1",
    "PUBLIC_URL": "https://studioface.app",
    "BUCKET_SRC": "sf-src",
    "BUCKET_OUT": "sf-out",
    "TASKS_QUEUE": "generate",
    "TASKS_TOKEN": "tt",
    "APP_TOKEN_SECRET": "app-secret-for-the-test",
    "STRIPE_SECRET_KEY": "sk_test_x",
    "STRIPE_WEBHOOK_SECRET": "whsec_x",
    "RESEND_API_KEY": "re_x",
    "TURNSTILE_SECRET": "0x-secret",
    "STRIPE_PRICE_EUR": "price_123",
    "GA4_MEASUREMENT_ID": "G-TEST",
    "GA4_API_SECRET": "ga4-secret",
}


class _Blob:
    def upload_from_string(self, data, content_type=None):
        return None

    def generate_signed_url(self, **kwargs):
        return "https://storage.googleapis.com/sf-out/x?X-Goog-Signature=abc"


class _Bucket:
    name = "sf-out"

    def blob(self, key):
        return _Blob()


class _StorageClient:
    def __init__(self, *a, **k):
        pass

    def bucket(self, name):
        return _Bucket()


class _Credentials:
    """What google.auth.default() hands back on Cloud Run."""

    valid = True
    token = "ya29.test"
    service_account_email = "run@sf.iam.gserviceaccount.com"

    def refresh(self, request):
        return None


class _Collection:
    """Firestore hands out collection and document handles without a round trip, so
    building one is not a network call and the double only has to exist."""

    def document(self, name=None):
        return _Collection()

    def get(self):
        raise AssertionError("build() must not READ from Firestore")


class _FirestoreClient:
    def __init__(self, *a, **k):
        pass

    def collection(self, name):
        return _Collection()


def _fake_stripe():
    stripe = types.ModuleType("stripe")
    stripe.api_key = ""

    class InvalidRequestError(Exception):
        pass

    stripe.InvalidRequestError = InvalidRequestError
    stripe.checkout = types.SimpleNamespace(Session=types.SimpleNamespace())
    stripe.Refund = types.SimpleNamespace()
    stripe.Webhook = types.SimpleNamespace()
    return stripe


@pytest.fixture
def built(monkeypatch):
    """Import `app.entry` with its boundaries already faked, then run `build()`.

    The order matters and cost a second red deploy to learn. `app/entry.py` ends with

        app = build() if os.environ.get("GCP_PROJECT") else None

    so importing it with GCP_PROJECT set runs the whole composition at import time,
    before any fixture can patch anything. The first version of this file set the
    environment first, so `build()` ran against the real Google clients; it passed here
    because this machine has application default credentials and failed in CI, which has
    none, with DefaultCredentialsError.

    So: keep GCP_PROJECT out of the environment across the import, patch at the source
    modules, and only then call `build()` ourselves.
    """
    import google.auth
    from google.cloud import firestore as real_firestore
    from google.cloud import storage as real_storage

    monkeypatch.delenv("GCP_PROJECT", raising=False)
    monkeypatch.delitem(sys.modules, "app.entry", raising=False)

    monkeypatch.setattr(google.auth, "default", lambda *a, **k: (_Credentials(), "sf"))
    monkeypatch.setattr(real_storage, "Client", _StorageClient)
    monkeypatch.setattr(real_firestore, "Client", _FirestoreClient)
    monkeypatch.setitem(sys.modules, "stripe", _fake_stripe())

    resend = types.ModuleType("resend")
    resend.api_key = ""
    resend.Emails = types.SimpleNamespace(send=lambda payload: {"id": "e"})
    monkeypatch.setitem(sys.modules, "resend", resend)

    from app import entry

    assert entry.app is None, "entry built itself at import time; the env was not clean"

    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(entry, "_enqueue_factory", lambda s: lambda order_id: None)
    return entry.build()


def test_the_application_is_built_at_all(built):
    """The whole point. Nothing below this line matters if this raises."""
    assert built is not None


def test_every_route_the_funnel_needs_is_registered(built):
    """A composition that builds but forgets a route is the same outage with a nicer
    traceback."""
    paths = {getattr(r, "path", "") for r in built.routes}
    for path in (
        "/api/preview",
        "/api/checkout",
        "/api/gracias",
        "/api/orders/{order_id}/{token}",
        "/api/stripe/webhook",
        "/internal/generate/{order_id}",
    ):
        assert path in paths, f"{path} is not registered; have {sorted(paths)[:12]}"


def test_the_preview_is_wired_to_store_and_sign_its_result(built):
    """C1, at the composition root rather than in a unit.

    This is the assertion that would have caught the failed deploy: it reaches the real
    `Preview` the real `build()` constructed and checks that both collaborators are
    callables bound to something, not a module attribute that happens to resolve.
    """
    from app.preview import Preview

    preview = None
    for route in built.routes:
        closure = getattr(getattr(route, "endpoint", None), "__closure__", None) or ()
        for cell in closure:
            if isinstance(getattr(cell, "cell_contents", None), object):
                candidate = cell.cell_contents
                if hasattr(candidate, "preview_fn"):
                    preview = candidate.preview_fn
                    break
        if preview is not None:
            break
    assert isinstance(preview, Preview), f"the composition root built {type(preview)}"
    assert callable(preview.store_result), "store_result is not callable"
    assert callable(preview.sign), "sign is not callable"
    assert preview.store_result.__self__ is not None, "store_result is not bound to a bucket"


def test_the_session_retriever_uses_the_supported_stripe_call(built):
    """I2 was `dict(session)` on stripe-python 15, which raises. The supported call is
    `.to_dict()`, and the exception path is `stripe.InvalidRequestError`, not the
    `stripe.error` shim that v13 removed."""
    import inspect

    from app import entry

    source = inspect.getsource(entry._session_retriever)
    assert ".to_dict()" in source, "the retriever is not using the supported call"
    assert "dict(stripe.checkout" not in source, "dict(session) is back"
    assert "stripe.error." not in source, "the removed stripe.error shim is back"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
