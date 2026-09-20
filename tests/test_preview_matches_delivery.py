"""F6 reopened: the preview is the sales promise, and it could not keep it.

O6 said the preview and the delivery disagree. The first audit answered "the model did
not follow the prompt" and that answer was wrong. The request bodies say so. For order
`cs_test_a1eehOBw`, variant 0 for both, everything identical except two fields:

    endpoint      fal-ai/nano-banana-2/edit          SAME
    image_urls    one, the same signed source        SAME
    aspect_ratio  4:5                                SAME
    output_format jpeg                               SAME
    seed          absent from both                   SAME
    num_images    absent from both                   SAME
    resolution    0.5K  ->  1K                       different, deliberate, not clothing
    prompt        "...a dark navy blazer over a plain white shirt..."
                  "...a smart-casual light blue shirt with an open collar..."

The model obeyed both times. The order carried `wardrobe='camisa-azul'` and the preview
carried none.

## Why the preview carried none, and why that is structural

`Preview.__call__` calls `build_prompt(self.style, 0)` with no wardrobe, so it always
renders the style default. It has no choice: the wardrobe selector is rendered inside
`{handle ? (...)}` in upload-form.tsx, which means it does not exist until the preview
has already come back. The order is: upload, preview, THEN choose clothes, then pay.

So a customer who picks anything other than the default is shown one garment and sold
another, every time, by construction. That is systematic, it is in our code, and it is
not something the model did.

## What this unit changes, and what it deliberately does not

F6 says the preview must use the wardrobe the DEFAULT delivery uses. It already does -
the style default is exactly `blazer-camisa` - so that rule does not fire and no prompt
is touched. F6 also says do not change the four final prompts, so the customer's choice
still wins.

What is left is a promise the interface does not keep, and the fix is to keep it: the
server says which wardrobe the preview was made with, and the page says so plainly when
the customer picks a different one. No extra fal call, no change to either prompt.
"""

import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from source_scan import strip_comments  # noqa: E402

from app.core import OrderStore, Pipeline  # noqa: E402
from app.guards import STYLES, WARDROBES, build_prompt, default_wardrobe_key  # noqa: E402
from app.main import make_app  # noqa: E402
from app.preview import PREVIEW_STYLE  # noqa: E402

FORM = ROOT / "frontend" / "src" / "components" / "upload-form.tsx"


def jpeg() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (600, 600), (128, 110, 100)).save(buffer, "JPEG")
    return buffer.getvalue()


def build():
    from app.preview import Preview

    pipeline = Pipeline(
        store=OrderStore(),
        model=type("M", (), {"edit": lambda self, u, p: "x"})(),
        storage=type("S", (), {"put": lambda self, k, u: k})(),
        send_email=lambda t, b: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret="app",
    )
    preview_fn = Preview(
        put_source=lambda key, data: f"gs://src/{key}",
        model=type("M", (), {"edit": lambda self, u, p: "https://fal/x.jpg"})(),
        store_result=lambda key, url: f"gs://out/{key}",
        sign=lambda uri: f"https://storage.googleapis.com/{uri}?sig=a",
    )
    from app.guards import MemoryCounter, RateLimiter

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

    return TestClient(app)


def post(client):
    return client.post(
        "/api/preview",
        data={"turnstile_token": "x"},
        files={"files": ("a.jpg", jpeg(), "image/jpeg")},
    )


# ---------------------------------------------------------------- the server


def test_the_default_wardrobe_key_is_derived_not_written_down():
    """If someone edits the style's garment, the key must follow it rather than become
    a lie. Derived by matching the prompt text, so the two cannot drift apart."""
    assert default_wardrobe_key(PREVIEW_STYLE) == "blazer-camisa"
    assert (
        WARDROBES[default_wardrobe_key(PREVIEW_STYLE)]["prompt"]
        == STYLES[PREVIEW_STYLE]["wardrobe"]
    )


def test_the_preview_says_which_wardrobe_it_used():
    """Without this the page has to guess, and a guess here is how the promise broke."""
    body = post(build()).json()
    assert body["wardrobe"] == "blazer-camisa", body


def test_the_preview_is_a_sample_of_that_delivery():
    """F6's actual requirement: the preview must be what the customer would receive if
    they left the selector alone. Same prompt, same wardrobe, same variant."""
    delivered = build_prompt(PREVIEW_STYLE, 0, wardrobe=default_wardrobe_key(PREVIEW_STYLE))
    preview = build_prompt(PREVIEW_STYLE, 0)
    assert preview == delivered, "the preview is not a sample of the default delivery"


def test_a_chosen_wardrobe_still_wins_for_the_four_finals():
    """Held-out. F6 says do not change the final prompts: the customer's choice is the
    product they bought."""
    chosen = build_prompt(PREVIEW_STYLE, 0, wardrobe="camisa-azul")
    assert WARDROBES["camisa-azul"]["prompt"] in chosen
    assert STYLES[PREVIEW_STYLE]["wardrobe"] not in chosen


# ---------------------------------------------------------------- the page


def source() -> str:
    return strip_comments(FORM.read_text(encoding="utf-8"), language="tsx")


def test_the_page_keeps_the_wardrobe_the_preview_used():
    assert "previewWardrobe" in source(), "the page throws away what the server told it"


def test_the_page_says_so_when_the_choice_differs_from_the_preview():
    """The whole unit, on the client. A customer who picks "Camisa azul" after seeing a
    navy blazer must be told which one the four photographs will use."""
    src = source()
    assert "Tu prueba se ha hecho con" in src, "no sentence explaining the difference"
    assert "wardrobe !== previewWardrobe" in src or "previewWardrobe !== wardrobe" in src, (
        "the sentence is not conditional on the two actually differing"
    )


def test_the_sentence_names_both_garments():
    """ "They will be different" is not an answer. It has to say which is which."""
    src = source()
    block = src[src.index("Tu prueba se ha hecho con") - 400 :][:900]
    assert block.count("labelFor") >= 2 or block.count("WARDROBES.find") >= 2, (
        "the sentence does not look up both labels"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
