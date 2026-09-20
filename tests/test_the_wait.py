"""The two screens a customer stares at, and the bar that was lying on both.

Measured on a served copy of the export, at 1440x900, with every /g/ state stubbed —
four of the five needed the API faked, which is why nobody had ever looked at them:

    state               content ends   footer at   dead canvas
    g-working                    273         656        383px
    g-notfound                   277         656        379px
    g-refunded                   253         656        403px
    g-refund-pending             277         656        379px
    recuperar                    361         656        295px

`g-working` is the page a customer sees straight after paying 19,99 EUR, for about two
minutes. It held a heading, one sentence, a progress bar frozen at 45%, and 383px of
nothing.

The bar is the part that matters. `value={45}` is a constant. Nothing measures it,
nothing moves it, and it is on both screens where money is in flight: `value={60}` on
the upload form as well. A bar that reports a number it did not measure is a fake
progress indicator, which docs/DESIGN.md bans outright, and it is worse than no
indicator because it invites the customer to read a position that means nothing.

What replaces it is the only honest thing available: what is happening, how long it
usually takes, the four frames that are coming, and the fact that they can close the
page because the email arrives either way. That last one is true — the pipeline sends
it on delivery (app/emails.py), so it is a fact and not reassurance.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_scan import Scanner, strip_comments  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
GALLERY = FRONTEND / "app" / "g" / "page.tsx"
RECOVER = FRONTEND / "app" / "recuperar" / "page.tsx"
UPLOAD = FRONTEND / "components" / "upload-form.tsx"


# The literal that was lying on both money screens. A Scanner rather than an inline
# regex so tests/test_source_scanners.py can prove, every run, that it still matches a
# fake bar and still ignores a real one bound to a variable.
FAKE_PROGRESS = Scanner(
    name="fake-progress-literal",
    pattern=r"<Progress[\s][^>]*value=\{(\d+)\}",
    catches=("<Progress value={45} />", '<Progress value={60} aria-label="x" />'),
    ignores=("<Progress value={done} />", "<ProgressBar value={45} />"),
)


def sources(code_only: bool = False) -> dict[str, str]:
    """`code_only` strips comments first.

    Third time for this bug class in three days: test_header grepped the rationale that
    explained why the header is not sticky, the bootstrap test grepped the comment that
    named core.hooksPath, and this one caught `<Progress value={60}>` inside the comment
    recording that `<Progress value={60}>` was deleted. A test that reads prose is
    testing prose."""
    out = {p.name: p.read_text(encoding="utf-8") for p in (GALLERY, RECOVER, UPLOAD)}
    if not code_only:
        return out
    return {k: strip_comments(v, language="tsx") for k, v in out.items()}


def test_no_screen_reports_a_progress_number_it_did_not_measure():
    """Both were literals: value={45} while generating, value={60} while uploading."""
    offenders = []
    for where, text in sources(code_only=True).items():
        for value in FAKE_PROGRESS.findall(text):
            offenders.append(f"{where}: value={{{value}}}")
    assert not offenders, f"fake progress: {offenders}"


def test_the_progress_component_is_gone_rather_than_merely_unused():
    """Delete the old path the day the new one lands. A component left in the tree is
    the one the next person reaches for."""
    assert not (FRONTEND / "components" / "ui" / "progress.tsx").exists(), (
        "ui/progress.tsx still exists, so the fake bar is one import away"
    )
    for where, text in sources(code_only=True).items():
        assert "ui/progress" not in text, f"{where} still imports it"


def test_the_wait_tells_the_customer_they_can_leave():
    """The single most useful fact to someone watching a page that cannot be hurried,
    and it is true: the delivery email is sent by the pipeline, not by this page."""
    text = GALLERY.read_text(encoding="utf-8")
    assert "cerrar esta página" in text, "the wait never says the page can be closed"
    assert "correo" in text, "the wait never says the link also arrives by email"


def test_the_wait_shows_the_shape_of_what_is_coming():
    """383px of empty canvas under a sentence is not a designed wait. Four frames say
    what will land there without claiming to know when."""
    text = GALLERY.read_text(encoding="utf-8")
    assert "FRAMES" in text, "no placeholder frames while generating"
    assert re.search(r"FRAMES\s*=\s*\[[^\]]*\]", text), "FRAMES is not a literal list"
    frames = re.search(r"FRAMES\s*=\s*\[([^\]]*)\]", text).group(1)
    assert len([x for x in frames.split(",") if x.strip()]) == 4, "four photos, four frames"


def test_every_terminal_state_offers_something_to_do_next():
    """A dead end with 400px of blank under it is where a customer gives up. Each of the
    three terminal states must carry a link, not just an apology."""
    text = GALLERY.read_text(encoding="utf-8")
    for state in ("refund_pending", "refunded", "notfound"):
        block = re.search(rf'status === "{state}" \? \((.*?)\n\s*\) : null', text, re.S)
        assert block, f"no block for {state}"
        assert "href=" in block.group(1), f"{state} leaves the customer with nowhere to go"


def test_the_recovery_page_says_what_will_arrive_and_what_to_do_if_it_does_not():
    """295px of dead canvas under a one-line form. The person here has already paid and
    lost the link; 'revisa el spam' is the answer 90% of them need."""
    text = RECOVER.read_text(encoding="utf-8")
    assert "spam" in text.lower()
    assert "hola@studioface.app" in text, "no way to reach a human from the recovery page"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
