"""The upload thumbnails are `blob:` URLs, and the policy has to allow them.

P3, and this is the second time the same shape of defect has shipped. I1 was the
preview image refused by `img-src` because the policy did not name fal's host. This is
the same fault in a new place: task 12 gave the visitor a thumbnail per chosen file
built with `URL.createObjectURL`, which produces a `blob:` URL, and `img-src` named
`'self'` and `data:` but never `blob:`. The browser refused all four, so the visitor
picked four photos and saw four empty squares.

`scripts/check.py upload_thumbnails` went green through all of that, because it only
greps the bundle for the `data-sf-thumbs` marker. A marker in the bundle is not a
picture on the screen. The browser walk is what caught it, with four
`securitypolicyviolation` events reading `img-src blob`.

So this test is two-sided on purpose: the policy must allow `blob:`, AND the form must
still be the kind of thing that needs it. Either half alone can pass while the visitor
sees nothing.
"""

from __future__ import annotations

from pathlib import Path

from tests.source_scan import strip_comments

ROOT = Path(__file__).resolve().parent.parent
FORM = ROOT / "frontend" / "src" / "components" / "upload-form.tsx"


def form_code() -> str:
    """Comments stripped first: this file's own comments name both markers, so a grep
    over the raw text would pass against a component that had lost the feature."""
    return strip_comments(FORM.read_text(encoding="utf-8"), language="tsx")


def test_the_policy_allows_blob_images() -> None:
    """The served header, not the constant: the middleware is what the browser obeys."""
    from app.main import CSP

    sources = CSP["img-src"]
    assert "blob:" in sources, (
        "img-src does not allow blob:, so every upload thumbnail is refused by the "
        f"browser and the visitor sees empty squares. img-src is: {' '.join(sources)}"
    )


def test_the_upload_form_still_builds_blob_urls() -> None:
    """The other half. If this ever stops being true, the allowance above is dead
    weight and should go - but until then the two must agree."""
    source = form_code()
    assert "URL.createObjectURL" in source, (
        "the upload form no longer creates object URLs; if the thumbnails were "
        "removed or rebuilt, drop blob: from img-src in the same change"
    )


def test_the_thumbnail_container_is_still_the_one_the_check_looks_for() -> None:
    """Held out: the production check greps for this marker, so if it moves, the check
    silently passes against a page that has no thumbnails at all."""
    source = form_code()
    assert "data-sf-thumbs" in source


def test_blob_is_not_allowed_anywhere_it_was_not_asked_for() -> None:
    """One check nobody asked for. blob: in script-src would let a page run code it
    assembled itself, which is a real escape hatch; the thumbnails need it for images
    only."""
    from app.main import CSP

    for directive in ("script-src", "script-src-elem", "default-src", "connect-src"):
        sources = CSP.get(directive, [])
        assert "blob:" not in sources, (
            f"blob: leaked into {directive}; the thumbnails only ever needed it in img-src"
        )
