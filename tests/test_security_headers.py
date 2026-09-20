"""The site served no security headers at all. Measured, not suspected.

    $ curl -I https://studioface.app/
    content-type, accept-ranges, last-modified, etag, cache-control,
    x-cloud-trace-context, content-length, date, server

That is the whole list. No HSTS, no X-Content-Type-Options, no Referrer-Policy, no CSP.

Every allowed origin below comes from one of two places and never from memory: the
vendor's own CSP documentation, or a measurement of what our pages actually request.
Both are cited in docs/verified.md.

**Stripe is absent from the CSP on purpose.** Stripe publishes a long list of directives
and none of them apply to us: Checkout runs in REDIRECT mode — `window.location.href =
data.url` — so the browser leaves studioface.app before any Stripe code runs, and a grep
for `js.stripe.com` or `Stripe(` across frontend/src returns nothing. Adding Stripe hosts
"to be safe" would widen the policy for a script that never loads, which is the opposite
of a policy.

**`'unsafe-inline'` in script-src is the known weak point.** Next emits inline scripts —
the RSC flight payload and the Consent Mode default — and this is a static export served
by FastAPI, so there is no per-request nonce to hand them. It is recorded here rather
than hidden: the CSP still blocks script from any origin not listed, which is the main
exfiltration path, and the route to closing it is in docs/verified.md.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.main import SECURITY_HEADERS, csp  # noqa: E402

# From Cloudflare's own CSP reference.
TURNSTILE = "https://challenges.cloudflare.com"
# Measured on the live pages, three routes, by resource type.
GA_SCRIPT = "https://www.googletagmanager.com"
# Signed URLs for delivered photographs are issued against this host.
SIGNED_IMAGES = "https://storage.googleapis.com"
# Stripe hosts, none of which may appear: Checkout is a redirect, not an embed.
STRIPE_HOSTS = ("js.stripe.com", "checkout.stripe.com", "api.stripe.com", "hooks.stripe.com")


def directives() -> dict[str, list[str]]:
    out = {}
    for part in csp().split(";"):
        part = part.strip()
        if not part:
            continue
        name, *values = part.split()
        out[name] = values
    return out


def test_every_header_the_brief_named_is_present():
    for name in (
        "strict-transport-security",
        "x-content-type-options",
        "referrer-policy",
        "content-security-policy",
    ):
        assert name in SECURITY_HEADERS, f"{name} is still missing"


def test_hsts_is_a_year_and_covers_subdomains():
    """MDN's recommended value. api.studioface.app is a subdomain and carries the Stripe
    webhook, so includeSubDomains is not decoration."""
    value = SECURITY_HEADERS["strict-transport-security"]
    age = re.search(r"max-age=(\d+)", value)
    assert age, value
    assert int(age.group(1)) >= 31536000, f"max-age is under a year: {value}"
    assert "includeSubDomains" in value


def test_hsts_does_not_claim_preload_we_have_not_submitted():
    """`preload` is a promise to the browser vendors' hard-coded list, and getting off
    that list takes months. It is not a header you add speculatively."""
    assert "preload" not in SECURITY_HEADERS["strict-transport-security"]


def test_nosniff_and_referrer_policy_are_the_strict_values():
    assert SECURITY_HEADERS["x-content-type-options"] == "nosniff"
    assert SECURITY_HEADERS["referrer-policy"] in {
        "no-referrer",
        "same-origin",
        "strict-origin-when-cross-origin",
    }


def test_the_csp_allows_turnstile_exactly_where_cloudflare_says_it_needs_it():
    d = directives()
    assert TURNSTILE in d["script-src"], "the challenge script cannot load"
    assert TURNSTILE in d["frame-src"], "the challenge widget cannot render"


def test_the_csp_allows_the_analytics_we_actually_load_and_nothing_further():
    d = directives()
    assert GA_SCRIPT in d["script-src"]
    assert any("google-analytics.com" in v for v in d["connect-src"]), (
        "gtag posts to a regional google-analytics.com host; measured region1"
    )


def test_the_csp_names_no_stripe_host():
    """Checkout is a redirect. Widening the policy for a script that never loads is the
    opposite of a policy, and it is the most tempting thing to copy out of Stripe's docs
    without checking whether it applies."""
    policy = csp()
    present = [h for h in STRIPE_HOSTS if h in policy]
    assert not present, f"Stripe hosts in a policy that never loads Stripe: {present}"


def test_the_csp_allows_signed_photograph_urls():
    """The gallery renders images from signed Cloud Storage URLs. A CSP that forgets them
    delivers a blank grid to somebody who has paid."""
    assert SIGNED_IMAGES in directives()["img-src"]


def test_the_csp_closes_the_directives_that_cost_nothing_to_close():
    d = directives()
    assert d["object-src"] == ["'none'"], "object-src is the cheapest XSS surface to shut"
    assert d["frame-ancestors"] == ["'none'"], "the page can still be framed"
    assert d["base-uri"] == ["'self'"], "an injected <base> can redirect every relative URL"
    assert d["form-action"] == ["'self'"], "an injected form can post the upload elsewhere"


def test_the_csp_has_a_default_src_so_an_unlisted_directive_is_not_open():
    d = directives()
    assert d["default-src"] == ["'self'"], "anything not named falls back to open"


def test_no_directive_allows_a_bare_wildcard():
    for name, values in directives().items():
        assert "*" not in values, f"{name} allows any origin"
        for value in values:
            assert not value.startswith("http://"), f"{name} allows plaintext: {value}"


# ---------------------------------------------------------------- on the wire


def client(tmp_path):
    """The app with the static export mounted, because the page a visitor loads is
    served by StaticFiles and that is exactly the response a CSP has to reach."""
    from tests.test_health import build

    (tmp_path / "index.html").write_text("<h1>StudioFace</h1>", encoding="utf-8")
    c, _ = build(static_dir=str(tmp_path))
    return c


def test_the_headers_are_actually_on_the_wire_not_merely_in_a_dict(tmp_path):
    """Held-out check. Every test above reads a Python dict; this is the one that fails
    if the middleware is never registered, which is the whole failure mode."""
    c = client(tmp_path)
    for path in ("/", "/health"):
        r = c.get(path)
        for name in SECURITY_HEADERS:
            assert name in r.headers, f"{path} carries no {name}"
        assert r.headers["content-security-policy"] == csp()


def test_an_error_response_carries_them_too(tmp_path):
    """A 404 is a response an attacker can reach as easily as a 200, and a page that
    drops its CSP on the error path has a CSP with a hole in it."""
    r = client(tmp_path).get("/api/orders/nope/nope")
    assert r.status_code == 404
    assert "content-security-policy" in r.headers


def test_the_cache_policy_still_wins_where_it_was_set(tmp_path):
    """setdefault, not assignment: CachedStatic sets cache-control per path and the
    security middleware must not flatten it. Regression guard for a fix breaking a fix."""
    c = client(tmp_path)
    assert c.get("/").headers["cache-control"] == "no-cache"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
