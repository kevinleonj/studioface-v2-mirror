"""Task 95e: "¿Cómo nos encontraste?", asked once the photos are delivered, never before.

One optional question on the gallery page, shown only after delivery, so it can never
stand between a visitor and paying. The answer is stored on the order (field
`found_us`) through the same key the gallery already proves ownership with
(X-Gallery-Token), and scripts/funnel_report.py counts the answers. During the ad test
this is the one way to learn how much of the traffic comes from AI answers (ChatGPT,
Gemini, Claude, Copilot) rather than from Google: none of them send a referrer we can
rely on.

Never on the checkout path: no checkout file, server or browser, mentions it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from fake_firestore import FakeFirestore  # noqa: E402
from source_scan import strip_comments  # noqa: E402

from app.core import Order, OrderStore, Pipeline, delivery_token  # noqa: E402
from app.entry import FirestoreOrderStore  # noqa: E402
from app.found_us import FOUND_US  # noqa: E402
from app.guards import MemoryCounter, RateLimiter  # noqa: E402
from app.main import make_app  # noqa: E402
from scripts.found_us_report import found_us_counts  # noqa: E402

# The signing value the fake pipeline mints gallery keys with; a fixture, not a credential.
SIGNING = "fixture-signing-value"
ORDER = "cs_test_found_us_order"
GALLERY = ROOT / "frontend" / "src" / "app" / "g" / "page.tsx"
FOUND_US_UI = ROOT / "frontend" / "src" / "components" / "found-us.tsx"
LABELS = (
    "Google",
    "ChatGPT",
    "Gemini",
    "Claude",
    "Copilot",
    "Instagram, TikTok o YouTube",
    "Recomendación",
    "Otro",
)


def _order(status: str = "delivered", **extra) -> Order:
    return Order(
        id=ORDER,
        email="cliente@example.com",
        source_image_urls=["gs://src/a.jpg"],
        style="corporativo",
        amount_cents=1999,
        status=status,
        **extra,
    )


def _client(store: OrderStore) -> TestClient:
    pipeline = Pipeline(
        store=store,
        model=type("M", (), {"edit": lambda self, u, p: "https://fal/1.jpg"})(),
        storage=type("S", (), {"put": lambda self, k, u: f"gs://out/{k}"})(),
        send_email=lambda to, body: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret=SIGNING,
    )
    app = make_app(
        pipeline,
        RateLimiter(counter=MemoryCounter()),
        enqueue=lambda i: None,
        preview_fn=lambda files, batch: "",
        webhook_secret="whsec",
        tasks_token="tt",
        retrieve_session=lambda session_id: {},
        sign_url=lambda url: url,
    )
    return TestClient(app, follow_redirects=False)


def _post(client: TestClient, answer, key: str | bytes | None = None):
    key = delivery_token(ORDER, SIGNING) if key is None else key
    return client.post(
        f"/api/orders/{ORDER}/found-us",
        json={"answer": answer},
        headers={"X-Gallery-Token": key},
    )


# ------------------------------------------------ the route


def test_a_delivered_order_stores_the_answer():
    store = OrderStore()
    store.put(_order())
    assert _post(_client(store), "chatgpt").status_code == 204
    assert store.get(ORDER).found_us == "chatgpt"


def test_the_same_answer_twice_leaves_the_same_state():
    store = OrderStore()
    store.put(_order())
    client = _client(store)
    assert [_post(client, "google").status_code for _ in range(2)] == [204, 204]
    assert store.get(ORDER).found_us == "google"


def test_a_wrong_key_is_refused_exactly_like_the_gallery():
    store = OrderStore()
    store.put(_order())
    assert _post(_client(store), "google", key="0" * 32).status_code == 404
    assert store.get(ORDER).found_us is None


def test_a_non_ascii_key_is_a_404_not_a_500():
    """hmac.compare_digest raises on non-ASCII str (task 73): compare bytes. Sent as raw
    bytes, the way a hostile client can; httpx refuses a non-ASCII str header itself."""
    store = OrderStore()
    store.put(_order())
    response = _post(_client(store), "google", key="ñ-no-es-una-llave".encode())
    assert response.status_code == 404


def test_an_order_not_yet_delivered_is_refused():
    """Never before delivery: the question cannot sit anywhere near paying."""
    store = OrderStore()
    store.put(_order(status="paid"))
    assert _post(_client(store), "google").status_code == 409
    assert store.get(ORDER).found_us is None


def test_a_missing_order_is_a_404():
    assert _post(_client(OrderStore()), "google").status_code == 404


def test_an_answer_outside_the_list_is_refused():
    store = OrderStore()
    store.put(_order())
    assert _post(_client(store), "tiktok-ads").status_code == 422
    assert _post(_client(store), 5).status_code == 422
    assert store.get(ORDER).found_us is None


def test_the_answers_are_exactly_the_eight_asked_for():
    assert FOUND_US == (
        "google",
        "chatgpt",
        "gemini",
        "claude",
        "copilot",
        "social",
        "recomendacion",
        "otro",
    )


def test_firestore_writes_only_the_one_field():
    """A single-field update, not a whole-document put, so the answer can never overwrite
    a concurrent write to the order."""
    db = FakeFirestore()
    store = FirestoreOrderStore(db)
    store.put(_order(outputs=["gs://out/1.jpg"]))
    store.set_found_us(ORDER, "gemini")
    got = store.get(ORDER)
    assert got.found_us == "gemini" and got.outputs == ["gs://out/1.jpg"]
    assert got.status == "delivered"


# ------------------------------------------------ funnel_report counts


def _seed(db, oid: str, started: float, answer: str | None, status: str = "delivered"):
    db.collection("orders").document(oid).set(
        {"id": oid, "status": status, "started_at": started, "found_us": answer}
    )


DAY = 20_000


def test_no_orders_gives_every_answer_at_zero():
    counts = found_us_counts(FakeFirestore(), DAY, DAY)
    assert counts == {**{a: 0 for a in FOUND_US}, "sin respuesta": 0}


def test_one_answer_is_counted():
    db = FakeFirestore()
    _seed(db, "a", DAY * 86400 + 60, "claude")
    assert found_us_counts(db, DAY, DAY)["claude"] == 1


def test_many_orders_count_by_answer_and_unanswered_delivered_orders_separately():
    db = FakeFirestore()
    _seed(db, "a", DAY * 86400 + 60, "google")
    _seed(db, "b", DAY * 86400 + 120, "google")
    _seed(db, "c", (DAY + 1) * 86400 + 5, "copilot")
    _seed(db, "d", DAY * 86400 + 180, None)
    _seed(db, "e", DAY * 86400 + 240, None, status="failed_refunded")
    counts = found_us_counts(db, DAY, DAY + 1)
    assert counts["google"] == 2 and counts["copilot"] == 1
    assert counts["sin respuesta"] == 1, "only delivered orders could have answered"


def test_orders_outside_the_range_are_not_counted():
    db = FakeFirestore()
    _seed(db, "a", (DAY - 1) * 86400 + 60, "google")
    assert found_us_counts(db, DAY, DAY)["google"] == 0


# ------------------------------------------------ the page


def test_the_gallery_asks_only_inside_the_delivered_block():
    code = strip_comments(GALLERY.read_text(encoding="utf-8"), language="tsx")
    delivered = code[code.index('{status === "delivered" ? (') :]
    delivered = delivered[: delivered.index(") : null}")]
    assert code.count("<FoundUs") == 1 and "<FoundUs" in delivered


def test_the_page_offers_exactly_the_server_list_with_the_asked_labels():
    code = strip_comments(FOUND_US_UI.read_text(encoding="utf-8"), language="tsx")
    keys = tuple(re.findall(r'value: "([a-z]+)"', code))
    assert keys == FOUND_US, "the browser and the server must accept the same answers"
    for label in LABELS:
        assert f'label: "{label}"' in code, label
    assert "¿Cómo nos encontraste?" in code


def test_nothing_on_the_checkout_path_mentions_it():
    """Must be refused: the question anywhere a visitor still has to pay."""
    for path in (
        ROOT / "frontend" / "src" / "components" / "upload-form.tsx",
        ROOT / "frontend" / "src" / "components" / "ad-landing.tsx",
        ROOT / "frontend" / "src" / "app" / "page.tsx",
    ):
        assert "found-us" not in path.read_text(encoding="utf-8").lower(), path
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    checkout = main[main.index('@app.post("/api/checkout")') :]
    checkout = checkout[: checkout.index("\ndef ")]
    assert "found" not in checkout.lower()


def test_the_morning_command_still_starts():
    """Nobody asked for this one, and it broke once already: run as Kevin runs it
    (`python scripts/funnel_report.py`), `scripts` is not an importable package, so a
    package-style import of the new counting module crashed before printing anything."""
    import subprocess

    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "funnel_report.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 0, done.stderr[-400:]
    assert "--since" in done.stdout
