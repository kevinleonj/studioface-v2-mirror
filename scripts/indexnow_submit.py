"""Submit changed URLs to IndexNow (Bing, Yandex, Seznam, Naver, Yep share the feed;
Google does not).
Usage: INDEXNOW_KEY=... python scripts/indexnow_submit.py URL [URL ...]
Exit 0 only on HTTP 200 or 202. The key is read from the environment, never hard-coded."""

import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

ENDPOINT = os.environ.get("INDEXNOW_ENDPOINT", "https://api.indexnow.org/indexnow")


def main(urls):
    key = os.environ.get("INDEXNOW_KEY", "")
    if not (8 <= len(key) <= 128) or not all(c.isalnum() or c == "-" for c in key):
        print("INDEXNOW_KEY missing or malformed")
        return 2
    hosts = {urlparse(u).netloc for u in urls}
    if len(hosts) != 1 or not urls:
        print("all URLs must share one host")
        return 2
    host = hosts.pop()
    # IndexNow answers 202 even when the key file is missing, then drops the URLs silently.
    # So prove the key file is live first: HTTP 200 and body equal to the key.
    key_url = f"https://{host}/{key}.txt"
    try:
        with urllib.request.urlopen(key_url, timeout=10) as r:
            live = r.status == 200 and r.read().decode().strip() == key
    except urllib.error.URLError:
        live = False
    if not live and os.environ.get("INDEXNOW_SKIP_KEY_CHECK") != "1":
        print(f"key file not live at {key_url}; nothing submitted")
        return 1
    body = json.dumps(
        {
            "host": host,
            "key": key,
            "keyLocation": f"https://{host}/{key}.txt",
            "urlList": urls[:10000],
        }
    ).encode()
    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    print(f"IndexNow {code} for {len(urls)} URL(s)")
    return 0 if code in (200, 202) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
