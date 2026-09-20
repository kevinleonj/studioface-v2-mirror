"""Record what the page tells Google, so a redesign cannot quietly change it.

Section 7. M7 is the reason this exists: a prerender once injected a script tag that
tripped an idempotency guard and skipped `gtag("config")` for real users, and nothing
noticed. The consent bootstrap and the gtag loader are not to be touched by any unit in
this brief; this is what proves they were not.

    .venv\\Scripts\\python.exe scripts\\analytics_probe.py https://studioface.app ^
        docs/ui/2026-09-19/analytics-before.json

Four things are recorded:

  a. the first two dataLayer entries, which must be the consent default with all four
     signals denied and wait_for_update, BEFORE any config
  b. whether a /g/collect request carrying gcs=G100 leaves the page while consent is
     denied - G100 is the signal that says "ad_storage denied", and its absence would
     mean either that nothing is being measured or that it is being measured without
     consent, which are different disasters
  c. that clicking "Aceptar" pushes a consent update with all four signals granted
  d. the ordered event names pushed during a scripted visit

Run it against the deployed hostname. GA4_ID is injected at build time and is empty in a
local build, so locally gtag.js never loads and (b) cannot happen; the probe says so in
the output rather than reporting a pass it did not observe.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SIGNALS = ("ad_storage", "ad_user_data", "ad_personalization", "analytics_storage")
COLLECT = "/g/collect"

# Entries are `arguments` objects pushed by the gtag shim, so they serialise as
# {"0": "consent", "1": "default", ...}. Read them as arrays, in order, unchanged.
READ_DATALAYER = """
() => (window.dataLayer || []).map((e) => {
  try { return JSON.parse(JSON.stringify(Array.from(e.length !== undefined ? e : [e]))); }
  catch (err) { return ['<unserialisable>']; }
})
"""


def consent_defaults(layer: list) -> dict:
    """(a) The first two entries, and whether they are the default, denied, before config."""
    first_two = layer[:2]
    default = next((e for e in layer if e[:2] == ["consent", "default"]), None)
    config_at = next((i for i, e in enumerate(layer) if e and e[0] == "config"), None)
    default_at = next((i for i, e in enumerate(layer) if e[:2] == ["consent", "default"]), None)
    settings = default[2] if default and len(default) > 2 else {}
    return {
        "firstTwoEntries": first_two,
        "allFourDenied": all(settings.get(s) == "denied" for s in SIGNALS),
        "waitForUpdate": settings.get("wait_for_update"),
        "defaultBeforeConfig": default_at is not None
        and (config_at is None or default_at < config_at),
        "configIndex": config_at,
    }


def consent_update(layer: list) -> dict:
    """(c) The update pushed by "Aceptar"."""
    update = next((e for e in layer if e[:2] == ["consent", "update"]), None)
    settings = update[2] if update and len(update) > 2 else {}
    return {
        "pushed": update is not None,
        "allFourGranted": all(settings.get(s) == "granted" for s in SIGNALS),
        "settings": settings,
    }


def event_names(layer: list) -> list[str]:
    """(d) The ordered event names, which is the list that must not lose a member."""
    return [str(e[1]) for e in layer if len(e) > 1 and e[0] == "event"]


def scripted_visit(page, fixture: Path) -> dict:
    """Load, move the slider, click the first-screen button, choose one file.

    Each step reports whether it actually happened, because in the before-run two of them
    cannot. The slider arrives with unit U3. The first-screen button is disabled until a
    file is chosen, which is F1 itself - the only product button on the page renders in
    its disabled style - so "click it" is not a step a visitor can take yet either. A
    skipped step is recorded, never silently passed over: the after-run has to be able to
    show these turning from skipped to done.
    """
    steps = {}
    slider = page.locator("input[type=range]")
    steps["slider"] = "moved" if slider.count() else "absent"
    if slider.count():
        slider.first.click()
        page.keyboard.press("ArrowRight")
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(200)
    # Unit U5's first-screen call to action is an ANCHOR, not a button, so `main button`
    # finds the uploader's submit instead - which is disabled until a file is chosen, and
    # the probe reported "disabled" against a page that had a working button on it.
    fold = page.locator("[data-cta=fold]")
    button = fold.first if fold.count() else page.locator("main button").first
    if not button.count():
        steps["firstScreenButton"] = "absent"
    elif button.is_disabled():
        steps["firstScreenButton"] = f"disabled: {button.inner_text()[:40]!r}"
    else:
        button.click()
        page.wait_for_timeout(600)
        steps["firstScreenButton"] = f"clicked: {button.inner_text()[:40]!r}"
    if page.locator("input[type=file]").count():
        page.set_input_files("input[type=file]", str(fixture))
        page.wait_for_timeout(400)
        steps["chooseFile"] = "done"
    else:
        steps["chooseFile"] = "absent"
    return steps


def probe(base: str, fixture: Path) -> dict:
    collect: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_context(viewport={"width": 390, "height": 844}).new_page()
        page.on(
            "request",
            lambda r: collect.append(r.url) if COLLECT in r.url else None,
        )
        # Not networkidle: in production Turnstile and gtag keep connections open and it
        # never settles, which times out after 30s against a page that loaded in one.
        page.goto(base.rstrip("/") + "/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        at_load = page.evaluate(READ_DATALAYER)
        steps = scripted_visit(page, fixture)
        denied_phase = page.evaluate(READ_DATALAYER)
        accept = page.get_by_role("button", name="Aceptar")
        accepted: list = []
        if accept.count():
            accept.first.click()
            page.wait_for_timeout(1200)
            accepted = page.evaluate(READ_DATALAYER)
        browser.close()
    gcs_denied = [u for u in collect if "gcs=G100" in u]
    return {
        "base": base,
        "a_consentDefaults": consent_defaults(at_load),
        "b_collect": {
            "gtagLoaded": any(e and e[0] in ("js", "config") for e in at_load),
            "collectRequests": len(collect),
            "withGcsG100": len(gcs_denied),
            "note": (
                "no collect request observed; GA4_ID is empty in a local build, so this "
                "check is only meaningful against the deployed hostname"
                if not collect
                else "observed"
            ),
        },
        "c_consentUpdate": consent_update(accepted),
        "d_events": {
            "steps": steps,
            "deniedPhase": event_names(denied_phase),
            "afterAccept": event_names(accepted),
        },
    }


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    base, target = sys.argv[1], Path(sys.argv[2])
    fixture = target.parent / "_probe-selfie.jpg"
    fixture.parent.mkdir(parents=True, exist_ok=True)
    from PIL import Image

    Image.new("RGB", (64, 64), (200, 150, 120)).save(fixture, "JPEG")
    result = probe(base, fixture)
    target.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"\nwritten to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
