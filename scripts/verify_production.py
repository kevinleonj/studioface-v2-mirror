"""Outside-in verification. A real browser, on the real internet, against a public URL.

Three production outages in two days, one shared property: **every test in this repo ran
either inside the process (pytest against the app object) or inside the build (Playwright
against a static export on localhost).** Nothing had ever made a request from outside.

    1  success_url carried no token      every paying customer hit "enlace no válido"
    2  the Turnstile widget never mounted  /api/preview answered 403 to everybody
    3  every fetch was cross-origin        preflight 405, "No hemos podido conectar."

All three were invisible to 407 passing tests, five green CI jobs and a 49/50 design
score, because all of those look at the parts. This looks at the whole thing from where
the customer stands.

It takes a URL and nothing else. No import from `app`, no fixture from the repo's
internals, no knowledge of how the service is built — if it can be answered from outside,
this is where it is answered, and if it cannot, this says so rather than faking it.

Exit codes: 0 all clear, 1 a link is broken, 2 the check itself could not run.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("verify_production")

TIMEOUT_S = 30.0
BROWSER_WAIT_MS = 12_000
OK, FAIL, BLOCKED = "ok", "FAIL", "BLOCKED"


@dataclass
class Check:
    link: str
    status: str
    evidence: str
    seconds: float = 0.0

    def line(self) -> str:
        return f"  {self.status:<8} {self.link:<34} {self.evidence} ({self.seconds:.2f}s)"


@dataclass
class Result:
    checks: list[Check] = field(default_factory=list)

    def add(self, check: Check) -> Check:
        print(check.line(), flush=True)
        self.checks.append(check)
        return check

    @property
    def broken(self) -> list[Check]:
        return [c for c in self.checks if c.status == FAIL]


def timed(fn, *args):
    start = time.monotonic()
    try:
        status, evidence = fn(*args)
    except Exception as exc:  # noqa: BLE001 - the report is the product; a crash is a FAIL
        status, evidence = FAIL, f"{type(exc).__name__}: {exc}"
    return status, evidence, time.monotonic() - start


# ---------------------------------------------------------------- HTTP links


def check_health(base: str) -> tuple[str, str]:
    r = httpx.get(f"{base}/health", timeout=TIMEOUT_S)
    if r.status_code != 200:
        return FAIL, f"{r.status_code} {r.text[:80]}"
    body = r.json()
    if not body.get("ok"):
        return FAIL, json.dumps(body)
    if body.get("killswitch"):
        return FAIL, "kill switch is ON: /api/checkout and /api/preview answer 503"
    return OK, json.dumps(body)


def check_landing_served(base: str) -> tuple[str, str]:
    r = httpx.get(base + "/", timeout=TIMEOUT_S, follow_redirects=True)
    if r.status_code != 200:
        return FAIL, f"{r.status_code}"
    if "foto de perfil profesional" not in r.text:
        return FAIL, "the H1 copy is not in the document"
    return OK, f"200, {len(r.content) / 1024:.0f} KB of HTML"


def check_gallery_rejects_a_bad_token(base: str) -> tuple[str, str]:
    """A made-up order and token must not resolve. This is the link that decides whether
    somebody can read another customer's photographs by guessing."""
    r = httpx.get(f"{base}/api/orders/cs_test_nope/deadbeef", timeout=TIMEOUT_S)
    if r.status_code != 404:
        return FAIL, f"expected 404 for an invalid token, got {r.status_code} {r.text[:60]}"
    return OK, "404 for an invented order and token"


