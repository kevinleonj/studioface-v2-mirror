"""The funnel harness's own wiring, checked without a browser or a fal credit.

Task 75. Cloudflare's published dummy secret reports a CONSTANT hostname, so the
harness cannot verify tokens against the host it actually serves. Measured against
Cloudflare on 22 Sep 2026 (docs/verified.md):

    POST /turnstile/v0/siteverify  secret=<dummy> response=XXXX.DUMMY.TOKEN.XXXX
    -> {"success": true, "hostname": "example.com", ...}

That is returned wherever the widget was really solved. Before this test the harness
expected hostname_of("http://127.0.0.1:8099") and every /api/preview in the walk
answered 403 "La comprobacion de seguridad no ha pasado".
"""

from __future__ import annotations

from tests.e2e.funnel_app import DUMMY_SECRET, expected_turnstile_hostname

BASE = "http://127.0.0.1:8099"


def test_the_dummy_secret_expects_the_constant_cloudflare_reports():
    """Must get through: this is the pair the walk actually runs on."""
    assert expected_turnstile_hostname(DUMMY_SECRET, BASE) == "example.com"


def test_a_real_secret_still_expects_the_host_being_served():
    """Must be refused: a non-dummy secret never borrows the dummy's constant, so a
    token solved on someone else's site still fails the check in app/adapters."""
    assert expected_turnstile_hostname("0x4AAAAAAAreal_looking_secret", BASE) == "127.0.0.1"
    assert (
        expected_turnstile_hostname("0x4AAAAAAAreal_looking_secret", "https://studioface.app")
        == "studioface.app"
    )


def test_the_runner_and_the_harness_mean_the_same_dummy_secret():
    """Nobody asked for this one. scripts/run_funnel.py writes the secret into the
    environment and funnel_app.py decides the hostname from it, each from its own
    literal. If they ever drift the walk goes back to 403 with nothing to point at."""
    import scripts.run_funnel as runner

    assert runner.DUMMY_SECRET == DUMMY_SECRET
