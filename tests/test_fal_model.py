"""The fal adapter. Every call shape here is pinned to docs/verified.md (2026-09-17,
Context7 /websites/fal_ai) and to inspect on the installed fal-client 1.0.1.

The important behaviour is the source URLs: we store selfies as gs://bucket/key in a
private bucket, and fal fetches over plain HTTPS. Handing fal a gs:// URI — which is
what the paid pipeline did — means fal cannot read the reference photos at all.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.adapters.fal import APPLICATION, FalModel  # noqa: E402


class FakeSubscribe:
    def __init__(self, result=None, error=None):
        self.calls = []
        self.result = result or {"images": [{"url": "https://fal.media/out.jpg", "width": 1024}]}
        self.error = error

    def __call__(self, application, arguments=None, **kw):
        self.calls.append((application, arguments))
        if self.error:
            raise self.error
        return self.result


def sign(uri):
    return f"https://storage.googleapis.com/{uri.removeprefix('gs://')}?X-Goog-Signature=ab"


def model(**kw):
    sub = kw.pop("subscribe", None) or FakeSubscribe()
    return FalModel(sign=sign, subscribe=sub, **kw), sub


# ---------------------------------------------------------------- one


def test_edit_returns_the_first_image_url():
    m, _ = model()
    assert m.edit(["gs://sf-src/a.jpg"], "a prompt") == "https://fal.media/out.jpg"


def test_it_calls_the_verified_application_id():
    m, sub = model()
    m.edit(["gs://sf-src/a.jpg"], "p")
    assert sub.calls[0][0] == APPLICATION == "fal-ai/nano-banana-2/edit"


def test_the_arguments_match_the_verified_schema():
    m, sub = model()
    m.edit(["gs://sf-src/a.jpg"], "a prompt")
    args = sub.calls[0][1]
    assert args["prompt"] == "a prompt"
    assert args["resolution"] == "1K"
    assert args["output_format"] == "jpeg"  # the schema default is png, so we must be explicit
    assert args["aspect_ratio"] == "4:5"


def test_resolution_is_configurable_for_the_cheap_preview():
    m, sub = model(resolution="0.5K")
    m.edit(["gs://sf-src/a.jpg"], "p")
    assert sub.calls[0][1]["resolution"] == "0.5K"


# ---------------------------------------------------------------- source URLs


def test_gs_sources_are_signed_because_fal_cannot_read_a_private_bucket():
    m, sub = model()
    m.edit(["gs://sf-src/u1/0.jpg", "gs://sf-src/u1/1.jpg"], "p")
    sent = sub.calls[0][1]["image_urls"]
    assert all(u.startswith("https://storage.googleapis.com/") for u in sent)
    assert all("X-Goog-Signature" in u for u in sent)


def test_https_sources_are_left_alone():
    m, sub = model()
    m.edit(["https://cdn.example/a.jpg"], "p")
    assert sub.calls[0][1]["image_urls"] == ["https://cdn.example/a.jpg"]


def test_many_sources_keep_their_order():
    m, sub = model()
    m.edit([f"gs://sf-src/u1/{i}.jpg" for i in range(4)], "p")
    sent = sub.calls[0][1]["image_urls"]
    assert [u.split("?")[0][-5:] for u in sent] == ["0.jpg", "1.jpg", "2.jpg", "3.jpg"]


# ---------------------------------------------------------------- failure


def test_no_sources_is_refused_before_spending_money():
    m, sub = model()
    with pytest.raises(ValueError, match="no_source_images"):
        m.edit([], "p")
    assert sub.calls == []  # never reached fal


def test_a_fal_error_propagates_so_the_retry_budget_sees_it():
    """The pipeline counts a raised call as one spent attempt. Swallowing it here
    would silently deliver an order with fewer than four images."""
    m, _ = model(subscribe=FakeSubscribe(error=RuntimeError("fal 500")))
    with pytest.raises(RuntimeError, match="fal 500"):
        m.edit(["gs://sf-src/a.jpg"], "p")


def test_an_empty_images_list_is_an_error_not_an_index_crash():
    """Held-out check: a 200 response with images=[] would raise IndexError deep in
    the adapter. It must look like any other failed attempt, with a readable reason."""
    m, _ = model(subscribe=FakeSubscribe(result={"images": [], "description": "refused"}))
    with pytest.raises(ValueError, match="fal_returned_no_image"):
        m.edit(["gs://sf-src/a.jpg"], "p")


def test_a_malformed_response_is_an_error_not_a_key_crash():
    m, _ = model(subscribe=FakeSubscribe(result={"detail": "nope"}))
    with pytest.raises(ValueError, match="fal_returned_no_image"):
        m.edit(["gs://sf-src/a.jpg"], "p")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