def check_budget_endpoint_refuses_anonymous(base: str) -> tuple[str, str]:
    """U1. The kill switch closes /api/checkout and /api/preview with 503, and this is
    the endpoint that sets it. Measured 19 Sep: an unauthenticated POST with a
    well-formed body returned 200 {"killswitch":false} — the handler ran. The external
    review saw 500, which was only an empty body failing request.json() one line earlier.

    A body is deliberately sent: `{}` is what proved the handler is reachable, and a
    check that posts nothing would pass on the parse error instead of on the auth."""
    r = httpx.post(
        f"{base}/internal/budget",
        json={},
        timeout=TIMEOUT_S,
    )
    if r.status_code in (401, 403):
        return OK, f"{r.status_code}, anonymous caller refused before any body parsing"
    if r.status_code >= 500:
        return FAIL, f"{r.status_code} — a 5xx means the handler was reached and then broke"
    return FAIL, f"{r.status_code} {r.text[:90]} — an anonymous caller reached the kill switch"


def check_gracias_refuses_an_unpaid_session(base: str) -> tuple[str, str]:
    """U2. Measured 19 Sep: this route minted a valid gallery token for any string
    starting `cs_`, deterministically, without asking Stripe anything:

        GET /api/gracias?session_id=cs_test_fake
        302 -> /g/?o=cs_test_fake&t=REDACTED

    `delivery_token` is the same token that gates /api/orders, so the route was a
    token-minting oracle for the whole order namespace: supply an id, receive its token.

    A redirect is the failure here, not the success. follow_redirects stays off so the
    Location header itself is the evidence."""
    r = httpx.get(
        f"{base}/api/gracias",
        params={"session_id": "cs_test_fake"},
        timeout=TIMEOUT_S,
        follow_redirects=False,
    )
    location = r.headers.get("location", "")
    if r.status_code == 404 and not location:
        return OK, "404 and no Location for a session Stripe does not confirm"
    if "&t=" in location:
        return FAIL, f"{r.status_code} handed out a gallery token: {location[-48:]}"
    return FAIL, f"expected 404, got {r.status_code} location={location[:60]!r}"


# What Google's own CSP guide lists for GA4 (with Ads features) and for an Ads conversion
# tag, https://developers.google.com/tag-platform/security/guides/csp, read 19 Sep 2026.
# Deliberately spelled out here rather than imported from app.main: this file's whole job
# is to check the deployed service from outside, and a check that imports the thing it is
# checking only proves the code agrees with itself.
_ADS = (
    "https://www.googletagmanager.com",
    "https://www.googleadservices.com",
    "https://*.g.doubleclick.net",
    "https://pagead2.googlesyndication.com",
    "https://*.google.com",
    "https://*.google.es",
)
GOOGLE_CSP = {
    "script-src": (
        "https://www.googletagmanager.com",
        "https://www.googleadservices.com",
        "https://www.google.com",
    ),
    "img-src": ("https://*.google-analytics.com", *_ADS),
    "connect-src": ("https://*.google-analytics.com", "https://ad.doubleclick.net", *_ADS),
    "frame-src": ("https://www.googletagmanager.com", "https://challenges.cloudflare.com"),
}
# Directives whose job is to refuse. The ads test must not have been bought with these.
CSP_LOCKED = {
    "default-src": ["'self'"],
    "object-src": ["'none'"],
    "frame-ancestors": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
}


def check_csp_carries_the_google_hosts(base: str) -> tuple[str, str]:
    """M1. An Ads conversion tag added today would be blocked silently, and GA4's image
    pings already are: measured 19 Sep, img-src had no googletagmanager and no
    doubleclick host, and frame-src had only Cloudflare."""
    header = httpx.get(base + "/", timeout=TIMEOUT_S).headers.get("content-security-policy", "")
    if not header:
        return FAIL, "no Content-Security-Policy header at all"
    served = {}
    for part in header.split(";"):
        name, *values = part.strip().split()
        served[name] = values
    missing = [
        f"{directive} {host}"
        for directive, hosts in GOOGLE_CSP.items()
        for host in hosts
        if host not in served.get(directive, [])
    ]
    if missing:
        return FAIL, f"{len(missing)} host(s) Google requires are absent: {missing[:4]}"
    widened = [d for d, want in CSP_LOCKED.items() if served.get(d) != want]
    if widened:
        return FAIL, f"a directive that should refuse was widened: {widened}"
    if "<TLD>" in header or "script-src-elem" in served:
        return FAIL, "the <TLD> placeholder or a shadowing script-src-elem is being served"
    return OK, f"every host Google lists for GA4 and an Ads tag is present ({len(header)} chars)"


