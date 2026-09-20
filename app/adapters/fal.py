"""fal.ai nano-banana-2/edit adapter.

Call shape verified 2026-09-17 (docs/verified.md): subscribe(application, arguments)
returns a dict whose "images" is a list of objects with a "url". output_format
defaults to png in the schema, so jpeg is passed explicitly.

Source images are stored as gs://bucket/key in a private bucket and fal fetches them
over ordinary HTTPS, so every gs:// URI is signed before it is sent. Nothing about
the bucket is ever made public.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core import ModelRefused
from app.logs import log_call

logger = logging.getLogger(__name__)

APPLICATION = "fal-ai/nano-banana-2/edit"

# fal answers a refused input with HTTP 422 and a body of `detail` items, each carrying a
# `type`. Anything else - 5xx, a timeout, a transport error - is an outage and is
# re-raised untouched, because a visitor cannot act on it.
# https://fal.ai/docs/documentation/model-apis/errors
REFUSAL_STATUS = 422
POLICY = "content_policy_violation"


def _refusal(exc: Exception) -> str | None:
    """The stable detail key for a fal refusal, or None if this is not one."""
    if getattr(exc, "status_code", None) != REFUSAL_STATUS:
        return None
    types = _error_types(exc)
    if POLICY in types:
        return "content_policy"
    return f"model_{types[0]}" if types else "model_refused"


def _error_types(exc: Exception) -> list[str]:
    """fal puts the type inside each `detail` item; older shapes use `error_type`."""
    body = getattr(exc, "message", None)
    if isinstance(body, list):
        found = [i.get("type") for i in body if isinstance(i, dict) and i.get("type")]
        if found:
            return found
    single = getattr(exc, "error_type", None)
    return [single] if single else []


def _default_subscribe(application: str, arguments: dict) -> Any:
    import fal_client

    return fal_client.subscribe(application, arguments=arguments)


@dataclass
class FalModel:
    """Implements the ImageModel port: edit(image_urls, prompt) -> url."""

    sign: Callable[[str], str]
    resolution: str = "1K"
    subscribe: Callable[..., Any] = field(default=_default_subscribe)

    def edit(self, image_urls: list[str], prompt: str) -> str:
        if not image_urls:
            raise ValueError("no_source_images")
        readable = [self.sign(u) if u.startswith("gs://") else u for u in image_urls]
        started = time.monotonic()
        try:
            return self._subscribe(readable, prompt, started)
        except Exception as exc:  # noqa: BLE001 - re-raised unless it is a refusal
            refusal = _refusal(exc)
            if refusal is None:
                raise
            logger.info("fal refused the input detail=%s", refusal)
            raise ModelRefused(refusal) from exc

    def _subscribe(self, readable: list[str], prompt: str, started: float) -> str:
        result = self.subscribe(
            APPLICATION,
            arguments={
                "prompt": prompt,
                "image_urls": readable,
                "resolution": self.resolution,
                "output_format": "jpeg",
                "aspect_ratio": "4:5",
            },
        )
        log_call(logger, "fal.edit", started, detail=self.resolution)
        latency_ms = int((time.monotonic() - started) * 1000)
        images = (result or {}).get("images") or []
        if not images or not images[0].get("url"):
            logger.error(
                "fal returned no image application=%s resolution=%s latency_ms=%s",
                APPLICATION,
                self.resolution,
                latency_ms,
            )
            raise ValueError("fal_returned_no_image")
        logger.info(
            "fal edit ok application=%s resolution=%s sources=%d latency_ms=%s",
            APPLICATION,
            self.resolution,
            len(readable),
            latency_ms,
        )
        return images[0]["url"]
