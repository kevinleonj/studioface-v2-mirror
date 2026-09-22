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

import logging
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


class _FakePrice:
    """What stripe.Price.retrieve() hands back. livemode is a plain bool attribute on
    the real Price object, same as on Balance (docs/verified.md, 2026-09-17)."""

    def __init__(self, livemode: bool = False) -> None:
        self.livemode = livemode


def _fake_stripe(price_livemode: bool = False, price_raises: bool = False):
    stripe = types.ModuleType("stripe")
    stripe.api_key = ""

    class InvalidRequestError(Exception):
        pass

    stripe.InvalidRequestError = InvalidRequestError
    stripe.checkout = types.SimpleNamespace(Session=types.SimpleNamespace())
    stripe.Refund = types.SimpleNamespace()
    stripe.Webhook = types.SimpleNamespace()

    class _RequestsClient:
        """Doubles stripe.RequestsClient so _price_is_live's explicit timeout wiring
        can run with no real socket. Real signature: RequestsClient(timeout=...)."""

        def __init__(self, *a, **k):
            pass

    stripe.RequestsClient = _RequestsClient
    stripe.default_http_client = None

    def _retrieve(price_id):
        if price_raises:
            raise RuntimeError("stripe unreachable")
        return _FakePrice(livemode=price_livemode)

    stripe.Price = types.SimpleNamespace(retrieve=_retrieve)
    return stripe


@pytest.fixture
def built(monkeypatch, request):
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

    Task 51: accepts an optional indirect param, a dict of extra environment variables
    layered on top of ENV (e.g. OWNER_ALERT_EMAIL), so both sides of a wiring can be
    proven at the composition root without a second copy of this setup.
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

    extra_env = getattr(request, "param", {})
    for name, value in {**ENV, **extra_env}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(entry, "_enqueue_factory", lambda s: lambda order_id: None)
    return entry.build()


def _deps_from(built):
    """The Deps instance any route closure carries. Same walk the stripe_mode and
    stripe_price_live tests below already do inline; task 51 is this pattern's third
    caller, so it is named once here rather than copied a third time."""
    for route in built.routes:
        closure = getattr(getattr(route, "endpoint", None), "__closure__", None) or ()
        for cell in closure:
            candidate = getattr(cell, "cell_contents", None)
            if hasattr(candidate, "stripe_mode"):
                return candidate
    raise AssertionError("no route closure carries Deps")


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


def test_health_reports_the_stripe_mode_from_the_configured_key(built):
    """Task 06, at the composition root: ENV's STRIPE_SECRET_KEY is sk_test_x, so
    build() must derive and wire 'test' into the real Deps, not just the unit.

    Reads Deps off a route closure rather than calling GET /health: that route also
    reads the (faked) killswitch from Firestore, and this fixture's Firestore double
    deliberately raises on any read (see _Collection.get above) to prove build() does
    not query Firestore at startup - a real GET here would trip that guard for a
    reason this test has nothing to do with."""
    deps = None
    for route in built.routes:
        closure = getattr(getattr(route, "endpoint", None), "__closure__", None) or ()
        for cell in closure:
            candidate = getattr(cell, "cell_contents", None)
            if hasattr(candidate, "stripe_mode"):
                deps = candidate
                break
        if deps is not None:
            break
    assert deps is not None, "no route closure carries Deps"
    assert deps.stripe_mode == "test"


def test_the_startup_log_states_the_stripe_mode_once(monkeypatch, built):
    """Task 06: 'log the same word once at startup.' Checked at the composition root
    (CLAUDE.md lesson 8) by re-running build() with a collector on app.entry's own
    logger, which configure_logging()'s root-handler replacement does not touch."""
    from app import entry

    records: list[str] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    handler = _Collect()
    entry_logger = logging.getLogger("app.entry")
    entry_logger.addHandler(handler)
    try:
        entry.build()
    finally:
        entry_logger.removeHandler(handler)

    lines = [m for m in records if "stripe_mode" in m]
    assert lines == ["stripe_mode=test"], f"expected exactly one line, got {records}"


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


# --------------------------------------------- task 21: stripe_price_live at startup


