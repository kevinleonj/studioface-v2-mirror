"""Make the application audible.

O10. Nothing in this repository configured logging, so the root logger sat at its
default of WARNING with no handler and every `logger.info` went nowhere. That is why
I2 was "cause unknown from outside": `/api/gracias` logs on both of its refusal paths
and neither line exists in Cloud Run. Only `logger.error` and `logger.exception`
survived, through Python's last-resort handler to stderr, which is how the fal
content-policy traceback was found at all.

Cloud Run parses a JSON object written to stdout and reads `severity` and `message`
from it, so one JSON object per line is both the structured format and the readable
one. `json` and `logging` are standard library: no new dependency.

Never log a whole session or order id. `id_prefix` keeps twelve characters, which is
enough to correlate two lines and not enough to look anything up.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any, TextIO

# The fields an adapter or a route may attach with `extra=`. Anything else on the
# record is ignored, so a stray attribute cannot quietly reshape the log schema.
EXTRA_FIELDS = ("route", "order", "batch", "call", "latency_ms", "detail", "status")

ID_PREFIX_LENGTH = 12


def id_prefix(value: str | None) -> str:
    """The first twelve characters of an id, which is a handle and not a key."""
    return (value or "")[:ID_PREFIX_LENGTH]


class JsonFormatter(logging.Formatter):
    """One JSON object per record, with the field names Cloud Run reads."""

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.exc_info:
            # Keep the traceback as text inside `message`. Cloud Run groups an error by
            # its message, and a traceback on its own line would be a separate entry.
            message = f"{message}\n{self.formatException(record.exc_info)}"
        payload: dict[str, Any] = {
            "severity": record.levelname,
            "message": message,
            "logger": record.name,
        }
        for field in EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: int = logging.INFO, stream: TextIO | None = None) -> None:
    """Attach exactly one JSON handler to the root logger.

    Idempotent: Cloud Run builds the app at import and a test or a reload can call this
    again, and two handlers would mean two copies of every line and double the bill.
    """
    root = logging.getLogger()
    for handler in root.handlers:
        if getattr(handler, "_studioface", False):
            handler.setStream(stream or sys.stdout)  # type: ignore[attr-defined]
            root.setLevel(level)
            return
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler._studioface = True  # type: ignore[attr-defined]
    root.handlers = [handler]
    root.setLevel(level)
    # uvicorn installs its own handlers for these; let them through ours instead so the
    # access line and our line are the same shape.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True


def log_call(
    logger: logging.Logger,
    call: str,
    started: float,
    now: Any = time.monotonic,
    **fields: Any,
) -> None:
    """One line per outbound call, with its latency as a number.

    craft.md: "every outbound call has an explicit timeout, bounded retry with backoff,
    and a log line with latency". A number rather than a sentence, so it can be graphed.
    """
    logger.info(
        "%s took %sms",
        call,
        int((now() - started) * 1000),
        extra={"call": call, "latency_ms": int((now() - started) * 1000), **fields},
    )
