"""The walk's storage double, and the one thing it has to get right.

fal fetches the source images itself. In production `sign` turns a `gs://` key into a
signed storage.googleapis.com URL, so fal always receives something it can GET. The walk
replaces the bucket with a temp directory and passed `sign=lambda uri: uri`, which hands
fal the raw `gs://local/...` key.

The preview path was fixed for this in September (`put_source_for_fal` uploads to fal's
own storage). The DELIVERY path was not, and nothing noticed because the paid walk had
never been run. On 20 September it was, and fal answered:

    Invalid URL scheme 'gs:' in image URL. Only http://, https://, and data: URLs
    are supported.

Four generations, four refusals, an empty gallery, ten minutes of polling. This test
costs nothing and would have said so in a second.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.e2e.funnel_app import LOCAL_SCHEME, LocalStorage  # noqa: E402

FAL_URL = "https://v3b.fal.media/files/elephant/abc.jpg"
KEY = "previews/b4tch/0.jpg"


def _uploading_to_fal(monkeypatch):
    import fal_client

    monkeypatch.setattr(fal_client, "upload", lambda data, ct, file_name=None: FAL_URL)


def test_a_delivery_source_is_addressed_by_a_url_fal_can_fetch(tmp_path, monkeypatch):
    _uploading_to_fal(monkeypatch)
    storage = LocalStorage(tmp_path)
    storage.put_source_for_fal(KEY, b"jpeg bytes")

    # What the checkout metadata carries, and what the pipeline hands the model.
    signed = storage.sign_for_fal(f"{LOCAL_SCHEME}{KEY}")

    assert signed.startswith("https://"), f"fal refuses this scheme: {signed}"
    assert signed == FAL_URL


def test_a_key_fal_never_uploaded_still_resolves_to_the_local_origin(tmp_path, monkeypatch):
    """Delivered outputs are not fal sources. They must keep going to `/__files__`, which
    is the app's own origin and what `img-src 'self'` allows."""
    _uploading_to_fal(monkeypatch)
    storage = LocalStorage(tmp_path)

    assert storage.sign_for_fal(f"{LOCAL_SCHEME}orders/cs_test_1/0.jpg") == (
        "/__files__/orders/cs_test_1/0.jpg"
    )


def test_an_address_that_is_already_fetchable_is_left_alone(tmp_path, monkeypatch):
    _uploading_to_fal(monkeypatch)
    storage = LocalStorage(tmp_path)

    assert storage.sign_for_fal(FAL_URL) == FAL_URL