def test_the_price_livemode_is_retrieved_once_and_wired_into_health(built):
    """Task 21, at the composition root (CLAUDE.md lesson 8): the fixture's fake Stripe
    Price answers livemode=False (the fixture's default), so build() must have called
    it and carried the answer into the real Deps, not left the field at its default."""
    deps = None
    for route in built.routes:
        closure = getattr(getattr(route, "endpoint", None), "__closure__", None) or ()
        for cell in closure:
            candidate = getattr(cell, "cell_contents", None)
            if hasattr(candidate, "stripe_price_live"):
                deps = candidate
                break
        if deps is not None:
            break
    assert deps is not None, "no route closure carries Deps"
    assert deps.stripe_price_live is False


def _settings(price_eur: object = "price_123") -> object:
    """A real Settings object, built with no network — Settings.from_env only reads a
    dict. price_eur=None reproduces STRIPE_PRICE_EUR never having reached Cloud Run."""
    from app.config import Settings

    env = dict(ENV)
    if price_eur is None:
        env.pop("STRIPE_PRICE_EUR", None)
    else:
        env["STRIPE_PRICE_EUR"] = price_eur
    return Settings.from_env(env)


def test_price_is_live_true_when_stripe_reports_livemode_true(monkeypatch):
    """Twin one of two: the exact state that makes checkout work."""
    monkeypatch.delitem(sys.modules, "app.entry", raising=False)
    monkeypatch.setitem(sys.modules, "stripe", _fake_stripe(price_livemode=True))
    from app import entry

    assert entry._price_is_live(_settings()) is True


def test_price_is_live_false_when_stripe_reports_livemode_false(monkeypatch):
    """Twin two of two: the exact outage this task closes — a live key, a test price —
    must not be reported as live."""
    monkeypatch.delitem(sys.modules, "app.entry", raising=False)
    monkeypatch.setitem(sys.modules, "stripe", _fake_stripe(price_livemode=False))
    from app import entry

    assert entry._price_is_live(_settings()) is False


def test_price_is_live_false_and_does_not_raise_when_the_retrieval_fails(monkeypatch, caplog):
    """A hung or failed startup call must never take the container down: it answers
    False and logs why, never a traceback that crashes the caller."""
    monkeypatch.delitem(sys.modules, "app.entry", raising=False)
    monkeypatch.setitem(sys.modules, "stripe", _fake_stripe(price_raises=True))
    from app import entry

    with caplog.at_level(logging.WARNING, logger="app.entry"):
        result = entry._price_is_live(_settings())
    assert result is False
    messages = " ".join(caplog.messages)
    assert "stripe_price_live" in messages
    assert ENV["STRIPE_SECRET_KEY"] not in messages


def test_price_is_live_false_when_no_price_is_configured(monkeypatch):
    """STRIPE_PRICE_EUR ships unset before Terraform sets it (HANDOFF, 17 Sep); there is
    nothing to retrieve, so this must answer False without ever calling Stripe."""
    monkeypatch.delitem(sys.modules, "app.entry", raising=False)

    def _must_not_be_called(price_id):
        raise AssertionError("no price is configured; Stripe must not be called")

    fake = _fake_stripe()
    fake.Price = types.SimpleNamespace(retrieve=_must_not_be_called)
    monkeypatch.setitem(sys.modules, "stripe", fake)
    from app import entry

    assert entry._price_is_live(_settings(price_eur=None)) is False


# --------------------------------------------- task 51: owner_alerts at startup


def test_owner_alerts_is_false_when_owner_alert_email_is_unset(built):
    """The state production was actually in before Kevin set the OWNER_ALERT_EMAIL
    repository variable: ENV carries no such key, so build() must wire False, not
    leave the field at some other default."""
    assert _deps_from(built).owner_alerts is False


@pytest.mark.parametrize("built", [{"OWNER_ALERT_EMAIL": "owner@example.com"}], indirect=True)
def test_owner_alerts_is_true_when_owner_alert_email_is_set(built):
    """Twin of the test above: identical composition, one address configured, so
    this field cannot be hard-coded to False and still pass."""
    assert _deps_from(built).owner_alerts is True


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
