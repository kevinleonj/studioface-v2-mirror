"""O1: the bundle contained exactly one Turnstile call, and it was `render`.

A Turnstile token is single-use and expires after five minutes - Cloudflare, verbatim:
"Each token can only be validated once. A replayed token will be rejected with the
`timeout-or-duplicate` error code." Nothing ever called `reset`, so after any failed
preview every retry replayed a spent token. Kevin's own production sequence:

    13:27:09  POST /api/preview  500  8.8s   fal content_policy_violation
    13:28:08  POST /api/preview  403  0.13s  spent token
    13:29:05  POST /api/preview  200  11.3s  after a page reload
    13:33:39  POST /api/preview  403  0.10s  spent again

The 0.13s tells you it never reached fal.

## The part that is NOT documented, and how this is written because of it

Cloudflare documents that `reset()` regenerates a token. No Cloudflare page says whether
the fresh one arrives through the `callback` given to `render()`; four were read in full
(docs/verified.md, F1b). Assuming undocumented Turnstile behaviour is exactly what caused
this repository's earlier widget outage - `turnstile.ready()`, which their runtime
refuses with an async script tag.

So the implementation does not choose. The callback sets the token if it fires, and a
bounded poll of `getResponse(widgetId)` picks it up if it does not. These tests assert
BOTH paths exist, because removing either one is the silent half of the bug.

The behavioural proof - fail once, retry without reloading, succeed - is the local
browser walk with Cloudflare's dummy keys, which is where an undocumented behaviour
actually gets settled.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from source_scan import strip_comments  # noqa: E402

FORM = ROOT / "frontend" / "src" / "components" / "upload-form.tsx"
BUNDLE = ROOT / "frontend" / "out" / "_next" / "static" / "chunks"


def source() -> str:
    """Comments stripped first (M4): this file's own prose names every symbol below."""
    return strip_comments(FORM.read_text(encoding="utf-8"), language="tsx")


def test_the_widget_id_render_returns_is_kept():
    """`reset()` takes the id `render()` returned and nothing else. Not keeping it is
    why there was no reset call to write."""
    src = source()
    assert re.search(r"widgetId\.current\s*=\s*window\.turnstile\.render\(", src), (
        "render()'s return value is still being thrown away"
    )


def test_reset_is_called():
    assert "window.turnstile.reset(" in source(), "nothing resets the widget"


def test_the_token_is_cleared_at_the_same_moment():
    """A reset with the old token still in the ref is the same bug with extra steps."""
    src = source()
    block = src[src.index("const refreshChallenge") :]
    block = block[: block.index("}, [])")]
    assert 'turnstileToken.current = ""' in block, "the spent token is not cleared"
    assert "window.turnstile.reset(" in block


def test_a_fresh_token_is_picked_up_whether_or_not_the_callback_refires():
    """The undocumented half. Both paths must exist."""
    src = source()
    assert "getResponse" in src, "no poll; this assumes the callback re-fires"
    assert "callback: (token: string)" in src, "no callback; this assumes it does not"


def test_every_preview_attempt_refreshes_the_challenge():
    """Success too: the visitor may come back and try another photograph."""
    src = source()
    block = src[src.index("const preview = useCallback") :]
    block = block[: block.index("const checkout")]
    assert "finally {" in block and "refreshChallenge()" in block, (
        "the token is not refreshed after every attempt"
    )


def test_the_retry_button_refreshes_too():
    """O1's sting: "Volver a intentarlo" walked straight into the same spent token."""
    src = source()
    block = src[src.index("Volver a intentarlo") - 900 : src.index("Volver a intentarlo")]
    assert "refreshChallenge()" in block, "the retry button reuses the spent token"


def test_the_submit_button_waits_for_a_fresh_token_and_says_so():
    src = source()
    assert 'challenge === "refreshing"' in src, "the button does not wait for a token"
    assert "Comprobando que eres una persona" in src, "the wait is not explained"


def test_the_built_bundle_really_contains_reset():
    """The source is not what ships. This is the assertion that would have caught O1:
    a grep of the shipped JavaScript found `turnstile.render` and nothing else."""
    if not BUNDLE.is_dir():
        pytest.skip("no build; CI builds first")
    shipped = " ".join(p.read_text(encoding="utf-8", errors="ignore") for p in BUNDLE.rglob("*.js"))
    calls = set(re.findall(r"turnstile\.(\w+)", shipped))
    assert "render" in calls, f"no turnstile calls at all in the bundle: {calls}"
    assert "reset" in calls, f"the shipped bundle still has no reset: {sorted(calls)}"


def test_the_mount_was_not_restructured():
    """M2. The widget took two outages to mount at all: `useEffect(..., [])` returned
    early on `!window.turnstile`, and `turnstile.ready()` is refused by Cloudflare with
    an async script tag. F1 adds a reset; it does not touch how the thing mounts."""
    src = source()
    assert "turnstile.ready(" not in src, "turnstile.ready() is back; Cloudflare refuses it"
    assert "rendered.current" in src, "the double-render guard is gone"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
