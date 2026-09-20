"""The free preview: one generated headshot, before anyone has paid.

Order of operations matters. Everything that can fail cheaply happens before
anything that costs money: decode and normalise the bytes first (a truncated JPEG
dies here), then store the sources, then make the single fal call. The call runs at
0.5K — it is the one endpoint strangers can reach, and the rate limiter in
guards.py is the other half of the ceiling on that bill.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.core import ImageModel
from app.guards import build_prompt
from app.images import normalise_all

logger = logging.getLogger(__name__)

PREVIEW_STYLE = "corporativo"


@dataclass
class Preview:
    """Callable: validated upload bytes -> a signed address the browser may load.

    Unit C1. This used to return whatever address fal handed back - something on
    `v3b.fal.media` - straight to the page. Two things were wrong with that, and the
    first one was live from the moment the site got security headers:

    1. `img-src` has never contained a fal host (`git log -S "fal.media"` is empty), so
       the browser refused the image and the visitor got a broken-image icon where their
       own face should have been. Adding fal to the policy is the wrong fix twice over:
       fal's own documentation shows three different result hostnames and a fallback
       chain, so there is no stable host to allowlist, and
    2. fal's result files are "available for at least 7 days by default" and "publicly
       accessible - anyone with the URL can access the file until it expires". A
       customer's face should not sit on a public third-party address for a week.

    So the preview now goes where the gallery's images already go: into the private
    bucket, read back through a signed URL on `storage.googleapis.com`, which the policy
    allows because that is where this application's images have always come from.
    """

    put_source: Callable[[str, bytes], str]  # key, jpeg bytes -> gs:// uri
    model: ImageModel
    store_result: Callable[[str, str], str]  # key, remote url -> gs:// uri
    sign: Callable[[str], str]  # gs:// uri -> a short-lived signed https URL
    style: str = PREVIEW_STYLE

    def __call__(self, files: list[bytes], batch: str) -> str:
        """`batch` is minted by the HTTP layer, which signs it for the checkout call."""
        if not files:
            raise ValueError("no_files")
        images = normalise_all(files)  # raises before anything is stored or paid for
        uris = [self.put_source(f"previews/{batch}/{i}.jpg", data) for i, data in enumerate(images)]
        logger.info("preview sources stored batch=%s count=%d", batch, len(uris))
        remote = self.model.edit(uris, build_prompt(self.style, 0))
        stored = self.store_result(f"previews/{batch}/preview.jpg", remote)
        logger.info("preview result stored batch=%s", batch)
        return self.sign(stored)
