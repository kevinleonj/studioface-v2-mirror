"""Non-developer proof that the preview guard is enforced in PRODUCTION.
Usage:  python scripts/verify_ratelimit.py https://api.studioface.app <selfie.jpg> [turnstile_token]
Expected without token: 403 x5. With a token from the site: 200 200 200 429 429.
"""

import sys

import httpx

api, img = sys.argv[1], sys.argv[2]
token = sys.argv[3] if len(sys.argv) > 3 else ""
data = {"turnstile_token": token} if token else {}
for i in range(1, 6):
    with open(img, "rb") as fh:
        r = httpx.post(f"{api}/api/preview", files={"files": fh}, data=data, timeout=60)
    print(f"call {i}: HTTP {r.status_code}")
print("PASS without token: 403 x5.  PASS with token: 200 200 200 429 429")
