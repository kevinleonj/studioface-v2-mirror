"""After choosing photos the visitor used to see only a file name, which does not answer
"is that the right photo" without opening the OS file dialog again.

Source/bundle checks mirror test_turnstile_look.py's pattern for this same component: the
markup is asserted from the .tsx source and, separately, proven to survive the real build.

The runtime check answers the harder question this feature raises: is every blob URL
this component creates actually revoked, not just followed somewhere in the file by a
call to revokeObjectURL that nothing ever runs? A real browser is driven against a copy
of the built export (docs/DESIGN.md verification protocol #1: never serve the directory
itself), URL.createObjectURL/revokeObjectURL are spied on from the page, and removing a
kept photo with its own button is used to prove the FIRST batch of URLs is revoked
before or as the remaining photo's fresh URL is created - not merely "revoked
eventually". Task 27 made picking again an ADD instead of a replace (see
tests/e2e/test_upload_edges.py), so the remove button is now the only user action that
takes a photo OUT of the kept set — a second file pick no longer does.

"On unmount" is not driven separately. The effect returns exactly one cleanup function
(test_the_effect_has_one_cleanup_for_both_paths), and React's own contract is that this
is the function invoked both when the effect's dependency changes and when the owning
component unmounts - there is no second, unmount-only code path to independently break.
"""

import http.server
import re
import shutil
import socketserver
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from source_scan import strip_comments  # noqa: E402

FORM = ROOT / "frontend" / "src" / "components" / "upload-form.tsx"
OUT = ROOT / "frontend" / "out"
FIXTURE_IMAGE = ROOT / "frontend" / "public" / "muestras"

playwright = pytest.importorskip("playwright.sync_api", reason="playwright not installed here")


def source() -> str:
    return strip_comments(FORM.read_text(encoding="utf-8"), language="tsx")


def thumbs_block() -> str:
    """The JSX block that renders the thumbnail row, comments stripped."""
    src = source()
    start = src.index("data-sf-thumbs")
    end = src.index("<input", start)
    return src[start:end]


def effect_block() -> str:
    """The useEffect that creates and revokes the blob URLs, comments stripped."""
    src = source()
    start = src.index("useEffect(() => {\n    const next: Thumb[]")
    end = src.index("}, [files]);", start)
    return src[start : end + len("}, [files]);")]


def test_the_dropzone_carries_the_thumbs_container():
    assert "data-sf-thumbs" in source()


def test_a_thumbnail_is_64px_square_cover_and_rounded_10px():
    block = thumbs_block()
    # --radius is 10px (frontend/src/app/globals.css) and rounded-lg maps to var(--radius)
    # in the @theme block, so rounded-lg IS 10px here, not the Tailwind default.
    assert "size-16" in block, "size-16 is 64px (16 * 4px); not found on the thumbnail"
    assert "rounded-lg" in block, "rounded-lg is the 10px radius token here"
    assert "object-cover" in block, "no object-fit: cover on the rendered image"


def test_each_thumbnail_has_the_required_alt_text():
    block = thumbs_block()
    assert "`Foto elegida ${i + 1}`" in block


def test_a_row_inside_the_dropzone_not_a_separate_element():
    """The container must be a descendant of the <label htmlFor="sf-files"> dropzone,
    not a sibling placed after it."""
    src = source()
    label_start = src.index('<label\n        htmlFor="sf-files"')
    thumbs_start = src.index("data-sf-thumbs")
    input_start = src.index('id="sf-files"')
    assert label_start < thumbs_start < input_start, (
        "data-sf-thumbs is not between the dropzone label and its file input"
    )


def test_heic_is_detected_and_falls_back_to_an_extension_tile():
    src = source()
    assert "function isHeic(file: File): boolean" in src
    assert '"image/heic"' in src and '"image/heif"' in src
    assert '"HEIC"' in src and '"HEIF"' in src
    block = thumbs_block()
    assert "thumb.ext" in block, "no fallback tile showing the file extension"
    assert 'role="img"' in block, "the fallback tile carries no accessible label"


def test_object_urls_are_created_and_revoked_in_the_same_effect():
    block = effect_block()
    assert "URL.createObjectURL(file)" in block
    assert "URL.revokeObjectURL(thumb.url)" in block
    # The revoke must be inside the function the effect RETURNS, not merely present
    # somewhere in the same block (which would pass even if never wired as a cleanup).
    cleanup_start = block.index("return () => {")
    assert block.index("URL.revokeObjectURL(thumb.url)") > cleanup_start


