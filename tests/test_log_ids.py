"""No logger call may print an order or session id longer than id_prefix keeps.

Task 08's audit found this real production line:

    ga4 purchase sent order_id=cs_test_REDACTED
    value=19.99 status=204

`order.id` IS the gallery's public id (app/logs.py's own docstring: "Never log a whole
session or order id"). Whoever can read that log line can open that customer's
gallery. `id_prefix` (app/logs.py) keeps the first twelve characters — enough to
correlate two lines and not enough to look anything up.

This test scans every `.py` file under `app/`, not only `app/adapters/ga4.py`: the
point is not today's offenders, it is that no future `logger.info(..., order.id)` can
slip back in unnoticed. The same value leaks under three different spellings in this
codebase: the `Order.id` attribute, and the bare `order_id` / `session_id` parameters
that hold that exact same string in `app/entry.py` (`enqueue`, `refund`) and
`app/main.py` (`gracias`) — Stripe's checkout session id IS this app's order id, read
straight from the call sites, not assumed. All three spellings are flagged unless the
identifier is wrapped in `id_prefix(...)`.

Comments are stripped first (tests/source_scan.py; the rule tests/test_source_scanners.py
enforces): app/adapters/ga4.py's own module docstring and `_transaction_id` docstring
talk *about* `order.id` in prose, and a naive text scan would flag its own explanation
rather than a real offender. String literals inside each logging call are stripped too
(`source_scan.strip_string_literals`, an explicit opt-in per that module's docstring,
right here because every offending line's format string literally contains the text
"order_id=%s" or "session_id=%s" — without stripping it the scanner would fire on its
own label instead of the code argument that follows it).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_scan import Scanner, strip_comments, strip_string_literals  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"

# Every call that ends up inside logging: the module-level `logger.<level>(...)` calls
# themselves, and `log_call(...)` (app/logs.py), which forwards its keyword fields
# straight into `logger.info(..., extra=...)`.
_CALL_START = re.compile(
    r"\blogger\.(?:debug|info|warning|error|exception|critical)\s*\(|\blog_call\s*\("
)

UNPREFIXED_ID = Scanner(
    name="unprefixed-order-or-session-id-in-log",
    # A fixed-width lookbehind, not a filter beside the pattern — tests/source_scan.py's
    # own lesson is that a scanner whose name describes a filter the pattern does not
    # itself enforce gets reused somewhere that filter is missing.
    #
    # `order.ga_session_id` and `SESSION_ID_PREFIX` are correctly left alone: `_` is a
    # word character, so `\b` cannot land between it and "session" inside
    # `ga_session_id`, and the pattern is case-sensitive so the constant name never
    # matches "session_id".
    #
    # Not registered: this repo's REGISTRY (tests/source_scan.py) is shared process-wide,
    # and tests/test_source_scanners.py validates every registered scanner against a
    # named fixture file under tests/fixtures/offenders/ that this one has no reason to
    # add. This scanner is proved instead, right here, by
    # test_the_scanner_catches_and_ignores_its_own_examples below.
    pattern=r"(?<!id_prefix\()\b(?:order\.id|order_id|session_id)\b",
    catches=("order.id", "order_id", "session_id"),
    ignores=(
        "id_prefix(order.id)",
        "id_prefix(order_id)",
        "id_prefix(session_id)",
        "order.ga_session_id",
        "SESSION_ID_PREFIX",
    ),
    language="py",
    register=False,
)


def _app_files() -> list[Path]:
    files = sorted(p for p in APP_DIR.rglob("*.py") if "__pycache__" not in p.parts)
    assert files, "no .py files found under app/ - the walk is broken, not the code"
    return files


def _call_spans(code: str) -> list[str]:
    """Every `logger.<level>(...)` / `log_call(...)` call, opening paren to its match.

    `code` must already have its string literals stripped to `""`, so a stray `)`
    inside a format string can never be miscounted as the call's own close paren.
    """
    spans = []
    for match in _CALL_START.finditer(code):
        depth = 0
        end = None
        for i in range(match.end() - 1, len(code)):
            if code[i] == "(":
                depth += 1
            elif code[i] == ")":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        assert end is not None, (
            f"unbalanced parentheses reading a logging call at offset {match.start()}"
        )
        spans.append(code[match.start() : end + 1])
    return spans


def _violations() -> list[str]:
    hits = []
    for path in _app_files():
        raw = path.read_text(encoding="utf-8")
        code = strip_string_literals(strip_comments(raw, language="py"))
        for span in _call_spans(code):
            for found in UNPREFIXED_ID.findall(span):
                snippet = " ".join(span.split())[:100]
                hits.append(f"{path.relative_to(ROOT).as_posix()}: {snippet!r} has {found!r}")
    return hits


def test_no_logger_call_in_app_formats_an_unprefixed_order_or_session_id():
    violations = _violations()
    assert not violations, (
        "logger call(s) in app/ print a full order/session id without id_prefix():\n"
        + "\n".join(violations)
    )


def test_the_scanner_catches_and_ignores_its_own_examples():
    """Same discipline tests/test_source_scanners.py enforces on its own registry: a
    pattern with no worked example, positive and negative, is a pattern nobody checked."""
    for example in UNPREFIXED_ID.catches:
        assert UNPREFIXED_ID.findall(example), f"missed its own example: {example!r}"
    for example in UNPREFIXED_ID.ignores:
        assert not UNPREFIXED_ID.findall(example), (
            f"fired on something it should ignore: {example!r}"
        )


def test_the_walk_actually_covers_app():
    """A scanner that silently walks zero files passes for the wrong reason."""
    names = {p.name for p in _app_files()}
    for expected in ("ga4.py", "core.py", "entry.py", "main.py", "logs.py"):
        assert expected in names, f"{expected} missing from the app/ walk"
