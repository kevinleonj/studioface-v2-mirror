"""The landing budget, and the attribute that was not doing its job.

Measured 18 Sep 2026 on a served copy of the export, gzipped, at 390x844, with NO
scrolling at all:

    transfer total   465.9 KB   (17 requests)
      images         213.5 KB
      js             156.8 KB
      fonts           82.8 KB
      css              6.6 KB
      html + other     6.3 KB

Over the 400 KB budget, and the reason is that `loading="lazy"` deferred nothing. All
six photographs were fetched before the visitor scrolled a pixel; scrolling to the very
end of a 3763px page then added 0.0 KB, which is the proof. Chromium's lazy-load
distance-from-viewport on a fast connection is large enough to swallow the whole page,
so the attribute is a hint that this page never benefits from.

Four of those six are the "Más muestras" pairs, 141.7 KB of photographs of two people a
visitor has not asked to see yet. They are now held back by an IntersectionObserver,
which is a mechanism rather than a hint, with a <noscript> fallback so a visitor without
JavaScript still gets them.

LCP: the hero photograph, not the H1. See docs/DESIGN.md — that is a deliberate change
and the constraint it replaces was a proxy for the thing that actually matters.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "frontend" / "out"
DESIGN = ROOT / "docs" / "DESIGN.md"
HERO_KEY = "mujer-40"

pytestmark = pytest.mark.skipif(
    not (EXPORT / "index.html").exists(), reason="no build; CI builds first"
)


def markup() -> str:
    """The rendered page, without the RSC flight payload, and without <noscript> —
    noscript markup is not fetched by a browser that runs JavaScript, so counting it
    would fail a page that is doing the right thing."""
    html = (EXPORT / "index.html").read_text(encoding="utf-8", errors="ignore")
    body = html[: html.index("</footer>")]
    return re.sub(r"<noscript>.*?</noscript>", "", body, flags=re.S)


def test_the_hero_photograph_is_in_the_initial_html():
    """It is the LCP element. Deferring it behind an observer would cost exactly what
    deferring the others saves, in the one place the page cannot afford it."""
    assert f"{HERO_KEY}-despues" in markup(), "the hero photograph is no longer server-rendered"


def test_the_gallery_photographs_are_not_fetched_before_anybody_asks():
    """141.7 KB of two people the visitor has not scrolled to yet, on a phone, on a
    first visit. The old `loading="lazy"` fetched every one of them anyway."""
    body = markup()
    late = [k for k in ("hombre-30", "hombre-25") if f"{k}-despues" in body]
    assert not late, f"gallery photographs still in the first payload: {late}"


def test_a_visitor_without_javascript_still_gets_them():
    """The deferral is an observer, so without JavaScript it never fires. A page that
    silently drops two thirds of its evidence for those visitors has not solved the
    problem, it has moved it somewhere nobody measures."""
    html = (EXPORT / "index.html").read_text(encoding="utf-8", errors="ignore")
    blocks = re.findall(r"<noscript>(.*?)</noscript>", html, re.S)
    assert blocks, "no <noscript> fallback at all"
    joined = "".join(blocks)
    for key in ("hombre-30", "hombre-25"):
        assert f"{key}-despues" in joined, f"{key} is unreachable without JavaScript"
    assert "generada con IA" in joined, "the fallback drops the AI disclosure"


def test_the_budget_is_written_down_with_the_measurement_beside_it():
    """A budget with no measured number next to it is an aspiration."""
    doc = DESIGN.read_text(encoding="utf-8")
    block = re.search(r"### Budgets, measured(.*?)(?=\n## |\n# )", doc, re.S)
    assert block, "no measured budget table in DESIGN.md"
    rows = re.findall(r"^\| ([^|]+) \| ([^|]+) \| ([^|]+) \|", block.group(1), re.M)
    rows = [r for r in rows if "---" not in r[0] and "budget" not in r[0].lower()]
    assert len(rows) >= 4, f"only {len(rows)} budgets recorded"
    for name, budget, measured in rows:
        # Both columns, and both must carry a number. A row with no measurement is an
        # aspiration; a row whose limit reads "no limit set" is a number nobody can
        # fail, which is the same thing wearing a table. Two rows said exactly that
        # until this assertion existed.
        assert re.search(r"\d", budget), f"{name.strip()}: no numeric limit"
        assert re.search(r"\d", measured), f"{name.strip()}: no measured value"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