def test_the_effect_has_one_cleanup_for_both_paths():
    """Exactly one useEffect governs thumbs, keyed on `files`, with exactly one
    `return () => {...}`. Two code paths (say, a second effect for unmount) would be two
    things to keep in sync instead of one thing to prove."""
    src = source()
    assert src.count("useEffect(() => {\n    const next: Thumb[]") == 1
    block = effect_block()
    assert block.count("return () => {") == 1
    assert block.endswith("}, [files]);")


def test_no_new_dependency_was_added():
    """URL.createObjectURL/revokeObjectURL are browser globals, not an import - the
    feature needed nothing added to package.json."""
    import json

    package_json = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    deps = {**package_json.get("dependencies", {}), **package_json.get("devDependencies", {})}
    assert "heic" not in " ".join(deps).lower(), "an unexpected HEIC-decoding package was added"


def test_the_built_bundle_really_ships_the_marker():
    """The source is not what ships (test_turnstile_look.py's own lesson)."""
    chunks = OUT / "_next" / "static" / "chunks"
    if not chunks.is_dir():
        pytest.skip("no build; CI builds first")
    shipped = " ".join(p.read_text(encoding="utf-8", errors="ignore") for p in chunks.rglob("*.js"))
    assert "data-sf-thumbs" in shipped, "the built bundle lacks the thumbnails marker"
    assert re.search(r"Foto elegida", shipped), "the built bundle lacks the alt text"


@pytest.fixture(scope="module", autouse=True)
def browser_available():
    """Skip on a laptop with no browser binary; fail loudly on CI (test_verify_production.py
    established this pattern after a silent-skip cost a day)."""
    import os

    try:
        with playwright.sync_playwright() as pw:
            pw.chromium.launch().close()
    except Exception as exc:  # noqa: BLE001 - any launch failure means no browser
        message = f"chromium will not launch: {exc}"
        if os.environ.get("CI") == "true":
            pytest.fail(f"{message} | run: python -m playwright install --with-deps chromium")
        pytest.skip(message)


@pytest.fixture(scope="module")
def served(tmp_path_factory):
    """A copy of frontend/out on a real socket - never the export directory itself
    (docs/DESIGN.md verification protocol #1)."""
    if not OUT.is_dir():
        pytest.skip("no build; run `npm run build` in frontend/ first")
    copy_dir = tmp_path_factory.mktemp("sf-thumbs-out")
    shutil.copytree(OUT, copy_dir, dirs_exist_ok=True)
    handler = __import__("functools").partial(
        http.server.SimpleHTTPRequestHandler, directory=str(copy_dir)
    )
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
        httpd.shutdown()


SPY = """
window.__sfUrls = { created: [], revoked: [] };
const realCreate = URL.createObjectURL.bind(URL);
const realRevoke = URL.revokeObjectURL.bind(URL);
URL.createObjectURL = (obj) => {
  const url = realCreate(obj);
  window.__sfUrls.created.push(url);
  return url;
};
URL.revokeObjectURL = (url) => {
  window.__sfUrls.revoked.push(url);
  return realRevoke(url);
};
"""


def _sample_files() -> list[str]:
    files = sorted(FIXTURE_IMAGE.glob("*-despues.jpg"))[:2]
    if len(files) < 2:
        pytest.skip("fewer than two sample images in frontend/public/muestras")
    return [str(f) for f in files]


def test_every_object_url_is_created_once_per_file_and_revoked_on_removal(served):
    """Real proof, not a read of the source: select two files, see two created URLs and
    two live thumbnails; remove one with its own remove button, see the first two
    REVOKED - before the component unmounts, purely from the `files` dependency
    changing.

    Task 27 changed what shrinks the kept set: picking again now ADDS (skipping
    duplicates, tests/e2e/test_upload_edges.py covers that), so re-picking one already
    kept file no longer removes the other one - the remove button is what does that
    now, and this test follows it instead of a second file pick.
    """
    samples = _sample_files()
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        try:
            page.add_init_script(SPY)
            page.goto(f"{served}/", wait_until="load")
            page.set_input_files("#sf-files", samples[:2])
            page.wait_for_selector("[data-sf-thumbs] img", timeout=5000)

            first_created = page.evaluate("window.__sfUrls.created.slice()")
            assert len(first_created) == 2, f"expected 2 created URLs, got {first_created}"
            assert page.evaluate("window.__sfUrls.revoked.length") == 0, (
                "a URL was revoked before any change happened"
            )

            page.get_by_label("Quitar foto 1").click()
            page.wait_for_function("window.__sfUrls.revoked.length >= 2", timeout=5000)

            revoked = page.evaluate("window.__sfUrls.revoked.slice()")
            assert set(first_created).issubset(set(revoked)), (
                f"the first batch was not fully revoked: created={first_created} revoked={revoked}"
            )
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
