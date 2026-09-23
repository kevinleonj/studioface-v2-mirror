"""Task 96b: the privacy page covers the optional "¿Cómo nos encontraste?" answer.

Task 95e started storing that answer on the order. It is personal data tied to a buyer,
so "Qué datos tratamos" says what it is (one of the fixed options), why (knowing which
channels bring customers), on what basis (consent: it is optional and skipping it changes
nothing) and for how long (the same as the order).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_scan import strip_comments  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "frontend" / "src" / "app" / "legal" / "privacidad" / "page.tsx"
SENTENCE = (
    "Si quieres, al recibir tus fotos puedes decirnos cómo nos encontraste, eligiendo una de "
    "las opciones que te mostramos. Lo guardamos junto a tu pedido para saber qué canales nos "
    "traen clientes. Es opcional: la base jurídica es tu consentimiento, y no responder no "
    "cambia nada. Se conserva el mismo tiempo que el pedido."
)


def _section(title: str) -> str:
    code = strip_comments(PAGE.read_text(encoding="utf-8"), language="tsx")
    start = code.index(f"<H2>{title}</H2>")
    return " ".join(code[start : code.index("<H2>", start + 1)].split())


def test_what_we_process_names_the_found_us_answer_with_purpose_basis_and_retention():
    assert SENTENCE in _section("Qué datos tratamos")


def test_it_sits_in_what_we_process_and_nowhere_else():
    """Must be refused: the same sentence dropped into another section."""
    code = " ".join(strip_comments(PAGE.read_text(encoding="utf-8"), language="tsx").split())
    assert code.count("cómo nos encontraste") == 1


def test_the_retention_sentences_stay_word_for_word():
    text = " ".join(PAGE.read_text(encoding="utf-8").split())
    assert "Las fotografías que subes se borran automáticamente a los 7 días." in text
    kept = "Las imágenes generadas se conservan 1 año para que puedas volver a descargarlas."
    assert kept in text
