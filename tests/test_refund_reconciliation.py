"""Issue #10: the webhook subscribed to one event and the refund never reconciled.

Bizum refunds are asynchronous. Stripe's own words, from the Bizum page:

    "Los reembolsos de pagos Bizum son asíncronos y tardan hasta 5 minutos en
    completarse. Stripe te notifica el estatus final reembolso usando el evento webhook
    `refund.updated` o `refund.failed`."

So `stripe.Refund.create` returns `pending`, the order is written `failed_refund_pending`,
and without those two events **it stays pending forever** — the gallery keeps telling a
customer their money is on its way back with nothing left to confirm it ever arrived, and
a refund that FAILED is indistinguishable from one still settling.

`enabled_events` was `["checkout.session.completed"]`.

**The set must match the dispatch table exactly, in both directions.** An event we receive
and do not handle is dead weight that looks like coverage; an event we handle and do not
receive is a code path that never runs. The test below compares the two sets rather than
checking a list of names, so adding either half alone fails.

Mapping an event back to an order: the Refund object carries `metadata`, and the refund is
created with `metadata.order_id`. The alternative — looking up by refund id — would need a
new Firestore query and index for something the payload can carry for free.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from source_scan import strip_comments  # noqa: E402

from tests.test_health import build  # noqa: E402

STRIPE_TF = ROOT / "infra" / "stripe.tf"
MAIN = ROOT / "app" / "main.py"


def subscribed() -> set[str]:
    text = STRIPE_TF.read_text(encoding="utf-8")
    block = re.search(r"enabled_events\s*=\s*\[(.*?)\]", text, re.S)
    assert block, "the webhook endpoint declares no events"
    return set(re.findall(r'"([\w.]+)"', block.group(1)))


def handled() -> set[str]:
    """The dispatch table itself, imported rather than grepped.

    The first version read the function body with a regex and returned an EMPTY SET the
    moment the event names became module constants — so the comparison below passed
    vacuously against a handler that dispatched perfectly well. Reading the data
    structure cannot drift from what the code does, because it is what the code does."""
    from app.main import HANDLERS

    return set(HANDLERS)


def test_the_two_refund_events_are_subscribed():
    """GO-LIVE step 11b, and the reason Bizum cannot be enabled without it."""
    missing = {"refund.updated", "refund.failed"} - subscribed()
    assert not missing, f"a Bizum refund can never be confirmed or failed: {missing}"


def test_the_subscription_and_the_dispatch_table_are_the_same_set():
    """Both directions, which is the point.

    Subscribed-but-unhandled looks like coverage and is not. Handled-but-unsubscribed is
    a branch that never executes. Either way the refund state machine has a hole."""
    assert subscribed() == handled(), (
        f"subscribed but not handled: {sorted(subscribed() - handled())}; "
        f"handled but not subscribed: {sorted(handled() - subscribed())}"
    )


def deps_for(store):
    """A Deps carrying the store under test. _handle_event touches only
    d.pipeline.store and d.enqueue."""
    from app.core import Pipeline
    from app.guards import MemoryCounter, RateLimiter
    from app.main import Deps

    pipeline = Pipeline(
        store=store,
        model=type("M", (), {"edit": lambda self, u, p: "x"})(),
        storage=type("S", (), {"put": lambda self, k, u: k})(),
        send_email=lambda t, b: None,
        refund=lambda o, c: None,
        track_conversion=lambda o: None,
        secret="app",
    )
    return Deps(
        pipeline=pipeline,
        limiter=RateLimiter(counter=MemoryCounter()),
        enqueue=lambda i: None,
        preview_fn=lambda f, batch: "",
        webhook_secret="whsec",
        tasks_token="tt",
    )


def order_with_pending_refund(store):
    from app.core import Order

    order = Order(
        id="cs_test_refund",
        email="k@example.com",
        source_image_urls=["gs://src/a.jpg"],
        style="corporativo",
        amount_cents=1999,
        status="failed_refund_pending",
        refund_id="re_1",
        refund_status="pending",
    )
    store.put(order)
    return order


def event(kind: str, status: str, order_id: str = "cs_test_refund") -> dict:
    return {
        "id": f"evt_{kind}_{status}",
        "type": kind,
        "data": {
            "object": {
                "id": "re_1",
                "status": status,
                "metadata": {"order_id": order_id},
            }
        },
    }


def test_a_succeeded_refund_moves_the_order_out_of_pending():
    _, store = build()
    order_with_pending_refund(store)
    from app.main import _handle_event

    _handle_event(deps_for(store), event("refund.updated", "succeeded"))
    assert store.get("cs_test_refund").status == "failed_refunded"
    assert store.get("cs_test_refund").refund_status == "succeeded"


def test_a_failed_refund_says_so_rather_than_staying_pending():
    """The customer's money did NOT come back and Stripe returned it to our balance.
    Leaving the order 'pending' tells them the opposite of what happened."""
    _, store = build()
    order_with_pending_refund(store)
    from app.main import _handle_event

    _handle_event(deps_for(store), event("refund.failed", "failed"))
    order = store.get("cs_test_refund")
    assert order.status == "failed_refund_failed"
    assert order.refund_status == "failed"


def test_a_refund_event_for_an_unknown_order_is_ignored_not_crashed():
    """Stripe replays and fans out. An event about an order we have never seen must not
    500, because a 500 makes Stripe retry it forever."""
    _, store = build()
    from app.main import _handle_event

    out = _handle_event(deps_for(store), event("refund.updated", "succeeded", "cs_nope"))
    assert out == {"ignored": True}


def test_a_replayed_refund_event_is_claimed_once():
    """Same idempotency guarantee as the purchase path. Stripe delivers at least once."""
    _, store = build()
    order_with_pending_refund(store)
    from app.main import _handle_event

    d = deps_for(store)
    first = _handle_event(d, event("refund.updated", "succeeded"))
    second = _handle_event(d, event("refund.updated", "succeeded"))
    assert "duplicate" in second, f"the replay was processed again: {first} then {second}"


def test_the_refund_carries_the_order_id_so_the_event_can_be_mapped_back():
    """Without metadata there is nothing in the payload tying a refund to an order, and
    the alternative is a new Firestore query and index for something free."""
    code = strip_comments((ROOT / "app" / "entry.py").read_text(encoding="utf-8"), language="py")
    create = re.search(r"stripe\.Refund\.create\((.*?)\)", code, re.S)
    assert create, "no refund is created"
    assert "metadata" in create.group(1), "the refund carries no order_id"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
