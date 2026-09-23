"""Task 96a: the site names the trader exactly as registered with the Agencia Tributaria.

Kevin's Modelo 036, filed 13-09-2026: titular Kevin Daniel León Jouvin (registered as
LEON JOUVIN KEVIN DANIEL), NIF Z3714124-C, domicilio Calle de Diego de León 13, 7º A,
28006 Madrid, and no nombre comercial. The site said "limeralda" at "Maria de Molina 31",
which is neither the registered name nor the registered address. LSSI-CE Art. 10 requires
the provider's real name and address, so every page (through the shared footer), every
legal page, and every customer email now carries the registered identity.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

sys.path.insert(0, str(ROOT / "tests"))

import go_live  # noqa: E402
from source_scan import strip_comments  # noqa: E402

from app import emails  # noqa: E402

EXPORT = ROOT / "frontend" / "out"
SRC = ROOT / "frontend" / "src"
TITULAR = (
    "Titular: Kevin Daniel León Jouvin. NIF: Z3714124-C. "
    "Domicilio: Calle de Diego de León 13, 7º A, 28006 Madrid."
)
NAME = "Kevin Daniel León Jouvin"
OLD = ("limeralda", "Molina")
SOURCES = (
    SRC / "app" / "legal" / "aviso-legal" / "page.tsx",
    SRC / "app" / "legal" / "privacidad" / "page.tsx",
    SRC / "app" / "legal" / "terminos" / "page.tsx",
    SRC / "app" / "sobre-nosotros" / "page.tsx",
    SRC / "components" / "site-footer.tsx",
)
LEGAL_PAGES = ("aviso-legal", "privacidad", "terminos", "cookies")
BUILT = EXPORT.is_dir()


def _flat(text: str) -> str:
    return " ".join(text.split())


def old_identity_in(text: str) -> list[str]:
    return [word for word in OLD if word.lower() in text.lower()]


def test_every_legal_page_and_the_footer_carry_the_exact_titular_line():
    """In the code, comments stripped: a comment quoting the line must not pass for it."""
    for path in SOURCES:
        code = strip_comments(path.read_text(encoding="utf-8"), language="tsx")
        assert TITULAR in _flat(code), path


def test_no_source_still_names_the_old_identity():
    """Raw text on purpose, stricter than the check above: not even a comment."""
    for path in SOURCES:
        assert old_identity_in(path.read_text(encoding="utf-8")) == [], path


def test_the_scan_catches_the_old_identity():
    """Meta-test: the check above does fail on the old line."""
    assert old_identity_in("Titular: limeralda. Domicilio: Maria de Molina 31") != []


def test_both_customer_emails_carry_the_registered_identity():
    assert (
        NAME in emails.TRADER and "Calle de Diego de León 13, 7º A, 28006 Madrid" in emails.TRADER
    )
    assert old_identity_in(emails.TRADER) == []


@pytest.mark.skipif(not BUILT, reason="no frontend/out; run the build")
def test_no_built_page_names_the_old_identity():
    offenders = [
        str(page.relative_to(EXPORT))
        for page in EXPORT.rglob("*.html")
        if old_identity_in(page.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert offenders == []


@pytest.mark.skipif(not BUILT, reason="no frontend/out; run the build")
def test_every_built_legal_page_shows_the_titular_line():
    for slug in LEGAL_PAGES:
        html = (EXPORT / "legal" / slug / "index.html").read_text(encoding="utf-8")
        assert TITULAR in _flat(html.replace("<!-- -->", "")), slug


def test_go_live_refuses_a_landing_page_without_the_registered_name(tmp_path, monkeypatch):
    """Must be refused: the NIF alone passed before, even under the wrong name."""
    (tmp_path / "index.html").write_text("<p>limeralda, NIF Z3714124-C</p>", encoding="utf-8")
    monkeypatch.setattr(go_live, "EXPORT", tmp_path)
    lssi = next(c for c in go_live.check_export() if "trader identity" in c.name)
    assert lssi.mark == go_live.NO


def test_go_live_accepts_the_registered_name_and_nif(tmp_path, monkeypatch):
    """Must get through."""
    (tmp_path / "index.html").write_text(f"<p>{TITULAR}</p>", encoding="utf-8")
    monkeypatch.setattr(go_live, "EXPORT", tmp_path)
    lssi = next(c for c in go_live.check_export() if "trader identity" in c.name)
    assert lssi.mark == go_live.OK
