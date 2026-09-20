"""Outside-in checks against production. Read-only: GET requests only, no cost, no email.

Usage: python scripts/check.py <name>     Exit 0 = green, 1 = red, 2 = unknown name.
"""

from __future__ import annotations

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


CHECKS = {
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
