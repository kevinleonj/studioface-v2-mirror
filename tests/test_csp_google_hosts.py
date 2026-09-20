"""M1 (E5): the Content-Security-Policy is missing hosts Google's own guide requires.

Measured against production on 19 September, before the fix - revision
`studioface-api-00079-8bq`, the `content-security-policy` response header on `/`:

    script-src  'self' 'unsafe-inline' https://challenges.cloudflare.com
                https://www.googletagmanager.com
    img-src     'self' data: https://challenges.cloudflare.com https://storage.googleapis.com
    connect-src 'self' https://challenges.cloudflare.com https://*.challenges.cloudflare.com
                https://*.google-analytics.com https://*.analytics.google.com
    frame-src   https://challenges.cloudflare.com

Ten hosts Google requires were absent. Two consequences, one of them already live:

1. GA4 sends image pings to `www.googletagmanager.com` and, with Ads features on, to
   `*.g.doubleclick.net`. `img-src` allowed neither, so those were already being dropped.
2. A Google Ads conversion tag added for the ads test would load
   `www.googleadservices.com`, ping `googleads.g.doubleclick.net` and frame
   `www.googletagmanager.com` - all blocked. CSP failures are silent to the advertiser:
   the tag reports nothing, the campaign shows zero conversions, and the obvious
   conclusion is that the landing page does not convert.

## What Google's guide actually says (docs/verified.md, 19 Sep)

https://developers.google.com/tag-platform/security/guides/csp, fetched today. The lists
below are transcribed from it, not remembered.

## Two judgements this file encodes

**`script-src-elem` vs `script-src`.** Google writes `script-src-elem`. We send only
`script-src`, and CSP Level 3 falls back to `script-src` when `script-src-elem` is absent,
so listing the hosts there is sufficient - as long as nobody later introduces a
`script-src-elem`, which would shadow `script-src` for element-loaded scripts and silently
undo this. A test below holds that shut.

**`https://*.google.<TLD>` is a placeholder, not a literal.** It cannot go into a header
as written; `<TLD>` is not a domain. Google redirects an Ads conversion ping through the
visitor's local Google property, so the fix has to name the ones we actually serve. This
product sells in Spain: `*.google.com` and `*.google.es`.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.main import CSP, csp  # noqa: E402

# Transcribed from Google's guide, with <TLD> expanded to the properties we serve.
# GA4 "with Ads features" plus the Google Ads conversion tag, unioned.
TLDS = ("https://*.google.com", "https://*.google.es")
REQUIRED = {
    "script-src": [
        "https://www.googletagmanager.com",
        "https://www.googleadservices.com",
        "https://www.google.com",
    ],
    "img-src": [
        "https://www.googletagmanager.com",
        "https://*.google-analytics.com",
        "https://*.g.doubleclick.net",
        "https://googleads.g.doubleclick.net",
        "https://www.googleadservices.com",
        "https://pagead2.googlesyndication.com",
        *TLDS,
    ],
    "connect-src": [
        "https://www.googletagmanager.com",
        "https://*.google-analytics.com",
        "https://*.g.doubleclick.net",
        "https://googleads.g.doubleclick.net",
        "https://www.googleadservices.com",
        "https://pagead2.googlesyndication.com",
        "https://ad.doubleclick.net",
        *TLDS,
    ],
    "frame-src": ["https://www.googletagmanager.com"],
}

# Directives that exist to STOP things. If the fix widened any of these it bought GA4 at
# the price of the protections U1-U3 were about.
LOCKED = {
    "default-src": ["'self'"],
    "base-uri": ["'self'"],
    "object-src": ["'none'"],
    "frame-ancestors": ["'none'"],
    "form-action": ["'self'"],
}


def allows(sources: list[str], host: str) -> bool:
    """Does this directive's source list permit `host`?

    A served `https://*.google.com` satisfies a required `https://www.google.com`, so the
    test can quote Google's literal list while the header uses the wildcard Google itself
    offers. `https://*.g.doubleclick.net` does NOT cover `https://ad.doubleclick.net`,
    which is exactly why that one needs its own entry.
    """
    if host in sources:
        return True
    name = host.removeprefix("https://")
    return any(
        name.endswith(s.removeprefix("https://*")) for s in sources if s.startswith("https://*.")
    )


def parse(header: str) -> dict[str, list[str]]:
    """Parse what is actually sent, the way a browser reads it - not the dict we built."""
    out = {}
    for part in header.split(";"):
        directive, *values = part.strip().split()
        out[directive] = values
    return out


@pytest.mark.parametrize(
    ("directive", "host"),
    [(d, h) for d, hosts in REQUIRED.items() for h in hosts],
)
def test_every_host_google_requires_is_allowed(directive, host):
    """The production defect, one row per host, so a failure names the missing one."""
    served = parse(csp())
    assert directive in served, f"{directive} is not in the header at all"
    assert allows(served[directive], host), f"{directive} does not allow {host}"


def test_no_directive_that_stops_something_was_widened():
    """Held-out check. Adding `default-src https:` would pass every test above and undo
    the reason a CSP exists."""
    served = parse(csp())
    for directive, expected in LOCKED.items():
        assert served.get(directive) == expected, f"{directive} is now {served.get(directive)}"


def test_no_blanket_source_anywhere():
    """`*`, bare `https:` or `data:` in script-src would each satisfy the whole REQUIRED
    list while allowing every host on the internet."""
    for directive, sources in CSP.items():
        assert "*" not in sources, directive
        assert "https:" not in sources, directive
        assert "'unsafe-eval'" not in sources, directive
    assert "data:" not in CSP["script-src"]


def test_the_tld_placeholder_was_not_copied_literally():
    """`https://*.google.<TLD>` is prose in Google's document. In a header it is a domain
    that cannot resolve, and the directive around it still parses, so it fails silently."""
    assert "<TLD>" not in csp()
    assert "%3CTLD%3E" not in csp()


def test_script_src_elem_is_absent_so_script_src_governs():
    """Google specifies `script-src-elem`. We satisfy it by fallback. Introducing a
    `script-src-elem` later would shadow `script-src` for every element-loaded script and
    silently block the tags this unit just allowed."""
    assert "script-src-elem" not in CSP, "then the Google hosts must be repeated there"


def test_the_header_is_actually_sent_on_a_real_response():
    """Cold start. The dict being right is not the same as the middleware sending it."""
    from fastapi.testclient import TestClient

    from app.core import OrderStore, Pipeline
    from app.guards import MemoryCounter, RateLimiter
    from app.main import make_app

    pipeline = Pipeline(
        store=OrderStore(),
        model=type("M", (), {"edit": lambda self, u, p: "x"})(),
        storage=type("S", (), {"put": lambda self, k, u: k})(),
        send_email=lambda t, b: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret="app",
    )
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter()),
        enqueue=lambda i: None,
        preview_fn=lambda f, batch: "",
        webhook_secret="whsec",
        tasks_token="tt",
    )
    header = TestClient(app).get("/health").headers.get("content-security-policy", "")
    assert header, "no CSP header on a real response"
    served = parse(header)
    assert allows(served["img-src"], "https://*.g.doubleclick.net")
    assert allows(served["frame-src"], "https://www.googletagmanager.com")


def test_turnstile_and_signed_images_still_work():
    """Held-out check the other way: this unit must not have displaced what was there.
    Turnstile is the gate on the free preview and the signed-URL host is the gallery."""
    served = parse(csp())
    assert allows(served["script-src"], "https://challenges.cloudflare.com")
    assert allows(served["frame-src"], "https://challenges.cloudflare.com")
    assert allows(served["img-src"], "https://storage.googleapis.com")
    assert allows(served["connect-src"], "https://*.analytics.google.com")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
