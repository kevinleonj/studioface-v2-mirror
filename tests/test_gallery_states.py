"""F4/O4: the gallery told every visitor their photographs were being made.

The component rendered the same block for `loading` and for `working`:

    {status === "loading" || status === "working" ? <Waiting /> : null}

`loading` is the state before the first poll answers. So a customer whose order was
already delivered - which is everybody arriving from the delivery email - read

    "Estamos revelando tus cuatro fotos. Suele tardar unos dos minutos"

for about two seconds, and then the photographs appeared. P10: the first paint must
never assert something that may be false.

Also here, because both need the same layout file: `/g/` and `/recuperar/` carried the
generic site title and no robots tag. A gallery URL contains an order id and a delivery
token. It is unguessable rather than secret, and one pasted into a public thread is all
a crawler needs.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from source_scan import strip_comments  # noqa: E402

EXPORT = ROOT / "frontend" / "out"
PAGE = ROOT / "frontend" / "src" / "app" / "g" / "page.tsx"

pytestmark = pytest.mark.skipif(
    not (EXPORT / "index.html").exists(), reason="no build; CI builds first"
)


def source() -> str:
    return strip_comments(PAGE.read_text(encoding="utf-8"), language="tsx")


def html(route: str) -> str:
    return (EXPORT / route / "index.html").read_text(encoding="utf-8", errors="ignore")


def test_loading_and_working_are_no_longer_the_same_branch():
    """O4 itself."""
    src = source()
    assert '"loading" || status === "working"' not in src, "the two states still share a branch"
    assert 'status === "loading" ? <Loading />' in src
    assert 'status === "working" ? <Waiting />' in src


def test_the_loading_state_claims_nothing():
    """It may be false, so it is not said. `Loading` renders the frames and no prose."""
    src = source()
    block = src[src.index("function Loading()") :]
    block = block[: block.index("function Waiting()")]
    assert "revelando" not in block, "the silent state still promises a reveal"
    assert "minutos" not in block, "the silent state still promises a time"
    assert "<Frames" in block, "the silent state does not reserve the four boxes"


def test_the_working_state_keeps_the_sentence_it_always_had():
    """Held-out. Splitting the states must not delete the true one: somebody whose
    order really is generating still needs to be told what is happening."""
    src = source()
    block = src[src.index("function Waiting()") :]
    assert "Estamos revelando tus cuatro fotos" in block
    assert "esta" in block and "actualiza sola" in block


def test_both_waiting_states_reserve_the_same_four_boxes():
    """So the layout does not jump between them, or when the photographs arrive."""
    src = source()
    assert "function Frames(" in src, "the frames are not shared"
    assert src.count("aspect-[4/5]") >= 2, "the reserved box is not 4:5"


def test_each_delivered_image_fades_in_on_its_own_load():
    """It used to animate on render with a staggered delay, which is a timer pretending
    to know when a picture arrived."""
    src = source()
    assert "onLoad={() => setLoaded(" in src, "nothing waits for the image to decode"
    assert "loaded[i] ?" in src, "the fade is not keyed to this image"
    assert "animationDelay" not in src, "the staggered timer is still there"


@pytest.mark.parametrize("route", ["g", "recuperar"])
def test_the_page_is_not_indexable(route):
    """A gallery URL carries an order id and a delivery token."""
    found = re.search(r'<meta name="robots" content="([^"]+)"', html(route))
    assert found, f"/{route}/ has no robots tag"
    assert "noindex" in found.group(1) and "nofollow" in found.group(1), found.group(1)


@pytest.mark.parametrize(
    ("route", "title"),
    [("g", "Tus fotos | StudioFace"), ("recuperar", "Recuperar mis fotos | StudioFace")],
)
def test_the_page_says_which_page_it_is(route, title):
    found = re.search(r"<title>(.*?)</title>", html(route))
    assert found and found.group(1) == title, found and found.group(1)


def test_the_landing_page_is_still_indexable():
    """Held-out check, and the expensive mistake: a robots tag applied at the layout
    above these two would quietly deindex the thing we are buying ads for."""
    found = re.search(r'<meta name="robots" content="([^"]+)"', html(""))
    assert not found or "noindex" not in found.group(1), (
        f"the landing page is noindex: {found and found.group(1)}"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
