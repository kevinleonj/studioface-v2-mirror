"""The free preview: validated bytes -> BUCKET_SRC -> one fal call at 0.5K.

0.5K because the preview is the part strangers can trigger; docs/verified.md prices
a 1K image at $0.08 and the rate limiter is the other half of that bill's ceiling.
"""

import io
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.guards import build_prompt  # noqa: E402
from app.preview import Preview  # noqa: E402


def jpeg(size=(900, 700)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (150, 90, 60)).save(buf, "JPEG")
    return buf.getvalue()


def heic(size=(800, 600)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (20, 80, 180)).save(buf, "HEIF")
    return buf.getvalue()


class FakeBucket:
    def __init__(self):
        self.objects = {}

    def put(self, key, data):
        self.objects[key] = data
        return f"gs://sf-src/{key}"


class FakeModel:
    def __init__(self, error=None):
        self.calls, self.error = [], error

    def edit(self, image_urls, prompt):
        self.calls.append((image_urls, prompt))
        if self.error:
            raise self.error
        return "https://fal.media/preview.jpg"


def build(error=None):
    """Unit C1 gave Preview two more collaborators: the result no longer leaves the
    building as fal's own address. `store_result` stands where the bucket upload stands
    and `sign` where the signer does, so these tests still see one call to fal and now
    also see where its output goes."""
    bucket, model = FakeBucket(), FakeModel(error=error)
    preview = Preview(
        put_source=bucket.put,
        model=model,
        store_result=lambda key, url: f"gs://out/{key}",
        sign=lambda uri: f"https://storage.googleapis.com/{uri.removeprefix('gs://out/')}?sig=x",
    )
    return preview, bucket, model


# ---------------------------------------------------------------- one


def test_one_file_is_uploaded_then_sent_to_fal():
    preview, bucket, model = build()
    assert preview([jpeg()], "batch1") == (
        "https://storage.googleapis.com/previews/batch1/preview.jpg?sig=x"
    ), "C1: the preview must come back as a signed address, not fal's"
    assert list(bucket.objects) == ["previews/batch1/0.jpg"]
    assert model.calls[0][0] == ["gs://sf-src/previews/batch1/0.jpg"]


def test_the_preview_uses_the_corporativo_prompt_variant_zero():
    preview, _, model = build()
    preview([jpeg()], "batch1")
    assert model.calls[0][1] == build_prompt("corporativo", 0)


# ---------------------------------------------------------------- many


def test_four_files_keep_their_order():
    preview, bucket, model = build()
    preview([jpeg(), jpeg(), jpeg(), jpeg()], "batch1")
    assert list(bucket.objects) == [f"previews/batch1/{i}.jpg" for i in range(4)]
    assert model.calls[0][0] == [f"gs://sf-src/previews/batch1/{i}.jpg" for i in range(4)]


def test_two_previews_do_not_overwrite_each_other():
    preview, bucket, _ = build()
    preview([jpeg()], "batch1")
    preview([jpeg()], "batch2")
    assert sorted(bucket.objects) == ["previews/batch1/0.jpg", "previews/batch2/0.jpg"]


# ---------------------------------------------------------------- normalisation


def test_heic_is_converted_before_it_reaches_the_bucket():
    """fal cannot read HEIC. Uploading it raw would fail at generation time, after
    the object was already stored and the rate-limit slot already spent."""
    preview, bucket, _ = build()
    preview([heic()], "batch1")
    stored = bucket.objects["previews/batch1/0.jpg"]
    assert stored[:3] == b"\xff\xd8\xff"  # JPEG magic, not ftypheic
    assert Image.open(io.BytesIO(stored)).format == "JPEG"


def test_a_huge_upload_is_shrunk_before_it_is_stored():
    preview, bucket, _ = build()
    preview([jpeg((4000, 3000))], "batch1")
    assert max(Image.open(io.BytesIO(bucket.objects["previews/batch1/0.jpg"])).size) == 1536


# ---------------------------------------------------------------- empty / failure


def test_no_files_is_refused_before_touching_the_bucket():
    preview, bucket, model = build()
    with pytest.raises(ValueError, match="no_files"):
        preview([], "batch1")
    assert bucket.objects == {} and model.calls == []


def test_an_undecodable_file_is_refused_before_touching_the_bucket():
    """Held-out check: guards.sniff passes anything with the right first bytes, so a
    truncated JPEG reaches here. Nothing may be stored and no fal call may be paid
    for when the bytes turn out to be junk."""
    preview, bucket, model = build()
    with pytest.raises(ValueError, match="undecodable_image"):
        preview([b"\xff\xd8\xff" + b"garbage"], "batch1")
    assert bucket.objects == {} and model.calls == []


def test_a_fal_failure_propagates_after_the_sources_are_stored():
    preview, bucket, _ = build(error=RuntimeError("fal 500"))
    with pytest.raises(RuntimeError, match="fal 500"):
        preview([jpeg()], "batch1")
    assert list(bucket.objects) == ["previews/batch1/0.jpg"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
