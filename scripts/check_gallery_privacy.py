"""Outside-in check: the private gallery key must never reach analytics or stay in the address.

Opens the gallery with a made-up order in the OLD link shape (?o=...&t=...), which customers
already hold in their inboxes. Read-only: a made-up order costs nothing and sends nothing.
Green only when (1) no request to Google carries the key or the order number, and (2) the
address bar no longer shows them in the query string after load. Exit 0 green, 1 red.
"""

from __future__ import annotations

import sys
import urllib.parse

from playwright.sync_api import sync_playwright

BASE = "https://studioface.app"
ORDER = "cs_test_REDACTED"
KEY = "0123456789abcdef0123456789abcdef"
GOOGLE_HOSTS = (
    "google-analytics.com",
    "analytics.google.com",
    "googletagmanager.com",
    "doubleclick.net",
    "google.com/ccm",
    "googleadservices.com",
)


def find_problems(base: str) -> list[str]:
    leaked: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_context(locale="es-ES").new_page()

        def watch(request) -> None:
            url = urllib.parse.unquote(request.url)
            body = urllib.parse.unquote(request.post_data or "")
            sent = url + body
            if any(host in url for host in GOOGLE_HOSTS) and (KEY in sent or ORDER in sent):
                leaked.append(url.split("?")[0])

        page.on("request", watch)
        page.goto(f"{base}/g/?o={ORDER}&t={KEY}", wait_until="load")
        page.wait_for_timeout(5000)
        query = urllib.parse.urlparse(page.url).query
        browser.close()
    problems = [f"gallery key or order number sent to {host}" for host in sorted(set(leaked))]
    if KEY in query or ORDER in query:
        problems.append("the key is still in the query string of the address bar after load")
    return problems


def main(argv: list[str]) -> int:
    problems = find_problems(argv[1] if len(argv) > 1 else BASE)
    for line in problems:
        print("RED  ", line)
    print("GREEN" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
