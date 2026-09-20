"""The walk: a real browser, the real app, Cloudflare's dummy keys, real fal, Stripe test.

P2 is why this exists. "Behind the human check: not tested" was a caveat in four reports
while the whole paid funnel sat behind it, and three defects lived there for a day.

Run it with the server from scripts/run_funnel.py:

    .venv\\Scripts\\python.exe scripts\\run_funnel.py --serve-only
    .venv\\Scripts\\python.exe -m pytest tests/e2e/test_funnel.py -v -s

It refuses to start unless the Stripe key is a test key and the base is loopback.

## Cost

The cheap half spends ONE fal image: the failing attempt is a text file renamed .jpg,
which the server rejects at 422 before fal is ever called, so fail-then-retry costs only
the retry. The paid walk spends four more. Marked so each can be run on its own.

## The question this walk exists to settle

Cloudflare documents that `turnstile.reset()` regenerates a token. No Cloudflare page
says whether the fresh one arrives through the `callback` given to `render()` or must be
read with `getResponse()` - four pages were read and none states it (docs/verified.md,
F1b). Unit F1 handles both. `test_which_path_delivers_the_fresh_token` decides it by
experiment: neuter `getResponse` and see whether the control recovers anyway.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

BASE = os.environ.get("FUNNEL_BASE", "http://127.0.0.1:8099")
FACE = ROOT / "tests" / "fixtures" / "faces" / "face.jpg"

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_FUNNEL") != "1",
    reason="the funnel walk spends real fal credits; set RUN_FUNNEL=1",
)


def _reachable() -> bool:
    try:
        return httpx.get(BASE + "/health", timeout=3.0).status_code == 200
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="module")
def page():
    if not BASE.startswith(("http://127.0.0.1", "http://localhost")):
        raise SystemExit(f"refusing: {BASE} is not loopback")
    if not _reachable():
        pytest.skip(f"nothing serving {BASE}; run scripts/run_funnel.py --serve-only")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1280, "height": 900}, accept_downloads=True
        )
        p = context.new_page()

        # B3. Anything the page's own policy refuses, and anything it logs as an error.
        p.violations = []  # type: ignore[attr-defined]
        p.console_errors = []  # type: ignore[attr-defined]
        p.add_init_script(
            "window.addEventListener('securitypolicyviolation', (e) => {"
            "  (window.__violations ||= []).push(e.violatedDirective + ' ' + e.blockedURI); });"
        )
        p.on(
            "console",
            lambda m: (
                p.console_errors.append(m.text)  # type: ignore[attr-defined]
                if m.type == "error"
                else None
            ),
        )
        yield p
        browser.close()


def violations(page) -> list[str]:
    return page.evaluate("() => window.__violations || []")


def wait_for_token(page, timeout=30_000) -> None:
    """A token in the hidden field. NOT the submit button: that is also disabled while
    no file is chosen, so waiting on it conflates two different states - which is what
    the first version of this walk did, and it reported a widget failure against a
    widget that was working."""
    page.wait_for_function(
        "() => { const i = document.getElementsByName('cf-turnstile-response')[0];"
        "        return i && i.value.length > 0; }",
        timeout=timeout,
    )


def spy_on_reset(page) -> None:
    """Count calls to turnstile.reset from inside the page.

    This is the real evidence for F1, and the reason the walk needs it: Cloudflare's
    dummy site key emits the CONSTANT token `XXXX.DUMMY.TOKEN.XXXX`, and the dummy
    secret accepts it every time. The dummy pair does NOT reproduce single-use
    semantics, so a retry that succeeds proves nothing on its own - it would have
    succeeded before F1 too. What distinguishes the fixed code is that it calls reset
    at all.
    """
    page.evaluate(
        "() => { if (window.__resetCount === undefined) {"
        "   window.__resetCount = 0;"
        "   const real = window.turnstile.reset.bind(window.turnstile);"
        "   window.turnstile.reset = (id) => { window.__resetCount++; return real(id); };"
        " } }"
    )


def reset_count(page) -> int:
    return page.evaluate("() => window.__resetCount || 0")


def submit(page):
    page.get_by_role("button", name=re.compile("prueba", re.I)).first.click()


# ---------------------------------------------------------------- the free half


def test_the_landing_page_loads_with_no_policy_violation(page):
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    assert violations(page) == [], f"content-security-policy refused: {violations(page)}"


def test_the_dummy_widget_mounts_and_issues_a_token(page):
    """P2: Cloudflare publishes these keys for exactly this and they were never used."""
    wait_for_token(page)
    value = page.evaluate("() => document.getElementsByName('cf-turnstile-response')[0].value")
    assert value == "XXXX.DUMMY.TOKEN.XXXX", f"not the documented dummy token: {value!r}"
    spy_on_reset(page)


def test_a_file_that_is_not_an_image_gets_its_own_sentence(page, tmp_path):
    """F2/O2, and it costs no fal image: the server refuses at 422 before calling fal."""
    fake = tmp_path / "not-an-image.jpg"
    fake.write_text("this is text, not a JPEG\n", encoding="utf-8")
    page.set_input_files("input[type=file]", str(fake))
    submit(page)
    # Wait for the TEXT, not the element: the node appears before React fills it, and
    # the first version of this walk read an empty string off it.
    page.wait_for_function(
        "() => [...document.querySelectorAll('[role=alert]')]"
        "  .some((e) => e.textContent.includes('imagen'))",
        timeout=30_000,
    )
    said = page.evaluate(
        "() => [...document.querySelectorAll('[role=alert]')].map((e) => e.textContent.trim())"
    )
    assert any("no es una imagen" in t for t in said), said


def test_the_widget_was_reset_after_the_failed_attempt(page):
    """O1's actual evidence, and the only kind the dummy keys can give.

    The dummy token is a constant and the dummy secret accepts it repeatedly, so a
    successful retry would have happened before F1 as well. What changed is that the
    page now spends the token and asks for another one. This asserts the call.
    """
    assert reset_count(page) >= 1, (
        "turnstile.reset was never called after the failed preview; "
        "every retry is replaying the same token, which in production is O1"
    )


def test_the_retry_succeeds_without_reloading_the_page(page):
    """O1 end to end. Necessary but, with dummy keys, not sufficient on its own - see
    the reset-count test above for the discriminating evidence.

    Spends ONE fal image.
    """
    wait_for_token(page, timeout=30_000)
    page.set_input_files("input[type=file]", str(FACE))
    submit(page)
    # Decoded, not merely present - the same race that failed the paid walk's gallery
    # assertion, in the half that happens to have been winning it.
    image = page.wait_for_selector("img[alt*='Prueba gratuita']", timeout=180_000)
    image.evaluate("el => el.complete || new Promise((r) => { el.onload = el.onerror = r; })")
    width = image.evaluate("el => el.naturalWidth")
    assert width > 0, "P4: the preview element exists but decoded nothing"
    assert violations(page) == [], f"the preview was refused by the policy: {violations(page)}"


def test_which_path_delivers_the_fresh_token(page):
    """The question Cloudflare does not answer, settled by experiment.

    `getResponse` is neutered and the widget reset. If the control recovers anyway, the
    `callback` given to `render()` re-fires. If it stays disabled, the poll is what
    delivers the token and removing it would have reintroduced O1.

    Costs nothing: it never submits.
    """
    page.reload(wait_until="domcontentloaded")
    wait_for_token(page, timeout=30_000)
    # Blind the poll, then spend the token. Whatever re-enables the control after this
    # cannot be `getResponse`.
    page.evaluate("() => { window.turnstile.getResponse = () => ''; }")
    page.set_input_files("input[type=file]", str(FACE))
    recovered = True
    try:
        page.evaluate(
            "() => { const i = document.getElementsByName('cf-turnstile-response')[0];"
            "        window.turnstile.reset(i.closest('div').id || undefined); }"
        )
        page.wait_for_function(
            "() => { const b = [...document.querySelectorAll('main button')]"
            "  .find((x) => x.textContent.includes('prueba')); return b && !b.disabled; }",
            timeout=15_000,
        )
    except Exception:  # noqa: BLE001 - the timeout IS the answer
        recovered = False

    delivered = "the render() callback re-fires" if recovered else "the getResponse poll"
    print(f"\n    TOKEN AFTER RESET IS DELIVERED BY: {delivered}")
    page.evaluate("() => { if (window.__real) window.turnstile.getResponse = window.__real; }")
    assert delivered  # recorded, not judged: either answer is a real finding


# ---------------------------------------------------------------- the paid half


@pytest.mark.skipif(os.environ.get("RUN_FUNNEL_PAID") != "1", reason="spends four fal images")
def test_paying_lands_on_the_gallery_with_four_real_images(page):
    """B2. Never on a JSON body - that is I2 - and every image must decode."""
    page.goto(BASE + "/", wait_until="domcontentloaded")
    wait_for_token(page, timeout=30_000)
    page.set_input_files("input[type=file]", str(FACE))
    submit(page)
    page.wait_for_selector("img[alt*='Prueba gratuita']", timeout=180_000)

    page.get_by_role("button", name=re.compile("Comprar", re.I)).click()
    page.wait_for_url(re.compile(r"checkout\.stripe\.com"), timeout=60_000)

    # NOT CONFIRMED by any vendor page (docs/verified.md, A4.4a): Stripe documents no
    # selectors for the hosted page, so these are unversioned and may break. They live in
    # tests/e2e/stripe_checkout_page.py behind a tripwire that costs no fal image, because
    # discovering the drift HERE costs five. A failure is reported as itself rather than
    # as a funnel defect.
    from tests.e2e.stripe_checkout_page import fill_test_card, pay

    fill_test_card(page)
    pay(page)

    page.wait_for_url(re.compile(r"/g/"), timeout=120_000)
    assert "detail" not in page.content()[:400].lower(), "landed on a JSON body (I2)"

    # Four elements existing is not four pictures. Measured 20 September on the real
    # delivered order: at the instant the fourth element appeared every image read
    # naturalWidth 0 and complete false, and 928 / true one second later. Waiting on the
    # COUNT and then asserting the WIDTH times the browser's decoder, not the gallery -
    # and it cost a whole paid walk to learn (docs/audit/paid-walk-2026-09-20.txt).
    page.wait_for_function(
        "() => { const i = [...document.querySelectorAll(\"img[alt^='Foto de perfil']\")];"
        "        return i.length === 4 && i.every((e) => e.complete && e.naturalWidth > 0); }",
        timeout=600_000,
    )
    widths = page.eval_on_selector_all(
        "img[alt^='Foto de perfil']", "els => els.map(e => e.naturalWidth)"
    )
    assert all(w > 0 for w in widths), f"P4: an image decoded nothing: {widths}"
    assert violations(page) == [], f"the gallery was refused by the policy: {violations(page)}"


@pytest.mark.skipif(os.environ.get("RUN_FUNNEL_PAID") != "1", reason="needs the paid walk")
def test_descargar_downloads_and_the_tab_stays_put(page):
    """O3. The reviewer measured no download event and a tab that navigated away."""
    before = page.url
    with page.expect_download(timeout=60_000) as caught:
        page.get_by_role("link", name=re.compile("Descargar", re.I)).first.click()
    download = caught.value
    assert download.suggested_filename.startswith("studioface-"), download.suggested_filename
    assert page.url == before, f"the tab navigated away to {page.url}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
