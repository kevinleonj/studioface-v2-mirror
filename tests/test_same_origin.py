"""Every browser-originated request is a relative path. The third outage came from one
that was not.

MEASURED, 18 Sep 2026:

    curl -i -X OPTIONS https://api.studioface.app/api/preview \\
      -H "Origin: https://studioface.app" \\
      -H "Access-Control-Request-Method: POST"

    HTTP/1.1 405 Method Not Allowed
    (no access-control-allow-origin header)

`NEXT_PUBLIC_API_URL` was `https://api.studioface.app`, so `apiUrl("/api/preview")` built
an absolute URL to a **different hostname** than the page. The app installs
`GZipMiddleware` and nothing else, and Starlette only answers `OPTIONS` on a route when
`CORSMiddleware` is present — so every preflight 405s.

Two different deaths, one cause (docs/verified.md):

- `/api/checkout` sends `Content-Type: application/json`, which is not CORS-safelisted,
  so it **preflights**, gets the 405, and the browser never sends the POST.
- `/api/preview` sends `multipart/form-data`, which IS safelisted, so it does not
  preflight — the POST goes out, and then "the response would be ignored and not made
  available to the web content" because there is no `Access-Control-Allow-Origin`.
  `fetch` rejects and the visitor is told "No hemos podido conectar."

**The fix is to remove the cross-origin call, not to permit it.** Both hostnames are the
same Cloud Run service and the same FastAPI process — `/health` answers identically on
both — and MDN is explicit that same-origin requests are not subject to CORS at all. A
CORS allowlist would be a second thing to keep correct in order to reach a server we are
already talking to.

`api.studioface.app` stays, for the Stripe webhook and Cloud Tasks. Those are
server-to-server, have no Origin, and CORS does not apply to them.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_scan import Scanner, strip_comments  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
CONFIG = FRONTEND / "lib" / "config.ts"
DEPLOY = ROOT / ".github" / "workflows" / "deploy.yml"

# Any absolute http(s) URL handed to something that performs a request. Turnstile's
# script tag and the Google Tag script are absolute by necessity — they are third-party
# origins and the browser loads them as scripts, not as XHR — so they are matched here
# and excluded by name below rather than by a vaguer pattern.
ABSOLUTE_FETCH = Scanner(
    name="absolute-origin-in-fetch",
    pattern=r"(?:fetch|axios|XMLHttpRequest[^;]*open)\(\s*[\"'`](https?://[^\"'`]+)",
    catches=('fetch("https://api.studioface.app/api/preview")', "fetch('http://x/y')"),
    ignores=('fetch("/api/preview")', 'fetch(apiUrl("/api/preview"))'),
    fixture="offenders.tsx",
    language="tsx",
)


def sources() -> dict[str, str]:
    out = {}
    for path in sorted(FRONTEND.rglob("*.ts*")):
        out[path.relative_to(FRONTEND).as_posix()] = strip_comments(
            path.read_text(encoding="utf-8"), language="tsx"
        )
    return out


def test_no_browser_request_targets_an_absolute_origin():
    offenders = []
    for name, text in sources().items():
        for url in ABSOLUTE_FETCH.findall(text):
            offenders.append(f"{name}: {url}")
    assert not offenders, f"cross-origin browser requests: {offenders}"


def test_the_api_base_is_gone_from_the_frontend_entirely():
    """Not emptied — gone. An `API_URL` that is "" today is an API_URL somebody sets
    tomorrow, and the outage comes back with no code change to review."""
    text = strip_comments(CONFIG.read_text(encoding="utf-8"), language="ts")
    assert "NEXT_PUBLIC_API_URL" not in text, "the frontend can still be pointed off-origin"
    assert "API_URL" not in text, "the API base is still a configurable value"


@pytest.mark.mirror_incompatible(reason="reads .github/workflows, which the mirror does not carry")
def test_ci_no_longer_writes_an_api_base_into_the_build():
    """The value lived in a GitHub variable, so removing it from the code is half the
    job: the build must stop consuming it, or the next person re-adds the read.

    Comments stripped, and that is not a formality — the first version of this test
    failed against a correct workflow, because the YAML comment explaining why
    NEXT_PUBLIC_API_URL was removed contains the words NEXT_PUBLIC_API_URL. Fifth
    occurrence of that bug class in two days, caught in minutes by the helper built for
    it an hour ago rather than by a customer."""
    text = strip_comments(DEPLOY.read_text(encoding="utf-8"), language="yml")
    assert "NEXT_PUBLIC_API_URL" not in text, "deploy.yml still bakes an API base in"


def test_every_api_call_is_a_relative_path():
    """Held-out check. Deleting apiUrl() achieves nothing if a call site hardcodes the
    hostname instead."""
    calls = []
    for name, text in sources().items():
        for path in re.findall(r"fetch\(\s*[\"'`]([^\"'`]+)", text):
            calls.append((name, path))
        for path in re.findall(r"fetch\(\s*`([^`]+)`", text):
            calls.append((name, path))
    assert calls, "no fetch call sites found at all, which means this test is not looking"
    for name, path in calls:
        assert path.startswith("/"), f"{name}: fetch target is not a relative path: {path!r}"


@pytest.mark.skipif(
    not (ROOT / "frontend" / "out" / "index.html").exists(), reason="no build; CI builds first"
)
def test_the_built_bundle_carries_no_api_hostname():
    """The assertion that actually matches the outage. Everything above reads source;
    this reads what the browser is served."""
    export = ROOT / "frontend" / "out"
    offenders = []
    for path in sorted(export.rglob("*.js")):
        if "api.studioface.app" in path.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(path.relative_to(export).as_posix())
    assert not offenders, f"the api hostname is still in the shipped bundle: {offenders}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
