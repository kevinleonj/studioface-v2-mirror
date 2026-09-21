"""Outside-in checks against production. Read-only: GET requests only, no cost, no email.

Usage: python scripts/check.py <name>     Exit 0 = green, 1 = red, 2 = unknown name.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.error
import urllib.request

BASE = "https://studioface.app"
CHUNK_PATTERN = re.compile(r"/_next/static/chunks/[A-Za-z0-9_.~-]+\.js")


def get(path: str) -> tuple[int, str]:
    request = urllib.request.Request(BASE + path, headers={"User-Agent": "studioface-check"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        return error.code, ""


NEXT_DEFAULT_FAVICON_MD5 = "c30c7d42707a47a3f4591831641e50dc"
TEMPLATE_LEFTOVERS = ("/next.svg", "/vercel.svg", "/globe.svg", "/window.svg", "/file.svg")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def first_hop(path: str) -> tuple[int, str]:
    """Status and Location of the first answer, without following it."""
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(BASE + path, timeout=30) as response:
            return response.status, ""
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get("Location", "")


def bundle() -> str:
    _, html = get("/")
    return "".join(get(path)[1] for path in sorted(set(CHUNK_PATTERN.findall(html))))


def robots() -> list[str]:
    status, body = get("/robots.txt")
    wanted = ["Disallow: /g/", "Disallow: /api/", "Sitemap:"]
    return [f"robots.txt status {status}"] * (status != 200) + [
        f"robots.txt lacks '{line}'" for line in wanted if line not in body
    ]


def sitemap() -> list[str]:
    status, body = get("/sitemap.xml")
    problems = [f"sitemap.xml status {status}"] * (status != 200)
    return problems + ["sitemap.xml lacks the home address"] * (BASE not in body)


def head() -> list[str]:
    _, html = get("/")
    wanted = {
        "canonical link": r'rel="canonical"',
        "share image": r'property="og:image"',
        "product data with the price": r'application/ld\+json[^<]*>[^<]*"price"\s*:\s*"19\.99"',
    }
    return [
        f"home page lacks {name}"
        for name, pattern in wanted.items()
        if not re.search(pattern, html)
    ]


def attribution() -> list[str]:
    code = bundle()
    problems = [
        f"bundle lacks '{word}'"
        for word in ("begin_checkout", "gbraid", "wbraid", "client_id", "session_id")
        if word not in code
    ]
    return problems + ["bundle still fires 'checkout_click'"] * ('"checkout_click"' in code)


def gallery_hidden() -> list[str]:
    _, html = get("/g/")
    return ["gallery page lacks noindex"] * ("noindex" not in html)


def favicon() -> list[str]:
    request = urllib.request.Request(BASE + "/favicon.ico")
    with urllib.request.urlopen(request, timeout=30) as response:
        digest = hashlib.md5(response.read()).hexdigest()  # noqa: S324 - identity, not security
    problems = ["favicon is still the Next.js default triangle"] * (
        digest == NEXT_DEFAULT_FAVICON_MD5
    )
    served = [path for path in TEMPLATE_LEFTOVERS if get(path)[0] == 200]
    return problems + [f"template leftover still served: {path}" for path in served]


def redirect() -> list[str]:
    status, location = first_hop("/legal/privacidad")
    wanted = BASE + "/legal/privacidad/"
    problems = [f"no-slash address answers {status}, wanted 301 or 308"] * (
        status not in (301, 308)
    )
    return problems + [f"it forwards to '{location}', wanted '{wanted}'"] * (location != wanted)


def human_check_look() -> list[str]:
    code = bundle()
    wanted = {
        "light theme": r'theme:\s*"light"',
        "Spanish": r'language:\s*"es"',
        "flexible width": r'size:\s*"flexible"',
    }
    return [
        f"human check lacks {name}"
        for name, pattern in wanted.items()
        if not re.search(pattern, code)
    ]


def upload_thumbnails() -> list[str]:
    return ["upload form shows no thumbnails (marker data-sf-thumbs absent)"] * (
        "data-sf-thumbs" not in bundle()
    )


def waiting_state() -> list[str]:
    _, html = get("/")
    sheets = re.findall(r"/_next/static/[A-Za-z0-9_./~-]+\.css", html)
    styles = "".join(get(path)[1] for path in sorted(set(sheets)))
    return ["no designed waiting state (class sf-wait absent from the stylesheet)"] * (
        ".sf-wait" not in styles
    )


def health() -> dict:
    _, body = get("/health")
    try:
        return json.loads(body)
    except ValueError:
        return {}


def stripe_mode() -> str:
    return str(health().get("stripe_mode", ""))


def stripe_price_live() -> bool:
    """Task 21: what Stripe itself says about the configured price's livemode, not
    just the key's prefix — see stripe_live's own docstring for why that gap matters."""
    return health().get("stripe_price_live") is True


def stripe_mode_reported() -> list[str]:
    mode = stripe_mode()
    return [f"/health reports stripe_mode '{mode}', wanted test or live"] * (
        mode not in ("test", "live")
    )


def stripe_live() -> list[str]:
    """Task 21: stripe_mode alone was green BEFORE the live switch, because a live key
    and a still-test price both leave stripe_mode == 'live' — the key's prefix says
    nothing about the price. Refuses unless BOTH are live."""
    mode = stripe_mode()
    price_live = stripe_price_live()
    problems = [f"/health reports stripe_mode '{mode}', wanted live"] * (mode != "live")
    problems += ["/health reports stripe_price_live false, wanted true"] * (not price_live)
    return problems


CHECKS = {
    "stripe_mode_reported": stripe_mode_reported,
    "stripe_live": stripe_live,
    "favicon": favicon,
    "redirect": redirect,
    "human_check_look": human_check_look,
    "upload_thumbnails": upload_thumbnails,
    "waiting_state": waiting_state,
    "robots": robots,
    "sitemap": sitemap,
    "head": head,
    "attribution": attribution,
    "gallery_hidden": gallery_hidden,
}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in CHECKS:
        print("usage: check.py", "|".join(CHECKS))
        return 2
    problems = CHECKS[argv[1]]()
    for line in problems:
        print("RED  ", line)
    print("GREEN" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
