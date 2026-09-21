"""The health check must live on a path that can actually be reached in production.

Google Front End answers the literal path /healthz itself, on every *.run.app host,
before the request reaches the container. Our app served /healthz correctly — locally,
and `/openapi.json` on the live revision listed it — but nothing outside the container
could ever call it, so the deploy smoke step failed on a healthy revision.

Evidence from revision 00004 (docs/verified.md, 2026-09-17):
    /healthz          404, 1568 bytes, Google's own error page, no x-cloud-trace-context
    /healthzz         404, 12165 bytes, our Next.js 404 — the container answered
    /nonexistent-page 404, 12165 bytes, our Next.js 404 — the container answered

Sibling paths are untouched, so the fix is the path, not the handler.
"""

import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import OrderStore, Pipeline  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import HEALTH_PATH, make_app  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEPLOY_YML = ROOT / ".github" / "workflows" / "deploy.yml"

# Paths Google Front End answers itself on *.run.app, so a container never sees them.
RESERVED_BY_GOOGLE_FRONTEND = {"/healthz"}


def build(static_dir=None, stripe_mode="unknown", stripe_price_live=False):
    store = OrderStore()
    pipeline = Pipeline(
        store=store,
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
        static_dir=static_dir,
        stripe_mode=stripe_mode,
        stripe_price_live=stripe_price_live,
    )
    return TestClient(app), store


# ---------------------------------------------------------------- the path


def test_health_is_not_on_a_path_google_answers_for_us():
    """The regression itself. /healthz cannot be reached on Cloud Run, so putting the
    only health check there makes a healthy revision look dead."""
    assert HEALTH_PATH not in RESERVED_BY_GOOGLE_FRONTEND


def test_health_responds():
    c, _ = build()
    r = c.get(HEALTH_PATH)
    assert r.status_code == 200
    assert r.json() == {
        "ok": True,
        "killswitch": False,
        "stripe_mode": "unknown",
        "stripe_price_live": False,
    }


def test_health_reports_the_killswitch():
    c, store = build()
    store.killswitch = True
    assert c.get(HEALTH_PATH).json() == {
        "ok": True,
        "killswitch": True,
        "stripe_mode": "unknown",
        "stripe_price_live": False,
    }


def test_health_reports_the_stripe_mode():
    c, _ = build(stripe_mode="test")
    assert c.get(HEALTH_PATH).json()["stripe_mode"] == "test"


def test_health_reports_the_stripe_mode_live():
    """Twin of the test above: identical wiring, live word, so this field cannot be
    hard-coded to 'test' and still pass."""
    c, _ = build(stripe_mode="live")
    assert c.get(HEALTH_PATH).json()["stripe_mode"] == "live"


def test_health_reports_stripe_price_live_true():
    """Task 21, twin one of two. stripe_mode alone stayed green through the exact
    outage state — a live key paired with a still-test price — because it only reads
    the key's prefix. This field is the one Stripe itself can answer."""
    c, _ = build(stripe_price_live=True)
    assert c.get(HEALTH_PATH).json()["stripe_price_live"] is True


def test_health_reports_stripe_price_live_false():
    """Twin two of two: identical wiring, the other bool, so this field cannot be
    hard-coded to True and still pass."""
    c, _ = build(stripe_price_live=False)
    assert c.get(HEALTH_PATH).json()["stripe_price_live"] is False


def test_the_old_reserved_path_is_gone_rather_than_left_as_a_decoy():
    """Leaving /healthz registered would keep passing every local test while staying
    unreachable in production — exactly how this survived to a deploy."""
    c, _ = build()
    assert c.get("/healthz").status_code == 404


def test_health_still_wins_over_the_static_mount(tmp_path):
    (tmp_path / "index.html").write_text("<h1>StudioFace</h1>")
    c, _ = build(static_dir=str(tmp_path))
    assert c.get("/").text == "<h1>StudioFace</h1>"
    assert c.get(HEALTH_PATH).json()["ok"] is True


# ---------------------------------------------------------------- the contract with CI


VERIFIER = ROOT / "scripts" / "verify_production.py"


def smoke_paths() -> list[str]:
    """Every path the deploy's outside-in verifier requests against the live service.

    It used to read `curl -fsS "$URL/..."` out of deploy.yml. Those two curls — /health
    and / — were green throughout all three outages, because a service can serve a
    perfect 200 to a landing page whose funnel is dead. The step is now
    scripts/verify_production.py, so this reads the paths out of the verifier instead.
    The guarantee is unchanged and the thing being guaranteed is stronger.
    """
    text = VERIFIER.read_text(encoding="utf-8")
    return sorted(set(re.findall(r'f"\{base\}(/[^"]*)"', text)))


def test_the_deploy_verifies_from_outside_rather_than_curling_two_paths():
    """The rule this exists to hold: a deploy that leaves the funnel dead is a RED
    deploy. If the verifier is ever dropped from the workflow, nothing else notices."""
    text = DEPLOY_YML.read_text(encoding="utf-8")
    assert "verify_production.py" in text, "the deploy no longer checks production at all"
    assert "PUBLIC_DOMAIN" in text, (
        "the verifier runs against the run.app URL, not the hostname a customer uses — "
        "which is where outage 3 lived, since CORS only exists on the public hostname"
    )


def test_the_verifier_requests_paths_this_app_actually_serves(tmp_path):
    """Held-out check: the app and the verifier can drift apart silently, and the only
    other place that notices is production, after a deploy.

    Built with the static export mounted, because the deployed image always has one
    (the Dockerfile copies it and sets STATIC_DIR), and one requested path is "/"."""
    (tmp_path / "index.html").write_text("<h1>StudioFace</h1>")
    c, _ = build(static_dir=str(tmp_path))
    paths = smoke_paths()
    assert paths, f"no request paths found in {VERIFIER}"
    for path in paths:
        got = c.get(path).status_code
        assert got != 405, f"the verifier requests {path!r} with a method the app refuses"
        assert got != 500, f"the verifier requests {path!r} and the app raises"


def test_the_verifier_does_not_request_a_reserved_path():
    for path in smoke_paths():
        assert path not in RESERVED_BY_GOOGLE_FRONTEND, (
            f"the verifier requests {path!r}, which Google Front End answers before Cloud Run"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
