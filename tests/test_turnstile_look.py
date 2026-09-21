"""The Cloudflare human check rendered dark, in English, and left-aligned on a light,
Spanish page.

`turnstile.render()` never said otherwise, so the widget fell back to its own defaults
instead of the page's. Cloudflare documents the fix as three render() options - theme,
language, size - at
developers.cloudflare.com/turnstile/get-started/client-side-rendering/widget-configurations
(verified through Context7, 20 Sep 2026).

This does not touch how the widget mounts or resets (that is test_turnstile_widget.py
and test_turnstile_reset.py, both hard-won). It adds three keys to the one existing
options object passed to turnstile.render() and changes nothing else in that call.
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


def render_call() -> str:
    """The exact options object passed to turnstile.render(), comments stripped."""
    src = strip_comments(FORM.read_text(encoding="utf-8"), language="tsx")
    start = src.index("widgetId.current = window.turnstile.render(")
    end = src.index("});", start)
    return src[start:end]


def test_the_widget_is_light_spanish_and_full_width():
    call = render_call()
    assert re.search(r'theme:\s*"light"', call), (
        "no light theme: the widget still renders dark on a light page"
    )
    assert re.search(r'language:\s*"es"', call), (
        "no Spanish language: the widget still renders in English on a Spanish page"
    )
    assert re.search(r'size:\s*"flexible"', call), "no flexible size: the widget is not full width"


def test_nothing_else_in_the_call_changed():
    """The same render() call, not a new one: sitekey and the three callbacks that make
    the F1 reset logic work are still exactly there."""
    call = render_call()
    assert "sitekey: TURNSTILE_SITEKEY" in call
    assert "callback: (token: string) => {" in call
    assert '"error-callback": () => {' in call
    assert '"expired-callback": () => {' in call


def test_the_widget_mount_and_reset_were_not_restructured():
    """M2, repeated: this task adds three options, it does not touch the mount effect,
    the widgetId ref, or the reset/poll pair."""
    src = strip_comments(FORM.read_text(encoding="utf-8"), language="tsx")
    assert "turnstile.ready(" not in src, "turnstile.ready() is back; Cloudflare refuses it"
    assert "rendered.current" in src, "the double-render guard is gone"
    assert "widgetId.current = window.turnstile.render(" in src, (
        "render() call was moved or rewritten"
    )
    assert "window.turnstile.reset(" in src, "reset() is gone"
    assert "getResponse" in src, "the getResponse poll is gone"


def test_the_built_bundle_really_ships_the_three_options():
    """The source is not what ships. Proven against the actual export, the same way
    test_turnstile_reset.py proves reset() survives the build."""
    if not BUNDLE.is_dir():
        pytest.skip("no build; CI builds first")
    shipped = " ".join(p.read_text(encoding="utf-8", errors="ignore") for p in BUNDLE.rglob("*.js"))
    assert re.search(r'theme:\s*"light"', shipped), "the built bundle lacks the light theme"
    assert re.search(r'language:\s*"es"', shipped), "the built bundle lacks the Spanish language"
    assert re.search(r'size:\s*"flexible"', shipped), "the built bundle lacks the flexible size"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