# Where this application's own images come from. I1: the free preview was served from
# fal's content delivery network instead, which img-src has never allowed, so the browser
# refused it. The policy was audited against Google's list and never against the
# addresses this server hands the browser (P3).
SIGNED_IMAGE_HOST = "https://storage.googleapis.com"


def check_img_src_allows_our_own_images(base: str) -> tuple[str, str]:
    """I1, from outside. The host the signer uses must be in the policy the page sends,
    and no fal host may have been added to the policy to take the short way out."""
    header = httpx.get(base + "/", timeout=TIMEOUT_S).headers.get("content-security-policy", "")
    served = {}
    for part in header.split(";"):
        name, *values = part.strip().split()
        served[name] = values
    img = served.get("img-src", [])
    if SIGNED_IMAGE_HOST not in img:
        return FAIL, f"img-src does not allow {SIGNED_IMAGE_HOST}: {' '.join(img)}"
    if any("fal.media" in source or "fal.ai" in source for source in img):
        return FAIL, "fal was added to img-src; C1 says store the preview instead"
    return OK, f"img-src allows {SIGNED_IMAGE_HOST} and no fal host"


def check_the_bundle_can_reset_turnstile(base: str) -> tuple[str, str]:
    """F1/O1. A Turnstile token is single-use. The shipped bundle contained exactly one
    Turnstile call - `render` - so every retry after a failed preview replayed a spent
    token and got 403 until the page was reloaded.

    This reads the DEPLOYED JavaScript, because the source is not what ships and a grep
    of the source would have said everything was fine.
    """
    html = httpx.get(base + "/", timeout=TIMEOUT_S).text
    chunks = set(re.findall(r'src="(/_next/static/chunks/[^"]+\.js)"', html))
    if not chunks:
        return FAIL, "no /_next/static/chunks script tags on the landing page"
    calls: set[str] = set()
    sentences = 0
    for path in sorted(chunks):
        body = httpx.get(base + path, timeout=TIMEOUT_S).text
        calls |= set(re.findall(r"turnstile\.(\w+)", body))
        sentences += body.count("filtro de contenido")
    if "render" not in calls:
        return FAIL, f"no turnstile calls in the deployed bundle: {sorted(calls)}"
    if "reset" not in calls:
        return FAIL, f"the deployed bundle still cannot reset: {sorted(calls)}"
    if not sentences:
        return FAIL, "the content-policy sentence (F2) is not in the deployed bundle"
    return OK, f"turnstile.{{{','.join(sorted(calls))}}}, and the F2 sentences shipped"


DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


def check_the_schema_is_not_published(base: str) -> tuple[str, str]:
    """F8/O9. /docs, /redoc and /openapi.json listed every route, parameter and response
    shape of the money path, including /internal/generate and /internal/budget."""
    published = []
    for path in DOC_PATHS:
        code = httpx.get(base + path, timeout=TIMEOUT_S).status_code
        if code != 404:
            published.append(f"{path}={code}")
    if published:
        return FAIL, f"still published: {', '.join(published)}"
    return OK, f"{', '.join(DOC_PATHS)} all 404"


