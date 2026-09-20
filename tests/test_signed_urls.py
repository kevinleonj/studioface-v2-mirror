"""Gallery links are short-lived signed URLs. The objects are never public.

The hard part is not signing, it is signing on Cloud Run: the metadata-server
credentials there hold a token and no private key, so generate_signed_url raises
AttributeError unless it is given service_account_email + access_token, which makes
it sign through the IAM signBlob API instead. That is what these tests pin.
"""

import datetime as dt
import sys
from pathlib import Path

import pytest
from google.cloud.storage import Blob

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.adapters.gcs import SignedUrlMaker, source_uploader  # noqa: E402


class FakeCredentials:
    def __init__(self, token=None, email="svc@sf-prod.iam.gserviceaccount.com", valid=False):
        self.token, self.service_account_email, self.valid = token, email, valid
        self.refreshes = 0

    def refresh(self, request):
        self.refreshes += 1
        self.token, self.valid = "ya29.fresh", True


class FakeBlob:
    def __init__(self, bucket, name):
        self.bucket, self.name, self.calls = bucket, name, []

    def generate_signed_url(self, **kw):
        self.calls.append(kw)
        return f"https://storage.googleapis.com/{self.bucket}/{self.name}?X-Goog-Signature=deadbeef"


class FakeStorageClient:
    def __init__(self):
        self.blobs = []

    def blob_from_uri(self, uri):
        rest = uri.removeprefix("gs://")
        bucket, _, name = rest.partition("/")
        b = FakeBlob(bucket, name)
        self.blobs.append(b)
        return b


def maker(**kw):
    creds = kw.pop("credentials", None) or FakeCredentials()
    client = FakeStorageClient()
    return (
        SignedUrlMaker(client=client, credentials=creds, blob_factory=client.blob_from_uri, **kw),
        client,
        creds,
    )


# ---------------------------------------------------------------- one


def test_a_gs_uri_becomes_a_signed_https_url():
    sign, client, _ = maker()
    url = sign("gs://sf-out/cs_1/0.jpg")
    assert url.startswith("https://storage.googleapis.com/sf-out/cs_1/0.jpg")
    assert "X-Goog-Signature" in url
    assert client.blobs[0].bucket == "sf-out" and client.blobs[0].name == "cs_1/0.jpg"


def test_it_signs_v4_for_get_and_expires_in_fifteen_minutes():
    sign, client, _ = maker()
    sign("gs://sf-out/cs_1/0.jpg")
    kw = client.blobs[0].calls[0]
    assert kw["version"] == "v4"
    assert kw["method"] == "GET"
    assert kw["expiration"] == dt.timedelta(minutes=15)


def test_it_passes_the_signblob_identity_because_cloud_run_has_no_private_key():
    """Without both of these, python-storage calls ensure_signed_credentials and
    raises AttributeError: 'you need a private key to sign credentials'."""
    sign, client, creds = maker()
    sign("gs://sf-out/cs_1/0.jpg")
    kw = client.blobs[0].calls[0]
    assert kw["service_account_email"] == "svc@sf-prod.iam.gserviceaccount.com"
    assert kw["access_token"] == "ya29.fresh"


# ---------------------------------------------------------------- credentials


def test_credentials_are_refreshed_once_then_reused():
    """service_account_email is not guaranteed to be populated before refresh(),
    but re-refreshing per image would be four metadata round trips per gallery poll."""
    sign, _, creds = maker()
    for i in range(4):
        sign(f"gs://sf-out/cs_1/{i}.jpg")
    assert creds.refreshes == 1


def test_an_expired_token_is_refreshed_again():
    creds = FakeCredentials(token="ya29.old", valid=True)
    sign, _, _ = maker(credentials=creds)
    sign("gs://sf-out/cs_1/0.jpg")
    assert creds.refreshes == 0  # still valid, left alone
    creds.valid = False  # an hour passes
    sign("gs://sf-out/cs_1/1.jpg")
    assert creds.refreshes == 1


# ---------------------------------------------------------------- many / empty


def test_sign_all_empty_list():
    sign, _, _ = maker()
    assert sign.all([]) == []


def test_sign_all_keeps_order():
    sign, _, _ = maker()
    out = sign.all([f"gs://sf-out/cs_1/{i}.jpg" for i in range(4)])
    assert len(out) == 4
    assert [u.split("?")[0].rsplit("/", 1)[1] for u in out] == ["0.jpg", "1.jpg", "2.jpg", "3.jpg"]


# ---------------------------------------------------------------- failure


def test_a_non_gs_url_is_passed_through_untouched():
    """Orders stored before this change hold plain https URLs; do not mangle them."""
    sign, client, _ = maker()
    assert sign("https://cdn.example/x.jpg") == "https://cdn.example/x.jpg"
    assert client.blobs == []


def test_a_malformed_gs_uri_fails_loudly():
    sign, _, _ = maker()
    with pytest.raises(ValueError, match="bad_gs_uri"):
        sign("gs://sf-out")  # bucket but no object


# ---------------------------------------------------------------- held-out


def test_the_real_library_parses_the_uris_we_actually_store():
    """Held-out check: the fake above could agree with a wrong parse forever. This
    runs the real google-cloud-storage parser (offline, no credentials) on a key
    shaped exactly like ours, including the slash the order id introduces."""
    blob = Blob.from_uri("gs://sf-out/cs_test_123/3.jpg", client=None)
    assert blob.bucket.name == "sf-out"
    assert blob.name == "cs_test_123/3.jpg"


# ---------------------------------------------------------------- source uploads


class RecordingBlob:
    def __init__(self, name):
        self.name, self.uploads = name, []

    def upload_from_string(self, data, content_type=None):
        self.uploads.append((data, content_type))


class RecordingBucket:
    def __init__(self):
        self.blobs = {}

    def blob(self, name):
        return self.blobs.setdefault(name, RecordingBlob(name))


class RecordingClient:
    def __init__(self):
        self.bucket_obj = RecordingBucket()

    def bucket(self, name):
        return self.bucket_obj


def test_source_upload_returns_a_gs_uri_and_sets_the_jpeg_content_type():
    client = RecordingClient()
    put = source_uploader(client, "sf-src")
    assert put("previews/b1/0.jpg", b"jpeg-bytes") == "gs://sf-src/previews/b1/0.jpg"
    blob = client.bucket_obj.blobs["previews/b1/0.jpg"]
    assert blob.uploads == [(b"jpeg-bytes", "image/jpeg")]


def test_source_upload_never_makes_the_object_public():
    """Held-out check: make_public()/predefined ACLs here would undo the whole point
    of signing. The blob must receive nothing but the upload."""
    client = RecordingClient()
    source_uploader(client, "sf-src")("k.jpg", b"x")
    blob = client.bucket_obj.blobs["k.jpg"]
    assert not hasattr(blob, "made_public")
    assert len(blob.uploads) == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
