"""F7/O10: nothing configured logging, so the application never spoke.

This is why I2 was "cause unknown from outside". `/api/gracias` logs on every refusal
path - "gracias: session lookup failed for %s" and "gracias: refused ... payment_status"
- and NEITHER line is anywhere in Cloud Run. The root logger defaults to WARNING with no
handler, so every `logger.info` in this repository went nowhere. The 404s were visible
only as uvicorn access lines, which cannot say which branch produced them.

What survived was `logger.error` and `logger.exception`, through Python's last-resort
handler to stderr, which is how the fal content-policy traceback was found at all.

Cloud Run parses a JSON object on stdout and reads `severity` and `message` from it,
so one line of JSON per record is both the structured format and the human one.
No dependency: `json` and `logging` are in the standard library.
"""

import io
import json
import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.logs import JsonFormatter, configure_logging, id_prefix, log_call  # noqa: E402


@pytest.fixture
def captured():
    """A root logger writing to a buffer, restored afterwards."""
    root = logging.getLogger()
    saved, saved_level = root.handlers[:], root.level
    buffer = io.StringIO()
    root.handlers = []
    configure_logging(stream=buffer)
    yield buffer
    root.handlers, root.level = saved, saved_level


def lines(buffer) -> list[dict]:
    return [json.loads(raw) for raw in buffer.getvalue().splitlines() if raw.strip()]


def test_an_info_line_reaches_the_stream_at_all():
    """The whole defect, in one assertion. Before this, it did not."""
    root = logging.getLogger()
    saved, saved_level = root.handlers[:], root.level
    buffer = io.StringIO()
    root.handlers = []
    try:
        configure_logging(stream=buffer)
        logging.getLogger("app.main").info("gracias: refused session_id=%s", "cs_test_abc")
        assert buffer.getvalue().strip(), "logger.info still goes nowhere"
    finally:
        root.handlers, root.level = saved, saved_level


def test_every_record_is_one_json_object_on_one_line(captured):
    logging.getLogger("app.main").info("hello %s", "world")
    logging.getLogger("app.core").warning("careful")
    rendered = captured.getvalue().splitlines()
    assert len(rendered) == 2
    for raw in rendered:
        json.loads(raw)  # raises if it is not one object per line


def test_severity_is_the_field_cloud_run_reads(captured):
    """Cloud Run reads `severity`, not `level`. Getting the name wrong means every line
    arrives as DEFAULT and the console cannot filter."""
    logging.getLogger("app.main").warning("careful")
    assert lines(captured)[0]["severity"] == "WARNING"


def test_the_message_is_formatted_not_a_template(captured):
    """Lazy %s formatting is the rule (craft.md); the record must still render."""
    logging.getLogger("app.main").info("refused %s after %sms", "cs_test_abc", 12)
    assert lines(captured)[0]["message"] == "refused cs_test_abc after 12ms"


def test_the_route_and_the_id_prefix_travel_with_the_line(captured):
    logging.getLogger("app.main").info(
        "refused", extra={"route": "/api/gracias", "order": id_prefix("cs_test_a1wOChYnTDQ")}
    )
    entry = lines(captured)[0]
    assert entry["route"] == "/api/gracias"
    assert entry["order"] == "cs_test_a1wO"


def test_an_id_is_truncated_to_twelve_characters():
    """The brief says the first twelve only. A Stripe session id is enough to look up a
    customer's order, so the log gets the handle and not the key."""
    assert id_prefix("cs_test_REDACTED") == "cs_test_a1wO"
    assert len(id_prefix("cs_test_REDACTED")) == 12
    assert id_prefix("") == ""
    assert id_prefix(None) == ""


def test_latency_is_a_number_not_a_sentence(captured):
    """So it can be graphed. `log_call` is what every external adapter uses."""
    log_call(logging.getLogger("app.adapters.fal"), "fal.edit", started=0.0, now=lambda: 1.25)
    entry = lines(captured)[0]
    assert entry["latency_ms"] == 1250
    assert isinstance(entry["latency_ms"], int)
    assert entry["call"] == "fal.edit"


def test_an_exception_keeps_its_traceback_in_the_message(captured):
    """logger.exception is how the fal content-policy body was found. It must survive
    JSON encoding as text rather than being dropped."""
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("app.main").exception("gracias: lookup failed for %s", "cs_test_a")
    entry = lines(captured)[0]
    assert entry["severity"] == "ERROR"
    assert "ValueError: boom" in entry["message"]
    assert "Traceback" in entry["message"]


def test_configuring_twice_does_not_double_every_line(captured):
    """Cloud Run calls build() at import; a test or a reload can call it again. Two
    handlers means two copies of every line and double the log bill."""
    configure_logging(stream=captured)
    configure_logging(stream=captured)
    logging.getLogger("app.main").info("once")
    assert len(lines(captured)) == 1


def test_it_writes_to_stdout_by_default():
    """Cloud Run reads structured logs from stdout. stderr is where unstructured output
    goes and is what the last-resort handler was already using."""
    root = logging.getLogger()
    saved = root.handlers[:]
    root.handlers = []
    try:
        configure_logging()
        handler = root.handlers[0]
        assert handler.stream is sys.stdout
        assert isinstance(handler.formatter, JsonFormatter)
    finally:
        root.handlers = saved


def test_a_message_with_a_quote_does_not_break_the_line(captured):
    """A log line that is not valid JSON is worse than no log line: Cloud Run keeps it
    as an opaque string and the severity filter stops working."""
    logging.getLogger("app.main").info('he said "no" and\nthen left')
    entry = lines(captured)[0]
    assert entry["message"] == 'he said "no" and\nthen left'


def test_no_route_logs_a_whole_session_id():
    """F7 says twelve characters. A whole Stripe session id in a log is a key, not a
    handle: it is enough to look up a customer's order. This caught `session_id[:14]`
    left behind in /api/gracias from before `id_prefix` existed."""
    import re

    sys.path.insert(0, str(ROOT / "tests"))
    from source_scan import strip_comments

    source = strip_comments((ROOT / "app" / "main.py").read_text(encoding="utf-8"), language="py")
    stray = re.findall(r"session_id\[:\d+\]|order\.id\[:\d+\]", source)
    assert not stray, f"truncate with id_prefix() instead of a literal slice: {stray}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
