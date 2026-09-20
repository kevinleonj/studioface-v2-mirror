"""The free preview was unreachable in production, for everybody, deterministically.

Found while trying to automate the 4242 test purchase (issue #4). Measured against
https://studioface.app with an uninstrumented browser, six time points:

    t=    0ms  window.turnstile=undefined  widget children=0  token fields=0
    t=  500ms  window.turnstile=object     widget children=0  token fields=0
    t= 1500ms  window.turnstile=object     widget children=0  token fields=0
    t= 3000ms  window.turnstile=object     widget children=0  token fields=0
    t= 6000ms  window.turnstile=object     widget children=0  token fields=0
    t=10000ms  window.turnstile=object     widget children=0  token fields=0

The container `<div class="min-h-[65px]">` never gained a child and
`input[name="cf-turnstile-response"]` never appeared. The cause is four words:

    if (!TURNSTILE_SITEKEY || !widget.current || !window.turnstile) return;

inside a `useEffect(..., [])`. Next loads the Turnstile script `afterInteractive`, so it
has not run when React fires mount effects — `window.turnstile` is undefined at exactly
that moment and an object 500ms later. The effect returns and never runs again.

So `turnstileToken.current` stays "", `/api/preview` receives an empty token,
`verify_turnstile` returns False for an empty token, and every visitor who asks for the
free preview gets 403 and "No hemos podido verificar que no eres un robot. Recarga la
página." Reloading does not help, because the race is deterministic rather than
intermittent. Nobody could reach the preview, so nobody could buy.

Cloudflare documents three ways to do this and none of them is "call render on mount":
`?onload=<fn>` on the script URL, `turnstile.ready(cb)`, or window.onload
(docs/verified.md, 18 Sep 2026). We use the Script onLoad callback, which is the same
guarantee expressed in the framework that owns the tag.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FORM = ROOT / "frontend" / "src" / "components" / "upload-form.tsx"
LANDING = ROOT / "frontend" / "src" / "app" / "page.tsx"
COMMENT = re.compile(r"\{/\*.*?\*/\}|/\*.*?\*/|//[^\n]*", re.S)


def form() -> str:
    return COMMENT.sub("", FORM.read_text(encoding="utf-8"))


def effect_body() -> str:
    """The mount effect that owns the widget, comments stripped."""
    src = form()
    start = src.index("useEffect(() => {", src.index("const rendered"))
    return src[start : src.index("}, []);", start)]


def test_a_script_that_has_not_arrived_is_waited_for_rather_than_given_up_on():
    """The exact shape of the bug was a one-shot effect that gave up if the script had
    not arrived, in a framework that guarantees the script arrives later.

    This asserts the PROPERTY, not the absence of a token. My first version banned
    `!window.turnstile) return` outright, which also fails the correct guard inside the
    render function — a guard that has to be there, because render() is called from a
    callback that can fire after unmount. Banning a string is not the same as requiring
    a behaviour."""
    body = effect_body()
    assert "setInterval" in body or "ready(" in body, (
        "nothing retries or waits: if the script is late the widget never appears"
    )
    assert "setTimeout" in body, (
        "no upper bound on the wait, so a script that never arrives leaves the visitor "
        "looking at an empty box with no explanation"
    )
    assert "clearInterval" in body, "the poll is never stopped"


def test_render_is_never_called_before_the_script_has_defined_turnstile():
    """And specifically NOT via turnstile.ready(), which is the first pattern in
    Cloudflare's docs and is invalid here. Their runtime says so out loud:

        TurnstileError: [Cloudflare Turnstile] Remove async/defer from the Turnstile
        api.js script tag before using turnstile.ready().

    Next injects the tag async. My first fix used ready(), it threw, and the widget
    still never rendered — identical symptom, different cause. Once `window.turnstile`
    is an object, api.js has executed and render() is safe."""
    body = effect_body()
    assert "turnstile.ready(" not in body, (
        "ready() throws against an async script tag; Cloudflare's runtime refuses it"
    )
    assert re.search(r"if \(window\.turnstile\)", body), (
        "render is not gated on the script having defined turnstile"
    )


def test_the_script_tells_the_form_when_it_has_loaded():
    """The landing page owns the <Script> tag and the form owns the container, so the
    signal has to cross between them. Without it the form is guessing again."""
    page = COMMENT.sub("", LANDING.read_text(encoding="utf-8"))
    assert "turnstile" in page.lower(), "the landing page no longer loads Turnstile at all"


def test_the_widget_is_only_rendered_once():
    """turnstile.render() on an element that already holds a widget throws, and React
    runs effects twice in development Strict Mode. A guard, not an assumption."""
    src = form()
    assert re.search(r"(rendered|widgetId)\.current", src), (
        "nothing records that the widget has already been rendered"
    )


def test_the_visitor_is_told_when_verification_could_not_start():
    """The old failure was silent until the moment they pressed the button, and then it
    blamed them: 'No hemos podido verificar que no eres un robot'. If the challenge never
    loaded, that is ours to say, not theirs to guess."""
    raw = FORM.read_text(encoding="utf-8")
    assert "error-callback" in raw or "errorCallback" in raw or '"error-callback"' in raw, (
        "no error callback, so a challenge that fails to load is indistinguishable from one "
        "that was never asked for"
    )


# Cloudflare's documented always-pass / always-block / always-challenge site keys. They
# are public constants, which is exactly why shipping one is dangerous: the widget looks
# present and the challenge is a no-op.
TEST_SITEKEYS = (
    "1x00000000000000000000AA",
    "1x00000000000000000000BB",
    "2x00000000000000000000AB",
    "2x00000000000000000000BB",
    "3x00000000000000000000FF",
)
EXPORT = ROOT / "frontend" / "out"


@pytest.mark.skipif(not EXPORT.is_dir(), reason="no build; CI builds first")
def test_no_build_ever_ships_a_cloudflare_test_site_key():
    """The guard that lets the end-to-end purchase be automated safely.

    A local or CI run uses 1x00000000000000000000AA so the flow can be driven without a
    human, and that is fine — as long as it can never reach a deploy. The site key is
    inlined into the client bundle at build time, so this is checkable against the
    artefact itself rather than against anybody's environment, and it needs no secret:
    a site key is public by definition, which is the whole reason a test one is unsafe.

    Checked in the bundle, not in .env. Nothing here reads a secret, and nothing here
    needs to."""
    shipped = []
    for path in EXPORT.rglob("*"):
        if path.suffix not in {".js", ".html", ".txt"} or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for key in TEST_SITEKEYS:
            if key in text:
                shipped.append(f"{path.relative_to(EXPORT).as_posix()}: {key}")
    assert not shipped, f"a Cloudflare TEST site key is in the build: {shipped[:5]}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
