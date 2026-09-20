"""F2: an input problem must never be an HTTP 500, and never one generic sentence.

O2, measured in production on 19 September. Kevin uploaded `Shrek_Profile.webp`:

    13:27:09  POST /api/preview  500  8.8s
    fal_client.client.FalClientHTTPError: [{'loc': ['body', 'prompt'],
      'msg': 'The content could not be processed because it contained material
              flagged by a content checker.',
      'type': 'content_policy_violation', ...}]

fal answered 422 and said exactly what was wrong. It left our building as a 500 with
FastAPI's own "Internal Server Error" body, which `messageFor` does not know, so the
visitor read "No hemos podido generar la prueba." - the fallback. The product knew the
answer and did not say it.

## The audit F2 asks for: every exception /api/preview can raise

    raised by                  value                     was    is
    killswitch                 paused                    503    503
    verify_turnstile false     turnstile                 403    403
    limiter                    client_cap/subnet_cap/
                               daily_cap                 429    429
    validate_uploads           upload_count:N            422    422
    validate_uploads           file_too_large:i          422    422
    validate_uploads           unsupported_type:i        422    422
    normalise (in preview_fn)  undecodable_image         500    422   <- also wrong
    Preview.__call__           no_files                  500    422
    fal 422                    content_policy_violation  500    422 content_policy
    fal 422                    any other documented type 500    422 model_<type>
    storage, network           anything else             500    500   correct

Two of those were 500s for an input problem, not one: `normalise_all` runs INSIDE
`preview_fn`, which is called outside the try/except that catches `validate_uploads`, so
a corrupt file was a 500 too.

fal's error types are branched on `type`, never on `msg` - fal's own documentation says
"Client code should not parse and rely on the msg field."
"""

import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import ModelRefused, OrderStore, Pipeline  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import make_app  # noqa: E402


def jpeg(size=(600, 600)) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, (128, 110, 100)).save(buffer, "JPEG")
    return buffer.getvalue()


def build(preview_fn):
    pipeline = Pipeline(
        store=OrderStore(),
        model=type("M", (), {"edit": lambda self, u, p: "x"})(),
        storage=type("S", (), {"put": lambda self, k, u: k})(),
        send_email=lambda t, b: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret="app",
    )
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter()),
        enqueue=lambda i: None,
        preview_fn=preview_fn,
        webhook_secret="whsec",
        tasks_token="tt",
        verify_turnstile=lambda token, ip: True,
    )
    from fastapi.testclient import TestClient

    # raise_server_exceptions=False so an unhandled exception becomes the 500 a browser
    # would actually receive, instead of being re-raised into the test.
    return TestClient(app, raise_server_exceptions=False)


def post(client, data=None):
    return client.post(
        "/api/preview",
        data={"turnstile_token": "x"},
        files={"files": ("a.jpg", data or jpeg(), "image/jpeg")},
    )


def raising(exc):
    def preview_fn(files, batch):
        raise exc

    return preview_fn


# ------------------------------------------------------------------ fal refusals


def test_a_content_policy_refusal_is_422_with_its_own_detail():
    """O2 itself. fal said what was wrong; the visitor must be told."""
    r = post(build(raising(ModelRefused("content_policy"))))
    assert r.status_code == 422, f"{r.status_code} {r.text}"
    assert r.json()["detail"] == "content_policy"


def test_another_documented_fal_refusal_keeps_its_own_name():
    """fal documents other 422 types - no_media_generated, image_load_error,
    image_too_large. Each gets its own sentence, so "we could not do it" is never the
    whole answer."""
    r = post(build(raising(ModelRefused("model_image_too_large"))))
    assert r.status_code == 422
    assert r.json()["detail"] == "model_image_too_large"


def test_a_corrupt_file_is_422_not_500():
    """The second 500 nobody had noticed: normalise runs inside preview_fn, outside the
    try/except that catches validate_uploads."""
    r = post(build(raising(ValueError("undecodable_image"))))
    assert r.status_code == 422, f"{r.status_code} {r.text}"
    assert r.json()["detail"] == "undecodable_image"


# ------------------------------------------------------------------ held out


def test_a_real_server_failure_is_still_a_500():
    """Held-out check, and the one that stops this unit becoming "return 422 for
    everything". Storage being down is our problem and must look like it."""
    r = post(build(raising(RuntimeError("the bucket is on fire"))))
    assert r.status_code == 500


def test_a_good_upload_still_succeeds():
    """Held-out the other way."""
    r = post(build(lambda files, batch: "https://storage.googleapis.com/x?sig=a"))
    assert r.status_code == 200, r.text
    assert r.json()["preview_url"].startswith("https://storage.googleapis.com/")


# ------------------------------------------------------------------ the adapter


def test_the_fal_adapter_turns_a_422_into_a_named_refusal():
    """Branching on `type`, never on `msg`: fal's documentation says "Client code should
    not parse and rely on the msg field."

    The shape below is the production body of 19 September, verbatim.
    """
    from app.adapters.fal import FalModel

    class FakeHTTPError(Exception):
        status_code = 422
        message = [
            {
                "loc": ["body", "prompt"],
                "msg": "The content could not be processed because it contained "
                "material flagged by a content checker.",
                "type": "content_policy_violation",
                "url": "https://docs.fal.ai/errors#content_policy_violation",
            }
        ]
        error_type = None

    def boom(application, arguments):
        raise FakeHTTPError()

    model = FalModel(sign=lambda u: u, subscribe=boom)
    with pytest.raises(ModelRefused) as caught:
        model.edit(["gs://src/a.jpg"], "a prompt")
    assert caught.value.detail == "content_policy"


def test_the_fal_adapter_does_not_swallow_a_real_outage():
    """A 5xx from fal is not an input problem and must keep its shape."""
    from app.adapters.fal import FalModel

    class FakeHTTPError(Exception):
        status_code = 503
        message = "upstream unavailable"
        error_type = None

    def boom(application, arguments):
        raise FakeHTTPError()

    model = FalModel(sign=lambda u: u, subscribe=boom)
    with pytest.raises(Exception) as caught:
        model.edit(["gs://src/a.jpg"], "a prompt")
    assert not isinstance(caught.value, ModelRefused), "a fal outage became a refusal"


# ------------------------------------------------------------------ the sentences


def test_every_detail_the_server_can_return_has_its_own_spanish_sentence():
    """The other half of O2: a detail with no sentence collapses into the fallback,
    which is what the visitor actually read.

    Comments are stripped first (M4) - this file's own prose names several of these
    keys, and a scan that read its own comments would pass against a page with none.
    """
    sys.path.insert(0, str(ROOT / "tests"))
    from source_scan import strip_comments

    source = strip_comments(
        (ROOT / "frontend" / "src" / "components" / "upload-form.tsx").read_text(encoding="utf-8"),
        language="tsx",
    )
    for detail in (
        "content_policy",
        "undecodable_image",
        "client_cap",
        "subnet_cap",
        "daily_cap",
        "turnstile",
        "paused",
        "bad_handle",
        "checkout_not_configured",
    ):
        assert detail in source, f"no Spanish sentence for detail {detail!r}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
