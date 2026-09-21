"""The outside-in proof for the defect fixed in 86513fe: `scripts/check.py
upload_thumbnails` stayed green while every visitor saw four empty squares, because it
only grepped the deployed bundle for the `data-sf-thumbs` marker. A marker in the bundle
is not a picture on the screen.

`check_upload_thumbnails` (scripts/verify_production.py) is the check that looks at the
screen instead: pick the fixture photo, wait for the thumbnail the browser actually
painted, read `naturalWidth` off the real `<img>` element, and read back whether the
page's own Content-Security-Policy fired a `securitypolicyviolation` event while doing
it. This file proves that check both ways: it must FAIL against a build whose policy is
missing `blob:` from img-src (the state production shipped before 86513fe) and PASS
against a build whose policy carries it (the state production ships now) - a check that
has never been seen to fail is decoration, not a check.

Both builds are the real `frontend/out` export, served from a real socket (never the
export directory itself - docs/DESIGN.md verification protocol #1), with a
Content-Security-Policy header built from the real `app.main.CSP` dict so the "before"
fixture is the actual header production served, not an invented one.
"""

from __future__ import annotations

import http.server
import shutil
import socketserver
import sys
import threading
from functools import partial
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import CSP  # noqa: E402
from scripts.verify_production import BLOCKED, FAIL, OK, check_upload_thumbnails  # noqa: E402

OUT = ROOT / "frontend" / "out"
FIXTURE_FACE = ROOT / "tests" / "fixtures" / "faces" / "face.jpg"

playwright = pytest.importorskip("playwright.sync_api", reason="playwright not installed here")


@pytest.fixture(scope="module", autouse=True)
def browser_available():
    """Skip on a laptop with no browser binary; fail loudly on CI. Same pattern as
    test_verify_production.py and test_upload_thumbnails.py - a silent skip here would
    turn the only test that can see this defect into a no-op on the one machine that
    matters."""
    import os

    try:
        with playwright.sync_playwright() as pw:
            pw.chromium.launch().close()
    except Exception as exc:  # noqa: BLE001 - any launch failure means no browser
        message = f"chromium will not launch: {exc}"
        if os.environ.get("CI") == "true":
            pytest.fail(f"{message} | run: python -m playwright install --with-deps chromium")
        pytest.skip(message)


def _csp_header(*, drop_blob_from_img_src: bool) -> str:
    """Build the real header app.main.csp() would send, optionally with `blob:` removed
    from img-src only - reproducing the exact policy production served before 86513fe,
    not a policy invented for this test."""
    directives = {name: list(values) for name, values in CSP.items()}
    if drop_blob_from_img_src:
        directives["img-src"] = [v for v in directives["img-src"] if v != "blob:"]
    return "; ".join(f"{name} {' '.join(values)}" for name, values in directives.items())


def _served(tmp_path_factory, *, drop_blob_from_img_src: bool):
    """A copy of the real frontend/out export, served with a real Content-Security-Policy
    header, on a real socket."""
    if not OUT.is_dir():
        pytest.skip("no build; run `npm run build` in frontend/ first")
    copy_dir = tmp_path_factory.mktemp("sf-thumb-csp")
    shutil.copytree(OUT, copy_dir, dirs_exist_ok=True)
    header = _csp_header(drop_blob_from_img_src=drop_blob_from_img_src)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def end_headers(self):  # noqa: D102 - stdlib override, no docstring expected
            self.send_header("Content-Security-Policy", header)
            super().end_headers()

    handler = partial(Handler, directory=str(copy_dir))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    return base, httpd


def test_it_goes_red_against_a_policy_missing_blob(tmp_path_factory):
    """The refused case. This is production's exact pre-86513fe policy: every host
    86513fe changed still there, only `blob:` itself missing from img-src - the state
    that shipped four empty squares to every visitor."""
    base, httpd = _served(tmp_path_factory, drop_blob_from_img_src=True)
    try:
        status, evidence = check_upload_thumbnails(base, fixture=FIXTURE_FACE)
    finally:
        httpd.shutdown()
    assert status == FAIL, f"the check passed a policy that refuses blob: images: {evidence}"
    assert "naturalwidth" in evidence.lower() or "violat" in evidence.lower(), (
        f"the FAIL evidence does not say why: {evidence}"
    )


def test_it_goes_green_against_the_real_policy(tmp_path_factory):
    """The case that must get through. Same export, the real app.main.CSP header,
    unmodified - the policy production serves today."""
    base, httpd = _served(tmp_path_factory, drop_blob_from_img_src=False)
    try:
        status, evidence = check_upload_thumbnails(base, fixture=FIXTURE_FACE)
    finally:
        httpd.shutdown()
    assert status == OK, f"the check refused a policy that allows blob: images: {evidence}"
    assert "naturalwidth" in evidence.lower()


def test_it_refuses_to_run_without_a_fixture_photo(tmp_path_factory):
    """The failure case: a missing fixture must be reported, not silently skipped or
    crash the whole verification run."""
    base, httpd = _served(tmp_path_factory, drop_blob_from_img_src=False)
    try:
        status, evidence = check_upload_thumbnails(base, fixture=ROOT / "no-such-file.jpg")
    finally:
        httpd.shutdown()
    assert status == FAIL
    assert "no-such-file.jpg" in evidence


def test_it_reports_blocked_when_playwright_is_unavailable(monkeypatch):
    """One check nobody asked for: if playwright cannot be imported this must say so
    (BLOCKED), never crash the rest of scripts/verify_production.py the way an
    unguarded ImportError would."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "playwright.sync_api":
            raise ImportError("no playwright here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    status, evidence = check_upload_thumbnails("https://example.invalid", fixture=FIXTURE_FACE)
    assert status == BLOCKED
    assert "playwright" in evidence.lower()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
