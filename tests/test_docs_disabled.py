"""F8/O9: `/docs`, `/redoc` and `/openapi.json` answer 200 in production.

Open since the go-live audit of 19 September and still open at 15:34 UTC. It publishes
every route, every parameter name and every response shape of the money path to anybody
who asks - including `/internal/generate/{order_id}`, `/internal/budget` and the exact
query parameter `/api/gracias` reads.

Two twins, because a flag that is off everywhere is not a configuration, it is a
deletion (P1): 404 when the flag is off, 200 when it is on. The local harness and the
tests keep their documentation; only production loses it.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import OrderStore, Pipeline  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import make_app  # noqa: E402

DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


def build(**kwargs):
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
        **kwargs,
    )
    from fastapi.testclient import TestClient

    return TestClient(app)


def test_the_documentation_is_gone_when_the_flag_is_off():
    """O9. This is production."""
    client = build(docs=False)
    for path in DOC_PATHS:
        assert client.get(path).status_code == 404, f"{path} is still published"


def test_the_documentation_is_there_when_the_flag_is_on():
    """The twin. A flag that is off everywhere is a deletion pretending to be a
    configuration, and it would pass the test above just as well."""
    client = build(docs=True)
    for path in DOC_PATHS:
        assert client.get(path).status_code == 200, f"{path} is missing locally"


def test_the_default_is_off():
    """Fail closed. The one place this matters is the one place nobody sets the flag."""
    client = build()
    assert client.get("/openapi.json").status_code == 404


def test_the_routes_themselves_still_work_with_the_documentation_off():
    """Held-out check: `openapi_url=None` disables the schema, not the application."""
    client = build(docs=False)
    assert client.get("/health").status_code == 200


def test_production_settings_keep_it_off_unless_asked():
    """By configuration, not by a literal in entry.py."""
    from app.config import Settings

    env = {
        "GCP_PROJECT": "sf",
        "GCP_REGION": "europe-west1",
        "PUBLIC_URL": "https://studioface.app",
        "BUCKET_SRC": "s",
        "BUCKET_OUT": "o",
        "TASKS_QUEUE": "q",
        "TASKS_TOKEN": "t",
        "APP_TOKEN_SECRET": "a",
        "STRIPE_SECRET_KEY": "sk_test_x",
        "STRIPE_WEBHOOK_SECRET": "w",
        "RESEND_API_KEY": "r",
        "TURNSTILE_SECRET": "ts",
    }
    assert Settings.from_env(env).enable_docs is False
    assert Settings.from_env({**env, "ENABLE_DOCS": "1"}).enable_docs is True


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