def check_the_gallery_can_offer_a_download(base: str) -> tuple[str, str]:
    """F3/O3. "Descargar" navigated away instead of downloading, because a `download`
    attribute is ignored cross-origin and the signed address carried no
    Content-Disposition. The gallery bundle must now read a separate `downloads` list.

    Read from the deployed JavaScript rather than by calling /api/orders, because every
    real order belongs to a customer and P7 says a verification request must never touch
    one.
    """
    html = httpx.get(base + "/g/", timeout=TIMEOUT_S).text
    chunks = set(re.findall(r'src="(/_next/static/chunks/[^"]+\.js)"', html))
    if not chunks:
        return FAIL, "no script tags on /g/"
    for path in sorted(chunks):
        if "downloads" in httpx.get(base + path, timeout=TIMEOUT_S).text:
            return OK, "the gallery reads a separate downloads list"
    return FAIL, "the deployed gallery has no downloads list; Descargar still navigates"


def check_preflight_is_not_needed(base: str) -> tuple[str, str]:
    """Outage 3, asked directly. The browser check below proves no request WAS
    cross-origin; this proves what would happen if one were, so the report says which."""
    r = httpx.request(
        "OPTIONS",
        f"{base}/api/preview",
        headers={
            "Origin": base,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
        timeout=TIMEOUT_S,
    )
    allow = r.headers.get("access-control-allow-origin")
    detail = f"OPTIONS -> {r.status_code}, allow-origin={allow!r}"
    if allow is None:
        return OK, f"{detail} (no CORS, as intended: every call is same-origin)"
    return OK, f"{detail} (CORS is configured; the allowlist is now load-bearing)"


# ---------------------------------------------------------------- browser links


def browser_checks(base: str, result: Result) -> None:
    """The half that needs a real browser, because the last two outages were only
    visible to one: a widget that never mounted and a request that never completed."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        result.add(Check("browser", BLOCKED, "playwright is not installed here"))
        return

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        requests: list[str] = []
        page.on("request", lambda r: requests.append(r.url))
        start = time.monotonic()
        page.goto(base + "/", wait_until="load", timeout=int(TIMEOUT_S * 1000))
        page.wait_for_timeout(BROWSER_WAIT_MS)
        elapsed = time.monotonic() - start

        result.add(Check(*_turnstile(page), seconds=elapsed))
        result.add(Check(*_same_origin(base, requests)))
        result.add(Check(*_first_screen(page)))
        result.add(Check(*_comparador(page)))
        result.add(Check(*_consent_banner(page)))
        result.add(Check(*_fold_cta(page)))
        browser.close()


# U1's numbers, from the 19 September brief. The header is the one the geometry tests
# measure locally; this is the same assertion made against the deployed hostname, because
# M1 says nothing is done until an outside-in check shows it.
MAX_MOBILE_HEADER = 56
H1_TEXT = "Tu foto profesional para LinkedIn, en dos minutos"
MOBILE_H1_PX = 30


def _first_screen(page) -> tuple[str, str, str]:
    """U1. At 390x844 the header is one row and "Recuperar mis fotos" has a home under
    the uploader. Both were true locally; only this says they are true in production."""
    header = page.evaluate(
        "() => { const h = document.querySelector('header');"
        " return h ? h.getBoundingClientRect().height : null; }"
    )
    if header is None:
        return "first screen", FAIL, "no <header> element on the deployed page"
    if header > MAX_MOBILE_HEADER:
        return (
            "first screen",
            FAIL,
            f"header is {header:.0f}px at 390 wide, over {MAX_MOBILE_HEADER}",
        )
    nav = page.evaluate(
        "() => { const n = document.querySelector('header nav');"
        " return n ? n.getBoundingClientRect().height > 0 : false; }"
    )
    if nav:
        return "first screen", FAIL, "the mobile header still renders its nav links"
    recover = page.locator("[data-recover-under-uploader]")
    if recover.count() == 0:
        return "first screen", FAIL, "no 'Recuperar mis fotos' link under the uploader"
    h1 = page.evaluate(
        "() => { const e = document.querySelector('h1'); if (!e) return null;"
        " return { text: e.textContent.trim(),"
        " size: parseFloat(getComputedStyle(e).fontSize),"
        " lines: Math.round(e.getBoundingClientRect().height"
        "   / parseFloat(getComputedStyle(e).lineHeight)) }; }"
    )
    if not h1 or h1["text"] != H1_TEXT:
        return "first screen", FAIL, f"H1 is {h1 and h1['text']!r}"
    if h1["size"] != MOBILE_H1_PX:
        return "first screen", FAIL, f"H1 is {h1['size']}px at 390 wide, not {MOBILE_H1_PX}"
    if h1["lines"] != 2:
        return "first screen", FAIL, f"H1 wraps to {h1['lines']} lines at 390 wide"
    return (
        "first screen",
        OK,
        f"header {header:.0f}px, no nav links, recover link present, "
        f"H1 {h1['size']:.0f}px over {h1['lines']} lines",
    )


def _comparador(page) -> tuple[str, str, str]:
    """U3. The slider is a real range input, it moves, and the two faces are the same
    size - the last of which is the only reason a comparison slider is worth having."""
    control = page.locator('.sf-ba input[type="range"]')
    if control.count() == 0:
        return "comparison slider", FAIL, "no range input in the hero frame"
    if control.first.get_attribute("aria-label") != "Comparar antes y despues".replace(
        "despues", "después"
    ):
        return "comparison slider", FAIL, "the control has no usable aria-label"
    handle = page.evaluate(
        "() => { const h = document.querySelector('.sf-ba-handle');"
        " if (!h) return null; const r = h.getBoundingClientRect();"
        " return { w: r.width, h: r.height }; }"
    )
    if not handle or handle["w"] < 44 or handle["h"] < 44:
        return "comparison slider", FAIL, f"handle is {handle}, under 44px"
    images = page.locator(".sf-ba img")
    if images.count() != 2:
        return "comparison slider", FAIL, f"{images.count()} images in the frame, expected 2"
    # Drag it with the keyboard, which is the path a mouse test would never exercise.
    control.first.focus()
    before = page.evaluate(
        "() => getComputedStyle(document.querySelector('.sf-ba')).getPropertyValue('--p')"
    )
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    after = page.evaluate(
        "() => getComputedStyle(document.querySelector('.sf-ba')).getPropertyValue('--p')"
    )
    if before.strip() == after.strip():
        return "comparison slider", FAIL, f"ArrowRight did not move it ({before!r})"
    return (
        "comparison slider",
        OK,
        f"range input, 44px handle, 2 images, {before.strip()} -> {after.strip()}",
    )


MAX_BANNER_PHONE = 112
CTA_TEXT = "Ver mi prueba gratis"


def _fold_cta(page) -> tuple[str, str, str]:
    """U5, at 390x844. There is a working product button on the first screen, it clears
    the consent banner, and it goes to the uploader rather than submitting anything.

    The conditions are a list rather than a chain of ifs: ruff caps complexity at 8, and
    a list also means the first failure names itself instead of being one branch of nine.
    """
    m = page.evaluate(
        "() => { const a = document.querySelector('[data-cta=fold]');"
        " const b = document.querySelector('[role=dialog][aria-label=Cookies]');"
        " if (!a || !b) return null; const r = a.getBoundingClientRect();"
        " return { text: a.textContent.trim(), top: r.top, bottom: r.bottom,"
        "          h: r.height, w: r.width, href: a.getAttribute('href'),"
        "          disabled: a.hasAttribute('disabled')"
        "                    || a.getAttribute('aria-disabled') === 'true',"
        "          bannerTop: b.getBoundingClientRect().top,"
        "          micro: !!document.querySelector('[data-cta-micro]') }; }"
    )
    if not m:
        return "first-screen cta", FAIL, "no [data-cta=fold] button on the deployed page"
    problems = [
        (m["text"] != CTA_TEXT, f"the button says {m['text']!r}"),
        (m["disabled"], "the first-screen button renders disabled"),
        (m["href"] != "#subir", f"href={m['href']!r}"),
        (page.locator("#subir").count() == 0, "nothing on the page has id=subir"),
        (abs(m["h"] - 52) > 1, f"the button is {m['h']:.0f}px tall"),
        (m["bottom"] > m["bannerTop"], f"the banner covers it, from {m['bannerTop']:.0f}"),
        (m["top"] > 560, f"the button top is {m['top']:.0f}, over 560"),
        (not m["micro"], "no reassurance line under the button"),
    ]
    for broken, why in problems:
        if broken:
            return "first-screen cta", FAIL, why
    return (
        "first-screen cta",
        OK,
        f"top {m['top']:.0f}, {m['w']:.0f}x{m['h']:.0f}, "
        f"clears the banner by {m['bannerTop'] - m['bottom']:.0f}px",
    )


def _consent_banner(page) -> tuple[str, str, str]:
    """U4, at 390x844. Height, equal buttons, and the same visual weight on both answers."""
    measured = page.evaluate(
        "() => { const b = document.querySelector('[role=dialog][aria-label=Cookies]');"
        " if (!b) return null;"
        " const btns = [...b.querySelectorAll('button')].map((el) => {"
        "   const r = el.getBoundingClientRect(); const s = getComputedStyle(el);"
        "   return { w: r.width, h: r.height, bg: s.backgroundColor,"
        "            border: s.borderTopWidth + ' ' + s.borderTopColor }; });"
        " return { h: b.getBoundingClientRect().height, btns }; }"
    )
    if not measured:
        return "consent banner", FAIL, "no consent banner on a first visit"
    if measured["h"] > MAX_BANNER_PHONE:
        return "consent banner", FAIL, f"banner is {measured['h']:.0f}px, over {MAX_BANNER_PHONE}"
    btns = measured["btns"]
    if len(btns) != 2:
        return "consent banner", FAIL, f"{len(btns)} buttons in the banner"
    if abs(btns[0]["w"] - btns[1]["w"]) > 1:
        return "consent banner", FAIL, f"unequal widths {btns[0]['w']:.0f}/{btns[1]['w']:.0f}"
    if any(b["h"] < 44 for b in btns):
        return "consent banner", FAIL, f"a button is under 44px: {[b['h'] for b in btns]}"
    if btns[0]["bg"] != btns[1]["bg"] or btns[0]["border"] != btns[1]["border"]:
        return "consent banner", FAIL, "the two answers carry different visual weight"
    return (
        "consent banner",
        OK,
        f"{measured['h']:.0f}px, two {btns[0]['w']:.0f}x{btns[0]['h']:.0f} answers, same weight",
    )


def _turnstile(page) -> tuple[str, str, str]:
    """Outage 2, asked directly. The container existed and stayed empty for ten seconds,
    so 'the div is in the HTML' is not the question — 'did the widget mount' is."""
    state = page.evaluate(
        "() => { const d = document.querySelector('div[class=\"min-h-[65px]\"]');"
        " const i = document.querySelector('input[name=\"cf-turnstile-response\"]');"
        " return { present: !!d, children: d ? d.children.length : -1, token: !!i }; }"
    )
    if not state["present"]:
        return "turnstile widget", BLOCKED, "no widget container: the site key is unset here"
    if state["children"] == 0 or not state["token"]:
        return (
            "turnstile widget",
            FAIL,
            f"container has {state['children']} children, token field present="
            f"{state['token']} — the challenge never mounted, so /api/preview will 403",
        )
    return "turnstile widget", OK, f"mounted, {state['children']} child, token field present"


def _same_origin(base: str, requests: list[str]) -> tuple[str, str, str]:
    """Outage 3, asked directly — and asked about the thing that actually broke.

    The first version compared every request host against ours minus an exact-match
    allowlist, and failed on `brunhild.challenges.cloudflare.com` and
    `region1.google-analytics.com`. Both are legitimate: Turnstile and GA4 shard across
    subdomains. A check that fires on a healthy page teaches people to ignore it.

    What broke was OUR API being called off-origin. So that is the assertion: every
    `/api/` request must be same-origin, and everything else must belong to a declared
    third-party script provider, matched by domain suffix rather than exact host.
    """
    host = urlparse(base).netloc
    third_party = (
        ".challenges.cloudflare.com",
        "challenges.cloudflare.com",
        ".google-analytics.com",
        "www.googletagmanager.com",
        ".gstatic.com",
        "fonts.googleapis.com",
    )
    api_offsite, unknown = set(), set()
    for url in requests:
        parts = urlparse(url)
        if not parts.netloc or parts.netloc == host:
            continue
        if parts.path.startswith("/api/"):
            api_offsite.add(parts.netloc)
        elif not any(parts.netloc.endswith(suffix) for suffix in third_party):
            unknown.add(parts.netloc)
    if api_offsite:
        return "same-origin api calls", FAIL, f"/api called off-origin: {sorted(api_offsite)}"
    if unknown:
        return "same-origin api calls", FAIL, f"undeclared third-party origin: {sorted(unknown)}"
    return (
        "same-origin api calls",
        OK,
        f"{len(requests)} requests, every /api one same-origin",
    )


# ------------------------------------------------------------- the thumbnails link

FIXTURE_FACE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "faces" / "face.jpg"

# Runs in the page before any navigation, so it is listening from the very first byte.
CSP_VIOLATION_SPY = """
window.__sfCspViolations = [];
document.addEventListener('securitypolicyviolation', (e) => {
  window.__sfCspViolations.push(e.violatedDirective + ' ' + e.blockedURI);
});
"""


def check_upload_thumbnails(base: str, fixture: Path = FIXTURE_FACE) -> tuple[str, str]:
    """86513fe, from outside, with a real file and a real screen — not a grep of the
    bundle. `scripts/check.py upload_thumbnails` stayed green through the whole defect
    because it only searched the downloaded code for the `data-sf-thumbs` marker; a
    marker in the bundle is not a picture on the screen. The browser refused every
    `blob:` thumbnail because `img-src` never named that scheme, and no check ever
    looked at what the visitor actually saw.

    This chooses the fixture photo, waits for the thumbnail the browser paints, and
    reads `naturalWidth` off the real `<img>` element — a blocked image reports 0,
    loaded or not. It also reads back whether the page's own Content-Security-Policy
    fired a `securitypolicyviolation` event while doing it, so a future scheme this
    check does not know to name by number is still caught by name.

    Stops here: it never touches the submit button, so unlike check_preview below it
    costs nothing and sends nothing — choosing a file and waiting for a thumbnail
    happens entirely in the browser and never reaches the server.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return BLOCKED, "playwright is not installed here"

    if not fixture.is_file():
        return FAIL, f"no fixture photo at {fixture}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        try:
            page.add_init_script(CSP_VIOLATION_SPY)
            page.goto(base + "/", wait_until="load", timeout=int(TIMEOUT_S * 1000))
            file_input = page.locator("#sf-files")
            if file_input.count() == 0:
                return FAIL, "no #sf-files file input on the deployed page"
            file_input.set_input_files(str(fixture))
            page.wait_for_selector("[data-sf-thumbs] img", timeout=int(TIMEOUT_S * 1000))
            page.wait_for_function(
                "() => { const i = document.querySelector('[data-sf-thumbs] img');"
                " return !!i && i.complete; }",
                timeout=int(TIMEOUT_S * 1000),
            )
            natural_width = page.evaluate(
                "() => { const i = document.querySelector('[data-sf-thumbs] img');"
                " return i ? i.naturalWidth : 0; }"
            )
            violations = page.evaluate("() => window.__sfCspViolations || []")
        finally:
            browser.close()

    if violations:
        return FAIL, f"{len(violations)} securitypolicyviolation event(s): {violations[:4]}"
    if not natural_width:
        return FAIL, f"thumbnail naturalWidth is {natural_width}; the browser drew nothing"
    return (
        OK,
        f"thumbnail naturalWidth={natural_width}, 0 securitypolicyviolation events",
    )


# ---------------------------------------------------------------- the preview link


def check_preview(base: str, token: str | None) -> tuple[str, str]:
    """The one link that cannot be automated against production, and is not faked.

    /api/preview needs a Turnstile token, and Turnstile exists to withhold one from
    automation — against the production site key it presents an interactive challenge.
    Solving it is off the table, so this reports BLOCKED and names the human step.

    Against a deployment built with Cloudflare's PUBLIC always-pass test key, pass
    --turnstile-token and the link is exercised for real. That key can never reach
    production: tests/test_turnstile_widget.py fails if any test site key appears in
    frontend/out.
    """
    if not token:
        return (
            BLOCKED,
            "needs a Turnstile token; production presents an interactive challenge "
            "by design. Human step: issue #4.",
        )
    files = {"files": ("selfie.jpg", b"\xff\xd8\xff\xdb" + b"\x00" * 64, "image/jpeg")}
    r = httpx.post(
        f"{base}/api/preview",
        files=files,
        data={"turnstile_token": token},
        timeout=TIMEOUT_S * 3,
    )
    if r.status_code != 200:
        return FAIL, f"{r.status_code} {r.text[:120]}"
    body = r.json()
    if not body.get("preview_url"):
        return FAIL, f"200 but no preview_url: {json.dumps(body)[:120]}"
    return OK, f"200, preview_url {body['preview_url'][:48]}..."


HTTP_CHECKS = (
    ("health", check_health),
    ("landing page served", check_landing_served),
    ("gallery rejects a bad token", check_gallery_rejects_a_bad_token),
    ("budget refuses anonymous", check_budget_endpoint_refuses_anonymous),
    ("gracias refuses unpaid", check_gracias_refuses_an_unpaid_session),
    ("csp carries google hosts", check_csp_carries_the_google_hosts),
    ("img-src allows our images", check_img_src_allows_our_own_images),
    ("turnstile can be reset", check_the_bundle_can_reset_turnstile),
    ("schema is not published", check_the_schema_is_not_published),
    ("gallery offers a download", check_the_gallery_can_offer_a_download),
    ("cors preflight", check_preflight_is_not_needed),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="the public base URL, e.g. https://studioface.app")
    parser.add_argument("--turnstile-token", default=None, help="only for a non-production build")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    # This runs on a GitHub runner and on a Windows console. The evidence lines carry
    # em dashes and a report that dies mid-way through encoding is a report that says
    # the site is broken when it is not — which is exactly how design_audit.py failed
    # twice. Same fix, applied before it can happen a third time.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    print(f"VERIFY PRODUCTION: {base}\n", flush=True)
    result = Result()
    for link, fn in HTTP_CHECKS:
        status, evidence, secs = timed(fn, base)
        if result.add(Check(link, status, evidence, secs)).status == FAIL:
            break
    else:
        if not args.no_browser:
            browser_checks(base, result)
            status, evidence, secs = timed(check_upload_thumbnails, base, FIXTURE_FACE)
            result.add(Check("upload thumbnails render", status, evidence, secs))
        status, evidence, secs = timed(check_preview, base, args.turnstile_token)
        result.add(Check("free preview", status, evidence, secs))

    broken = result.broken
    blocked = [c for c in result.checks if c.status == BLOCKED]
    print()
    if broken:
        print(f"VERIFY PRODUCTION: BROKEN at {broken[0].link} — {broken[0].evidence}")
        sys.exit(1)
    note = f", {len(blocked)} link(s) blocked by an anti-automation control" if blocked else ""
    print(f"VERIFY PRODUCTION: all {len(result.checks)} links answered{note}")
    sys.exit(0)


if __name__ == "__main__":
    main()
