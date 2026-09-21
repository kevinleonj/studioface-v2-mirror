"""Browser edge cases for picking photos more than once. Task 27
(work/done/27-add-more-photos.md).

Boot the server first:

    .venv\\Scripts\\python.exe scripts\\run_upload_edges.py --serve-only

then, in another shell:

    .venv\\Scripts\\python.exe -m pytest tests/e2e/test_upload_edges.py -v -s

scripts/run_upload_edges.py with no flag does both for you, in one process, and exits
0 or 1 — that is the form the task's own check uses.

Every case here is client-side page behaviour: adding to the kept photos instead of
replacing them, skipping an exact duplicate, removing one, re-picking the same file,
and the notice a new pick must show without erasing an existing preview. None of it
needs a real preview to be generated. /api/preview is answered INSIDE the browser by
Playwright's own route interception before the request ever leaves the page — the
loopback server never receives it, let alone fal. scripts/run_upload_edges.py adds a
second, server-side guard in case a test here ever forgets to intercept.

WHY THIS BUG MATTERED (21 Sep 2026, Kevin's own browser): picking photos a second
time replaced the first photo and erased the preview, so the buy button vanished for
up to an hour. `test_preview_survives_a_new_pick` is the direct regression test for
that: it proves a second pick keeps the preview and the buy button on screen.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

BASE = os.environ.get("EDGES_BASE", "http://127.0.0.1:8098")
FACE = ROOT / "tests" / "fixtures" / "faces" / "face.jpg"
FACE2 = ROOT / "tests" / "fixtures" / "faces" / "face2.jpg"

# A signed-shaped answer with a value nobody will mistake for a real one. Only its
# SHAPE matters here (preview_url, batch, n, t, wardrobe) — the frontend never
# validates the signature, only /api/checkout does, and this test never presses buy.
FAKE_HANDLE = {
    "preview_url": "/__fake__/preview.jpg",
    "batch": "edges-test-batch",
    "n": 1,
    "t": "edges-test-signature",
    "wardrobe": "",
}

# Task 29, never-block-a-buyer. What /api/preview answers once the free previews for
# the hour are spent: `preview_url` null, `limited` true, and a handle shaped exactly
# like FAKE_HANDLE's — the frontend never checks the signature, only /api/checkout
# does, and this test never presses buy either.
LIMITED_HANDLE = {
    "preview_url": None,
    "batch": "edges-test-batch-limited",
    "n": 1,
    "t": "edges-test-signature-limited",
    "wardrobe": "",
    "limited": True,
}


def _reachable() -> bool:
    try:
        return httpx.get(BASE + "/health", timeout=3.0).status_code == 200
    except Exception:  # noqa: BLE001 - the skip below is the judge
        return False


@pytest.fixture()
def page():
    if not BASE.startswith(("http://127.0.0.1", "http://localhost")):
        raise SystemExit(f"refusing: {BASE} is not loopback")
    if not _reachable():
        pytest.skip(f"nothing serving {BASE}; run scripts/run_upload_edges.py --serve-only")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(viewport={"width": 390, "height": 844})
        p = context.new_page()
        yield p
        browser.close()


def fake_preview(page, handle: dict = FAKE_HANDLE) -> None:
    """Answers /api/preview entirely inside the browser, before the request ever
    leaves the page. Only test_preview_survives_a_new_pick calls this — every other
    test here never presses "Ver una prueba gratis" at all, so for them no request to
    /api/preview happens in the first place. If either kind of test ever did reach the
    loopback server for real, scripts/run_upload_edges.py's NeverCallTheModel refuses
    the call before it could reach fal."""
    page.route("**/api/preview", lambda route: route.fulfill(status=200, json=handle))


def thumbs_locator(page):
    return page.locator("[data-sf-thumbs] img, [data-sf-thumbs] [role=img]")


def expect_thumb_count(page, n: int) -> None:
    """A plain `.count()` reads the DOM at the instant it is called, before React has
    necessarily re-rendered after the pick — that raced and failed once, red before
    this fix. `expect(...).to_have_count()` polls, the same auto-waiting every other
    Playwright locator assertion in this repository already relies on."""
    from playwright.sync_api import expect

    expect(thumbs_locator(page)).to_have_count(n)


def open_app(page) -> None:
    """`load`, not `domcontentloaded`: the file input's change handler is wired up by
    React after hydration, and hydration cannot start before the page's own script
    tags have finished downloading and running. Found the hard way — the very first
    choose() in the very first test of a run raced `domcontentloaded` and the pick
    silently went nowhere, red before this fix."""
    page.goto(BASE, wait_until="load")


def choose(page, *paths: Path) -> None:
    page.locator("#sf-files").set_input_files([str(p) for p in paths])


def test_second_pick_adds(page):
    open_app(page)
    choose(page, FACE)
    expect_thumb_count(page, 1)
    choose(page, FACE2)  # a second, separate pick — must ADD, not replace
    expect_thumb_count(page, 2)
    assert page.get_by_text("2 de 4 elegidas").is_visible()


def test_duplicate_is_skipped(page):
    open_app(page)
    choose(page, FACE)
    expect_thumb_count(page, 1)
    choose(page, FACE)  # same name, size and last-modified as the first pick
    expect_thumb_count(page, 1)  # an exact duplicate must not be added a second time


def test_remove_button_works(page):
    open_app(page)
    choose(page, FACE)
    choose(page, FACE2)
    expect_thumb_count(page, 2)
    remove_first = page.get_by_label("Quitar foto 1")
    box = remove_first.bounding_box()
    assert box is not None, "the remove button must be on screen"
    assert box["width"] >= 44 and box["height"] >= 44, (
        f"touch target under 44px: {box['width']}x{box['height']}"
    )
    remove_first.click()
    expect_thumb_count(page, 1)


def test_same_file_is_repickable_after_removal(page):
    open_app(page)
    choose(page, FACE)
    expect_thumb_count(page, 1)
    page.get_by_label("Quitar foto 1").click()
    expect_thumb_count(page, 0)
    choose(page, FACE)  # the very same path, chosen again
    expect_thumb_count(page, 1)  # the same file must be choosable again once removed


def test_preview_survives_a_new_pick(page):
    open_app(page)
    choose(page, FACE)
    fake_preview(page)
    page.get_by_role("button", name="Ver una prueba gratis").click()
    page.wait_for_selector("img[alt='Prueba gratuita de tu foto de perfil']")
    buy = page.get_by_role("button", name="Comprar las cuatro fotos por 19,99 €")
    assert buy.is_visible(), "the buy button must be there while a preview is showing"

    choose(page, FACE2)  # picking again, while the preview from the first pick is up

    # The preview from the first pick is still the one on screen — not erased.
    assert page.locator("img[alt='Prueba gratuita de tu foto de perfil']").is_visible()
    assert buy.is_visible(), "picking again must not take the buy button away"
    assert page.get_by_text(
        "Has cambiado las fotos. Puedes generar una prueba nueva o comprar con las fotos actuales."
    ).is_visible()


def test_the_four_photo_cap_still_holds(page):
    """Not one of the five named cases. The likeliest place an add-instead-of-replace
    change breaks is the boundary it did not touch: four already kept, one more
    picked — it must be dropped, not swapped in for one already kept."""
    open_app(page)
    tmp = Path(tempfile.mkdtemp())
    try:
        extra_a, extra_b, extra_c = tmp / "a.jpg", tmp / "b.jpg", tmp / "c.jpg"
        for extra in (extra_a, extra_b, extra_c):
            shutil.copy(FACE, extra)
        choose(page, FACE, FACE2)
        choose(page, extra_a, extra_b)  # 2 + 2 = 4, exactly at the cap
        expect_thumb_count(page, 4)
        choose(page, extra_c)  # a 5th distinct file: must be dropped, not substituted
        expect_thumb_count(page, 4)
        assert page.get_by_text("4 de 4 elegidas").is_visible()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- task 28
#
# count-only-real-tries (work/queue/28-count-only-real-tries.md). WHY: a reviewer
# uploaded one empty file (refused server-side), then a good photo, and the shop
# answered "you have used your free tries" — the server used to count BEFORE
# validating. The server side of that fix is tests/test_preview_counting.py. These
# four are the browser's own share of the same task: refuse an empty or oversized
# file before it is ever sent, never leave the submit button clickable before the
# human check has actually delivered a token, and never tell a visitor a check
# "expired" when the server only ever says it did not pass.


def test_empty_file_is_refused_with_its_own_message(page):
    open_app(page)
    tmp = Path(tempfile.mkdtemp())
    try:
        empty = tmp / "empty.jpg"
        empty.write_bytes(b"")
        choose(page, empty, FACE)  # one empty, one good, in the same pick
        expect_thumb_count(page, 1)  # the good photo is kept; the empty one is not
        assert page.get_by_text("Hemos ignorado 1 archivo vacío.").is_visible()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_oversized_file_is_refused_with_its_own_message(page):
    open_app(page)
    tmp = Path(tempfile.mkdtemp())
    try:
        big = tmp / "big.jpg"
        big.write_bytes(b"\xff\xd8\xff" + b"\x00" * (12 * 1024 * 1024 + 1))
        choose(page, big, FACE)  # one over 12 MB, one good, in the same pick
        expect_thumb_count(page, 1)  # the good photo is kept; the big one is not
        assert page.get_by_text("Hemos ignorado 1 foto que supera los 12 MB.").is_visible()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_server_refusal_drops_only_the_refused_file(page):
    """Task 31 (drop-the-refused-file). THE BUG, measured 21 Sep against the real
    local app: the server names the offending file by its position in the batch —
    `unsupported_type:<index>` from app/guards.py's validate_uploads — and the page
    used to keep that file forever, so every later attempt re-sent it and was
    refused again. The visitor was stuck with no way to get a preview at all.

    A text file saved under a .jpg name passes the BROWSER's own image/* filter
    (browsers infer File.type from the extension, not the bytes) but fails the
    SERVER's real magic-byte sniff() in app/guards.py, so this reaches the loopback
    server for real and is refused for real — the one test in this file that does
    not need `fake_preview`, because the refusal happens in `validate_uploads`
    before `preview_fn` (NeverCallTheModel) is ever called."""
    open_app(page)
    tmp = Path(tempfile.mkdtemp())
    try:
        bad = tmp / "not-really-a-photo.jpg"
        bad.write_bytes(b"this is a text file wearing a .jpg name\n" * 10)
        choose(page, bad, FACE)
        expect_thumb_count(page, 2)
        page.get_by_role("button", name="Ver una prueba gratis").click()
        error = page.locator("p[role='alert']")
        error.wait_for()
        text = error.inner_text()
        assert "not-really-a-photo.jpg" in text, text  # names which file was dropped
        expect_thumb_count(page, 1)  # the refused file is gone
        assert page.get_by_text("1 de 4 elegidas").is_visible()  # the good one remains
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_submit_stays_disabled_and_says_so_until_the_human_check_has_a_ticket(page):
    """Blocking Cloudflare's own script is what makes this deterministic: without it,
    the real Turnstile widget can resolve before the assertion below ever runs, and
    the test would be proving nothing. With the script blocked, `window.turnstile`
    never becomes an object, so the page stays in its very first "waiting" state for
    the ten seconds this test runs nowhere near."""
    page.route("**/challenges.cloudflare.com/**", lambda route: route.abort())
    open_app(page)
    choose(page, FACE)
    button = page.get_by_role("button", name="Comprobando que eres una persona")
    assert button.is_visible(), "the button must say what it is waiting for"
    assert button.is_disabled(), "a click here would send an empty token"


def test_turnstile_failure_says_it_did_not_pass_not_that_it_expired(page):
    """The server only ever sends `turnstile` when `verify_turnstile` returned
    false — a check that did NOT pass, not one that ran out of time."""
    open_app(page)
    choose(page, FACE)
    page.route(
        "**/api/preview",
        lambda route: route.fulfill(status=403, json={"detail": "turnstile"}),
    )
    page.get_by_role("button", name="Ver una prueba gratis").click()
    # Not get_by_role("alert"): Next's own route announcer div also carries
    # role="alert" and matches too, which is a strict-mode violation here.
    error = page.locator("p[role='alert']")
    error.wait_for()
    text = error.inner_text()
    assert "no ha pasado" in text, text
    assert "caduc" not in text, f"still says it expired: {text}"


# ---------------------------------------------------------------- task 29
#
# never-block-a-buyer (work/done/29-never-block-a-buyer.md). WHY: 21 September,
# Kevin's own shop hit the free-preview limit and from that moment showed no buy
# button at all, for an hour, because the buy button only exists while the page
# holds a signed handle and only a successful preview used to create one. The
# image model is faked exactly the way every other test in this file fakes it — by
# never letting the request leave the browser at all (fake_preview, below) — so this
# proves the PAGE's behaviour, not the server's; the server's own proof that no
# image-model call happens at the limit is tests/test_buy_at_limit.py.


def test_the_buy_button_is_visible_and_enabled_at_the_free_preview_limit(page):
    open_app(page)
    choose(page, FACE)
    fake_preview(page, LIMITED_HANDLE)
    page.get_by_role("button", name="Ver una prueba gratis").click()
    assert page.get_by_text(
        "Has usado tus pruebas gratis de esta hora. Puedes comprar tus cuatro "
        "fotos ahora o volver dentro de una hora."
    ).is_visible()
    # Not a promise the terms do not already make: no preview image, no claim one is
    # coming.
    assert page.locator("img[alt='Prueba gratuita de tu foto de perfil']").count() == 0
    assert page.get_by_label("Ropa en las fotos").is_visible(), (
        "the clothing selector must be part of the normal buy surface"
    )
    buy = page.get_by_role("button", name="Comprar las cuatro fotos por 19,99 €")
    assert buy.is_visible(), "the buy button must be there even at the limit"
    assert buy.is_enabled(), "a stored handle is a real handle — nothing disables it"


# ---------------------------------------------------------------- task 30
#
# preview-survives (work/queue/30-preview-survives.md). WHY: the handle above lived
# only in this page's own React state. PRINT FIRST, measured 21 Sep by reading
# app/entry.py's `_checkout_factory`: Stripe's cancel_url is
# `f"{s.public_url}/?cancelado=1"` — the plain home page, one inert query parameter
# `grep -rn cancelado frontend/src` finds nowhere read — so a visitor who reloads, or
# who opens Stripe and presses back or cancel, lands on a page that remounts from
# nothing and loses the preview and the buy button, costing them another of their
# three tries an hour. The fix keeps batch/n/t/wardrobe in sessionStorage and asks
# GET /api/preview/{batch} for a fresh signed address on mount — /api/preview itself
# (the POST that generates one) must never be asked again.


def fake_resign(page, preview_url: str = "/__fake__/resigned.jpg") -> dict:
    """Answers GET /api/preview/{batch} entirely inside the browser — the SAME
    technique fake_preview uses for the POST route — so a reload never reaches the
    loopback server's own resign_preview double, scripts/run_upload_edges.py's
    NeverResignEither, which raises loudly if a test ever forgets this. Returns a
    dict with a live `count`, so a test can prove the route was asked the number of
    times it expects rather than assuming it from a passing assertion elsewhere."""
    calls = {"count": 0}

    def handler(route):
        calls["count"] += 1
        route.fulfill(status=200, json={"preview_url": preview_url})

    page.route("**/api/preview/*", handler)
    return calls


def test_the_preview_and_buy_button_survive_a_reload(page):
    open_app(page)
    choose(page, FACE)
    generation_calls = {"count": 0}

    def handle_generation(route):
        generation_calls["count"] += 1
        route.fulfill(status=200, json=FAKE_HANDLE)

    page.route("**/api/preview", handle_generation)
    resign_calls = fake_resign(page)

    page.get_by_role("button", name="Ver una prueba gratis").click()
    page.wait_for_selector("img[alt='Prueba gratuita de tu foto de perfil']")
    assert generation_calls["count"] == 1

    page.reload(wait_until="load")

    page.wait_for_selector("img[alt='Prueba gratuita de tu foto de perfil']")
    buy = page.get_by_role("button", name="Comprar las cuatro fotos por 19,99 €")
    assert buy.is_visible(), "the buy button must survive a reload"
    assert generation_calls["count"] == 1, "a reload must never mint a new preview"
    assert resign_calls["count"] == 1, "the reload should ask once for a fresh signed address"


# ---------------------------------------------------------------- task 34
#
# buy-with-changed-photos (work/queue/34-buy-with-changed-photos.md). WHY: task 31's
# drop-the-refused-file fix (test_server_refusal_drops_only_the_refused_file, above)
# was only ever proven for the free-preview path. The buy button calls the SAME
# /api/preview endpoint from a different place — storeCurrentPhotosForBuy, used when
# the kept photos have changed since the last preview — and that call was never
# exercised for a server refusal. These two cases are the first exercise of that path.


def fake_preview_but_let_store_only_through(page, handle: dict = FAKE_HANDLE) -> None:
    """Same technique as fake_preview, except a request carrying `store_only` (the
    field storeCurrentPhotosForBuy adds to the SAME /api/preview endpoint,
    app/main.py's _register_preview) is let through to the real loopback server
    instead of being answered here. That is how these tests get a REAL refusal out of
    validate_uploads for the buy path — the same real refusal
    test_server_refusal_drops_only_the_refused_file gets for the preview path — while
    the ordinary preview that opens each test still never reaches the server or fal.
    post_data_buffer (bytes), not post_data (str): the body carries real JPEG bytes,
    which are not valid UTF-8 and would make a text read of the body unreliable."""

    def handler(route):
        body = route.request.post_data_buffer or b""
        if b"store_only" in body:
            route.continue_()
        else:
            route.fulfill(status=200, json=handle)

    page.route("**/api/preview", handler)


def test_buy_with_a_refused_file_drops_it_and_names_it(page):
    """The visitor already has a preview and a buy button, then adds a file the
    server will refuse, and presses buy. Before this task's fix: storeCurrentPhotosForBuy's
    own catch block never looked at which file the server named, so it showed a
    generic sentence and left the refused file in the kept set forever — the same bug
    task 31 fixed for the free-preview path, never fixed here. A text file saved
    under a .jpg name is used for the same reason test_server_refusal_drops_only_the_
    refused_file uses one: it passes the browser's own image/* filter but fails the
    server's real magic-byte sniff(), so this is a genuine refusal, not a staged one."""
    open_app(page)
    choose(page, FACE)
    fake_preview_but_let_store_only_through(page)
    page.get_by_role("button", name="Ver una prueba gratis").click()
    page.wait_for_selector("img[alt='Prueba gratuita de tu foto de perfil']")

    tmp = Path(tempfile.mkdtemp())
    try:
        bad = tmp / "not-really-a-photo.jpg"
        bad.write_bytes(b"this is a text file wearing a .jpg name\n" * 10)
        choose(page, bad)  # added after the preview, alongside the kept FACE
        expect_thumb_count(page, 2)

        page.get_by_role("button", name="Comprar las cuatro fotos por 19,99 €").click()

        error = page.locator("p[role='alert']")
        error.wait_for()
        text = error.inner_text()
        assert "not-really-a-photo.jpg" in text, text  # names which file was dropped

        expect_thumb_count(page, 1)  # the refused file is gone, the good one stays
        assert page.get_by_text("1 de 4 elegidas").is_visible()
        buy = page.get_by_role("button", name="Comprar las cuatro fotos por 19,99 €")
        assert buy.is_visible() and buy.is_enabled(), (
            "the visitor must never be stuck: the buy button must still work "
            "with the photos that remain"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_buy_button_will_not_sell_an_empty_set(page):
    """A preview exists (and so does the stored handle behind the buy button), then
    every photo is removed. The buy button must not offer to sell zero photos — it
    must never send a batch with nothing in it."""
    open_app(page)
    choose(page, FACE)
    fake_preview(page)
    page.get_by_role("button", name="Ver una prueba gratis").click()
    page.wait_for_selector("img[alt='Prueba gratuita de tu foto de perfil']")

    page.get_by_label("Quitar foto 1").click()
    expect_thumb_count(page, 0)

    buy = page.get_by_role("button", name="Comprar las cuatro fotos por 19,99 €")
    assert buy.is_visible(), "the button stays on screen, it just must not be usable"
    assert buy.is_disabled(), "the buy button must not offer to sell an empty set"


def test_the_preview_and_buy_button_survive_returning_from_the_payment_page(page):
    """Simulates Stripe's own cancel_url — the home page plus `?cancelado=1`, an
    inert query parameter — by navigating there directly: the same full page
    navigation a real cancel produces, without a real Checkout Session."""
    open_app(page)
    choose(page, FACE)
    generation_calls = {"count": 0}

    def handle_generation(route):
        generation_calls["count"] += 1
        route.fulfill(status=200, json=FAKE_HANDLE)

    page.route("**/api/preview", handle_generation)
    resign_calls = fake_resign(page)

    page.get_by_role("button", name="Ver una prueba gratis").click()
    page.wait_for_selector("img[alt='Prueba gratuita de tu foto de perfil']")
    assert generation_calls["count"] == 1

    page.goto(BASE + "/?cancelado=1", wait_until="load")

    page.wait_for_selector("img[alt='Prueba gratuita de tu foto de perfil']")
    buy = page.get_by_role("button", name="Comprar las cuatro fotos por 19,99 €")
    assert buy.is_visible(), "the buy button must survive a return from Stripe's cancel redirect"
    assert generation_calls["count"] == 1, "returning from Stripe must never mint a new preview"
    assert resign_calls["count"] == 1
