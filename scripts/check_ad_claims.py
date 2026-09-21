"""Validate that every number or duration an ad group promises actually appears on the
page the ad points to — an ad that says "19,99 €" must not point at a page that says
"29,99 €".

Reads docs/ads/rsa.json's ad_groups (task 24: cv, linkedin). For each group, extracts
every "claim" — a price (19,99), a range (1 a 4), a digit duration (7 días) or a word
duration (dos minutos) — from its headlines and descriptions only (not keywords, not
negatives: those are never shown to a visitor), and checks that each claim is a
substring of the VISIBLE, rendered text of that group's final_url page in the built
export (frontend/out by default) — script and style tag contents stripped first, so a
build hash such as "...0cz1d0mv5g_q7.js" cannot masquerade as a "7 días" match.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

WORD_NUMBERS = "un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez"
DURATION_UNITS = r"minutos?|horas?|d[ií]as?|semanas?|meses?|a[nñ]os?"

_DECIMAL = re.compile(r"\d+,\d+")
_RANGE = re.compile(r"\b\d+ a \d+\b")
_DIGIT_DURATION = re.compile(rf"\b\d+\s+(?:{DURATION_UNITS})\b", re.IGNORECASE)
_WORD_DURATION = re.compile(rf"\b(?:{WORD_NUMBERS})\s+(?:{DURATION_UNITS})\b", re.IGNORECASE)
_BARE_NUMBER = re.compile(r"\b\d+\b")

_SCRIPT_OR_STYLE = re.compile(r"<(script|style)[\s\S]*?</\1>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


def extract_claims(text: str) -> list[str]:
    """Every price, range, and duration mentioned in `text`, in order, deduplicated."""
    claims: list[str] = []
    working = text
    for pattern in (_DECIMAL, _RANGE, _DIGIT_DURATION, _WORD_DURATION):
        for match in pattern.finditer(working):
            claims.append(match.group())
        working = pattern.sub(" ", working)
    for match in _BARE_NUMBER.finditer(working):
        claims.append(match.group())
    seen: set[str] = set()
    ordered: list[str] = []
    for claim in claims:
        if claim not in seen:
            seen.add(claim)
            ordered.append(claim)
    return ordered


def visible_text(html: str) -> str:
    """Human-visible text: script/style bodies removed, then every tag stripped."""
    html = _SCRIPT_OR_STYLE.sub(" ", html)
    text = _TAG.sub(" ", html)
    return _WHITESPACE.sub(" ", text).strip()


def group_claims(group: dict) -> list[str]:
    claims: list[str] = []
    seen: set[str] = set()
    for field in ("headlines", "descriptions"):
        for text in group.get(field, []):
            for claim in extract_claims(text):
                if claim not in seen:
                    seen.add(claim)
                    claims.append(claim)
    return claims


def page_path_for(export_dir: Path, final_url: str) -> Path:
    slug = final_url.rstrip("/").rsplit("/", 1)[-1]
    return export_dir / slug / "index.html"


def find_claim_violations(data: dict, export_dir: Path) -> list[str]:
    violations: list[str] = []
    for group in data.get("ad_groups", []):
        name = group.get("name", "?")
        page_path = page_path_for(export_dir, group.get("final_url", ""))
        if not page_path.is_file():
            violations.append(f"{name}: page not found in the export: {page_path}")
            continue
        text = visible_text(page_path.read_text(encoding="utf-8"))
        for claim in group_claims(group):
            if claim not in text:
                violations.append(f"{name}: claim '{claim}' not found on {page_path}")
    return violations


def main(argv: list[str]) -> int:
    rsa_path = Path(argv[1]) if len(argv) > 1 else Path("docs/ads/rsa.json")
    export_dir = Path(argv[2]) if len(argv) > 2 else Path("frontend/out")
    data = json.loads(rsa_path.read_text(encoding="utf-8"))
    violations = find_claim_violations(data, export_dir)
    for line in violations:
        print(line)
    print("FAIL" if violations else "OK: every claim appears on its page")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
