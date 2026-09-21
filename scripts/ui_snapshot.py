"""Capture the built site at three viewports and record where things actually are.

B0.2. This builds nothing. Point it at a base URL that is already serving the real
FastAPI app over the real static export (M6: scripts/demo_server.py, never `next dev`)
and it writes PNG files plus one geometry.json.

    .venv\\Scripts\\python.exe scripts\\ui_snapshot.py http://127.0.0.1:8099 ^
        docs/ui/2026-09-19/before

The geometry file is the acceptance evidence for units U1-U10; the PNG files are what
scripts/ui_diff.py compares so the locked pages of section 2 cannot move by a pixel.
Every number is a CSS pixel at device scale factor 1, because an earlier review reported
the header as 270px and the banner as 280px - device pixels at scale 2, both wrong.

Nothing here is a judgement about the design. It is a ruler.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

VIEWPORTS = {"360x640": (360, 640), "390x844": (390, 844), "1440x900": (1440, 900)}

# Every route the export serves. `/g/` is visited without a token, which is the state a
# stranger following a stale link sees, and one of the pages locked by section 2.
#
# Task 23 adds the two Google Ads landing pages. They share the fold-clearing shape U5
# proved for home (H1, slider, first-screen CTA, uploader, banner) through the same
# selectors in TARGETS below, so tests/test_fold_geometry.py can hold them to the same
# geometry without a second set of selectors.
PAGES = {
    "home": "/",
    "foto-cv": "/foto-cv/",
    "foto-linkedin": "/foto-linkedin/",
    "recuperar": "/recuperar/",
    "gallery": "/g/",
    "legal-aviso": "/legal/aviso-legal/",
    "legal-privacidad": "/legal/privacidad/",
    "legal-terminos": "/legal/terminos/",
    "legal-cookies": "/legal/cookies/",
}

# One place to adjust when a unit renames something, rather than nine call sites.
# `sticky` has no match today; unit U8 introduces it, and "if present" is the point.
TARGETS = {
    "header": "header",
    "h1": "h1",
    "hero": "h1",  # resolved to the closest section in MEASURE, see below
    # Measured, not assumed: there is no <form> element on the page and the button is
    # type="button". The consent banner renders outside <main>, so "the first button in
    # main" is the primary call to action without depending on its Spanish label, which
    # units U5 and U8 are free to change.
    "cta": "main button",
    "uploader": "label:has(input[type=file])",
    "banner": "[role=dialog][aria-label=Cookies]",
    "sticky": "[data-sticky-bar]",
    # Unit U1 moves "Recuperar mis fotos" out of the mobile header and gives it a second
    # home directly under the uploader. Measured by its own hook so a test can assert
    # where it landed, not merely that a link to /recuperar/ exists somewhere on the page.
    "recoverUnderUploader": "[data-recover-under-uploader]",
    "headerNav": "header nav",
    # Unit U2 removes the empty vertical gap F2 measured between the H1 and the
    # sub-headline in the desktop left column. Measuring it needs both ends named.
    "subhead": "[data-subhead]",
    # U3's frame and U5's first-screen call to action. The existing "cta" target is the
    # first button in <main>, which is the uploader's submit; U5 adds an anchor above it,
    # so it needs a name of its own or the two are indistinguishable.
    "sliderFrame": ".sf-ba",
    "foldCta": "[data-cta=fold]",
    "foldMicro": "[data-cta-micro]",
}

# /api/preview is rate limited per IP, and the counter lives in the server process. Submit
# once per run, or every state after the first photographs the rate-limit message instead
# of its own answer - which is exactly what the first run of this script did.
SUBMIT_STATE = "invalid"

MEASURE = """
(targets) => {
  const rect = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return {
      x: +r.x.toFixed(2), y: +r.y.toFixed(2),
      w: +r.width.toFixed(2), h: +r.height.toFixed(2),
      top: +(r.y + scrollY).toFixed(2), bottom: +(r.bottom + scrollY).toFixed(2),
      position: s.position, display: s.display, visible: r.width > 0 && r.height > 0,
    };
  };
  const out = {};
  for (const [name, sel] of Object.entries(targets)) {
    let el = null;
    try { el = document.querySelector(sel); } catch (e) { el = null; }
    if (name === 'hero' && el) el = el.closest('section') || el.parentElement;
    out[name] = rect(el);
  }
  // Anything pinned that is not the banner: a sticky bar this script was not told about
  // still gets recorded, so U8 cannot introduce one that covers content unnoticed.
  out.pinned = [...document.querySelectorAll('body *')]
    .filter((el) => ['fixed', 'sticky'].includes(getComputedStyle(el).position))
    .filter((el) => el.getBoundingClientRect().height > 0)
    .slice(0, 8)
    .map((el) => ({ tag: el.tagName.toLowerCase(), cls: el.className.toString().slice(0, 60),
                    ...rect(el) }));
  // Type, not just boxes: U2 sets the H1 to 30px at 390 wide so it holds two lines, and
  // "how many lines" is only answerable from the rendered height over the line box.
  out.h1Type = (() => {
    const el = document.querySelector('h1');
    if (!el) return null;
    const s = getComputedStyle(el);
    const lh = parseFloat(s.lineHeight) || parseFloat(s.fontSize) * 1.2;
    return {
      fontSize: +parseFloat(s.fontSize).toFixed(2),
      lineHeight: +lh.toFixed(2),
      lines: Math.round(el.getBoundingClientRect().height / lh),
      text: el.textContent.trim(),
    };
  })();
  // Unit U4: the two consent buttons must be one row, equal width, 44px tall and the
  // SAME visual weight. "Same weight" is a fact about paint, so the paint is recorded.
  out.bannerButtons = [...document.querySelectorAll(
    '[role=dialog][aria-label=Cookies] button')].map((el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return {
      text: el.textContent.trim(),
      x: +r.x.toFixed(2), y: +r.y.toFixed(2),
      w: +r.width.toFixed(2), h: +r.height.toFixed(2),
      background: s.backgroundColor, color: s.color,
      borderWidth: s.borderTopWidth, borderColor: s.borderTopColor,
    };
  });
  out.viewport = { w: innerWidth, h: innerHeight, dpr: devicePixelRatio };
  out.document = { h: document.documentElement.scrollHeight,
                   scrollWidth: document.documentElement.scrollWidth };
  out.horizontalScroll = document.documentElement.scrollWidth > innerWidth;
  return out;
}
"""


def fixtures(tmp: Path) -> dict[str, list[Path]]:
    """The uploader states reachable with no Turnstile token, as files on disk.

    `not-an-image.jpg` is a text file with a .jpg name: the client-side type check must
    reject it, and a check that only reads the extension will not.
    """
    from PIL import Image

    tmp.mkdir(parents=True, exist_ok=True)
    good = []
    for i in range(5):
        path = tmp / f"selfie-{i}.jpg"
        Image.new("RGB", (64, 64), (200 - i * 20, 150, 120)).save(path, "JPEG")
        good.append(path)
    fake = tmp / "not-an-image.jpg"
    fake.write_text("this is text, not a JPEG\n", encoding="utf-8")
    return {"chosen": good[:2], "invalid": [fake], "too-many": good[:5]}


def settle(page) -> None:
    """Fonts and images decided before anything is measured or photographed."""
    page.wait_for_load_state("networkidle")
    page.evaluate("document.fonts ? document.fonts.ready : null")
    page.wait_for_timeout(250)


def capture(page, out_dir: Path, name: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    settle(page)
    page.screenshot(path=str(out_dir / f"{name}.png"), full_page=False)
    page.screenshot(path=str(out_dir / f"{name}--full.png"), full_page=True)
    return page.evaluate(MEASURE, TARGETS)


def reject_cookies(page) -> bool:
    button = page.get_by_role("button", name="Rechazar")
    if button.count() == 0:
        return False
    button.first.click()
    page.wait_for_timeout(200)
    return True


def read_uploader(page) -> dict:
    """What the uploader is telling the visitor right now, in words."""
    return {
        "alerts": [t.strip() for t in page.locator("[role=alert]").all_inner_texts() if t.strip()],
        "status": [t.strip() for t in page.locator("[role=status]").all_inner_texts() if t.strip()],
        "label": page.locator("label:has(input[type=file])").inner_text().replace("\n", " | "),
        "ctaDisabled": page.locator("main button").first.is_disabled(),
    }


def uploader_states(page, out_dir: Path, prefix: str, files: dict) -> dict:
    """The uploader states, choosing files and then submitting.

    Measured 19 Sep: this build has NO client-side validation. `onChange` stores whatever
    was chosen, `accept=` is only a file-picker hint, and every message the visitor sees
    comes back from /api/preview. So the "client-side validation error" state B0.2 asks
    for does not exist to capture; the submitted state is captured instead, which is where
    the message actually appears. Locally Turnstile is stubbed by demo_server, so the
    round trip completes - noted because in production this needs a real challenge.
    """
    results = {}
    for state, paths in files.items():
        page.reload()
        settle(page)
        reject_cookies(page)
        page.set_input_files("input[type=file]", [str(p) for p in paths])
        page.wait_for_timeout(400)
        chosen = capture(page, out_dir, f"{prefix}--upload-{state}")
        chosen.update(read_uploader(page))
        results[f"upload-{state}"] = chosen
        button = page.locator("main button").first
        if state != SUBMIT_STATE or button.is_disabled():
            continue
        button.click()
        page.wait_for_timeout(2500)
        sent = capture(page, out_dir, f"{prefix}--upload-{state}-sent")
        sent.update(read_uploader(page))
        results[f"upload-{state}-sent"] = sent
    return results


def snapshot_page(context, base: str, path: str, out_dir: Path, tag: str, files) -> dict:
    page = context.new_page()
    page.goto(base.rstrip("/") + path, wait_until="domcontentloaded")
    result = {"first-visit": capture(page, out_dir, f"{tag}--first-visit")}
    result["first-visit"]["bannerPresent"] = result["first-visit"]["banner"] is not None
    if reject_cookies(page):
        result["rejected"] = capture(page, out_dir, f"{tag}--rejected")
    if files is not None:
        result.update(uploader_states(page, out_dir, tag, files))
    page.close()
    return result


def run(base: str, out_dir: Path, browsers: list[str]) -> dict:
    files = fixtures(out_dir / "_fixtures")
    geometry: dict = {"base": base, "browsers": browsers, "pages": {}}
    with sync_playwright() as pw:
        for browser_name in browsers:
            browser = getattr(pw, browser_name).launch()
            for vp_name, (w, h) in VIEWPORTS.items():
                for page_name, path in PAGES.items():
                    tag = f"{browser_name}--{vp_name}--{page_name}"
                    print(f"  {tag}", flush=True)
                    key = f"{browser_name}/{vp_name}/{page_name}"
                    # One context per page, not per viewport. Sharing it carried the
                    # consent choice from the home page into every page after it, so six
                    # of seven pages were photographed with the banner already answered
                    # and the file called them "first-visit". A first visit is a first
                    # visit: no cookies, no localStorage, nothing.
                    context = browser.new_context(
                        viewport={"width": w, "height": h}, device_scale_factor=1
                    )
                    geometry["pages"][key] = snapshot_page(
                        context, base, path, out_dir, tag, files if page_name == "home" else None
                    )
                    context.close()
            browser.close()
    return geometry


def available(browsers: list[str]) -> list[str]:
    """WebKit is captured only if its binary is actually installed (R4f)."""
    ok = []
    with sync_playwright() as pw:
        for name in browsers:
            try:
                getattr(pw, name).launch().close()
                ok.append(name)
            except Exception as exc:  # noqa: BLE001 - absence is the answer, not an error
                print(f"SKIP {name}: not installed here ({str(exc).splitlines()[0][:80]})")
    return ok


def contact_sheets(out_dir: Path, geometry: dict) -> list[Path]:
    """One reviewable image per browser and viewport, so git holds sheets not hundreds.

    B0.3: the raw PNG files stay in a gitignored directory; these are what get committed
    and what a person actually looks at.
    """
    from PIL import Image, ImageDraw

    groups: dict[str, list[Path]] = {}
    for png in sorted(out_dir.glob("*.png")):
        if png.name.startswith(("sheet--", "DIFF--")) or png.stem.endswith("--full"):
            continue
        browser, viewport, _ = png.stem.split("--", 2)
        groups.setdefault(f"{browser}--{viewport}", []).append(png)
    written = []
    for name, pngs in groups.items():
        thumbs = []
        for png in pngs:
            img = Image.open(png).convert("RGB")
            img.thumbnail((260, 520))
            thumbs.append((png.stem.split("--", 2)[2], img))
        cols = min(6, len(thumbs))
        rows = (len(thumbs) + cols - 1) // cols
        cell_w = max(t.width for _, t in thumbs) + 12
        cell_h = max(t.height for _, t in thumbs) + 30
        sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), (242, 241, 237))
        draw = ImageDraw.Draw(sheet)
        for i, (label, img) in enumerate(thumbs):
            x, y = (i % cols) * cell_w + 6, (i // cols) * cell_h + 24
            sheet.paste(img, (x, y))
            draw.text((x, y - 14), label[:42], fill=(20, 19, 18))
        target = out_dir / f"sheet--{name}.png"
        sheet.save(target)
        written.append(target)
    geometry["sheets"] = [p.name for p in written]
    return written


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    base, out_dir = sys.argv[1], Path(sys.argv[2])
    wanted = sys.argv[3].split(",") if len(sys.argv) > 3 else ["chromium", "webkit"]
    browsers = available(wanted)
    if not browsers:
        print("no browser available")
        return 1
    geometry = run(base, out_dir, browsers)
    for sheet in contact_sheets(out_dir, geometry):
        print(f"  sheet {sheet}")
    target = out_dir / "geometry.json"
    target.write_text(json.dumps(geometry, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\n{target}  ({len(geometry['pages'])} page/viewport combinations)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
