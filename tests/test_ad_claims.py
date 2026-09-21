"""Task 24, closed out by task 33. The claims test: every number or duration promised
in an ad group's headlines or descriptions (19,99; 4; 1 a 4; 7 días; dos minutos) must
actually appear in the rendered text of that group's final_url page in the built
export — an ad that promises "19,99 €" must not point at a page that says "29,99 €".

Hermetic, per docs/DESIGN.md/HANDOFF's own precedent for scripts/design_audit.py: each
fixture is staged into its OWN tmp export directory rather than read from the live
frontend/out, so a twin (page missing a claim) can be proven without touching a real,
currently-serving, real-payments page.

test_the_real_ad_groups_claims_do_land_on_their_pages used to be marked xfail(strict=
False): task 23's ad-landing pages showed only 3 of the 5 shared FAQ questions
(frontend/src/content/ad-pages.ts, SHARED_FAQ), and the retention question ("¿Qué pasa
con mis fotos?" -> "... se borran a los 7 días ...") was not one of them, so the ad
copy's "Tus fotos se borran a los 7 días" claim was true of the product (stated on the
home page, in the delivery email, and in /legal/privacidad/) but not visible on
/foto-cv/ or /foto-linkedin/ themselves. Task 33 added that fourth question to
SHARED_FAQ — from the shared content, not retyped — so the claim now lands on both
pages and this test is a real, passing check, not an expected failure.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_ad_claims import (  # noqa: E402
    extract_claims,
    find_claim_violations,
    group_claims,
    page_path_for,
    visible_text,
)

RSA_JSON = ROOT / "docs" / "ads" / "rsa.json"
EXPORT = ROOT / "frontend" / "out"
CLAIMS_SCRIPT = ROOT / "scripts" / "check_ad_claims.py"

PAGE_TEMPLATE = """<!doctype html><html><head>
<script>window.__DATA__={{"build":12345}}</script>
</head><body>
<h1>Tu foto para el currículum, en dos minutos</h1>
<p>Sube de 1 a 4 selfies y prueba gratis.</p>
<p>{price} € IVA incluido, pago único.</p>
<p>Tus fotos se borran a los 7 días.</p>
</body></html>"""


def _group(**overrides) -> dict:
    base = {
        "name": "cv",
        "final_url": "https://studioface.app/foto-cv/",
        "headlines": ["Foto de CV en dos minutos", "4 fotos para CV por 19,99 €"],
        "descriptions": [
            "Sube de 1 a 4 selfies y mira una prueba gratis.",
            "Tus fotos se borran a los 7 días. Devolución automática.",
        ],
    }
    base.update(overrides)
    return base


def _stage_export(tmp_path: Path, slug: str, price: str = "19,99") -> Path:
    export_dir = tmp_path / "out"
    page_dir = export_dir / slug
    page_dir.mkdir(parents=True)
    (page_dir / "index.html").write_text(PAGE_TEMPLATE.format(price=price), encoding="utf-8")
    return export_dir


# --------------------------------------------------------------------- extract_claims


def test_extract_claims_finds_the_price():
    assert "19,99" in extract_claims("4 fotos para CV por 19,99 €")


def test_extract_claims_finds_the_range():
    assert "1 a 4" in extract_claims("Sube de 1 a 4 selfies y mira una prueba gratis.")


def test_extract_claims_finds_the_digit_duration():
    assert "7 días" in extract_claims("Tus fotos se borran a los 7 días.")


def test_extract_claims_finds_the_word_duration():
    assert "dos minutos" in extract_claims("Foto de CV en dos minutos")


def test_extract_claims_finds_a_bare_number():
    assert "4" in extract_claims("4 fotos para CV por 19,99 €")


def test_extract_claims_has_no_duplicates():
    claims = extract_claims("19,99 € y otra vez 19,99 €")
    assert claims.count("19,99") == 1


# ------------------------------------------------------------- find_claim_violations


def test_a_group_with_every_claim_on_its_page_has_no_violations(tmp_path):
    export_dir = _stage_export(tmp_path, "foto-cv", price="19,99")
    data = {"ad_groups": [_group()]}
    assert find_claim_violations(data, export_dir) == []


def test_the_twin_a_page_that_says_29_99_is_refused(tmp_path):
    """The twin the brief asks for: the ad says 19,99, the page says 29,99."""
    export_dir = _stage_export(tmp_path, "foto-cv", price="29,99")
    data = {"ad_groups": [_group()]}
    violations = find_claim_violations(data, export_dir)
    assert violations, "a page saying 29,99 instead of 19,99 must be refused"
    assert any("19,99" in v for v in violations)


def test_a_missing_page_is_reported_not_crashed(tmp_path):
    export_dir = tmp_path / "out"
    export_dir.mkdir()
    data = {"ad_groups": [_group()]}
    violations = find_claim_violations(data, export_dir)
    assert violations
    assert any("foto-cv" in v for v in violations)


def test_only_headlines_and_descriptions_are_checked_not_keywords():
    """keywords_exact and negative_keywords_phrase are not ad copy shown to a visitor —
    a stray number there must not be treated as a claim the page has to back up."""
    group = _group(keywords_exact=["mejor foto 2026"])
    claims = []
    for field in ("headlines", "descriptions"):
        for text in group[field]:
            claims.extend(extract_claims(text))
    assert "2026" not in claims


def test_two_groups_are_checked_against_their_own_final_url_not_the_others(tmp_path):
    export_dir = tmp_path / "out"
    (export_dir / "foto-cv").mkdir(parents=True)
    (export_dir / "foto-cv" / "index.html").write_text(
        PAGE_TEMPLATE.format(price="19,99"), encoding="utf-8"
    )
    (export_dir / "foto-linkedin").mkdir(parents=True)
    (export_dir / "foto-linkedin" / "index.html").write_text(
        PAGE_TEMPLATE.format(price="29,99"), encoding="utf-8"
    )
    data = {
        "ad_groups": [
            _group(name="cv", final_url="https://studioface.app/foto-cv/"),
            _group(name="linkedin", final_url="https://studioface.app/foto-linkedin/"),
        ]
    }
    violations = find_claim_violations(data, export_dir)
    assert not any(v.startswith("cv:") for v in violations)
    assert any(v.startswith("linkedin:") for v in violations)


# ------------------------------------------------------------------------------- CLI


def test_cli_exits_0_on_a_clean_export(tmp_path):
    export_dir = _stage_export(tmp_path, "foto-cv", price="19,99")
    rsa_path = tmp_path / "rsa.json"
    rsa_path.write_text(json.dumps({"ad_groups": [_group()]}), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(CLAIMS_SCRIPT), str(rsa_path), str(export_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_cli_exits_1_on_the_29_99_twin(tmp_path):
    export_dir = _stage_export(tmp_path, "foto-cv", price="29,99")
    rsa_path = tmp_path / "rsa.json"
    rsa_path.write_text(json.dumps({"ad_groups": [_group()]}), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(CLAIMS_SCRIPT), str(rsa_path), str(export_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "FAIL" in result.stdout


# --------------------------------------------------------------------- real export

_export_reason = "no frontend/out — run `npm run build` in frontend/. CI builds before this runs."


@pytest.mark.skipif(not EXPORT.is_dir(), reason=_export_reason)
def test_the_real_ad_groups_claims_do_land_on_their_pages():
    """Task 33 closes the gap that kept this xfail: the retention question is now on
    both ad-landing pages (frontend/src/content/ad-pages.ts, SHARED_FAQ), so every
    number and duration either ad group promises is on the page its ad points to."""
    data = json.loads(RSA_JSON.read_text(encoding="utf-8"))
    violations = find_claim_violations(data, EXPORT)
    assert violations == [], "\n".join(violations)


def _real_claim_cases() -> list[tuple[str, str]]:
    """(group name, claim) for every number/duration in the real docs/ads/rsa.json —
    one case per claim, so a single missing claim on a real page fails by name instead
    of hiding inside one aggregate assertion."""
    data = json.loads(RSA_JSON.read_text(encoding="utf-8"))
    return [(group["name"], claim) for group in data["ad_groups"] for claim in group_claims(group)]


@pytest.mark.skipif(not EXPORT.is_dir(), reason=_export_reason)
@pytest.mark.parametrize("group_name,claim", _real_claim_cases())
def test_every_real_claim_appears_on_its_own_groups_page(group_name, claim):
    """The case that must get through: every claim docs/ads/rsa.json actually makes,
    checked one at a time against the visible text of that same group's own rendered
    page — not a marker in the source, the text a visitor would actually read."""
    data = json.loads(RSA_JSON.read_text(encoding="utf-8"))
    group = next(g for g in data["ad_groups"] if g["name"] == group_name)
    page_path = page_path_for(EXPORT, group["final_url"])
    assert page_path.is_file(), f"{page_path} missing — run `npm run build` in frontend/"
    text = visible_text(page_path.read_text(encoding="utf-8"))
    assert claim in text, f"{group_name}: claim {claim!r} not found on {page_path}"


def test_the_twin_a_real_claim_missing_from_its_own_real_page_is_refused(tmp_path):
    """The case that must be refused, proven against the REAL rsa.json data (not the
    synthetic _group() fixture above): stage a page carrying every real claim the 'cv'
    group makes except the retention duration, and confirm the checker names exactly
    that missing claim rather than passing silently."""
    data = json.loads(RSA_JSON.read_text(encoding="utf-8"))
    group = next(g for g in data["ad_groups"] if g["name"] == "cv")
    claims = group_claims(group)
    assert "7 días" in claims, "fixture drifted from docs/ads/rsa.json — no '7 días' claim to drop"
    claims_without_retention = [c for c in claims if c != "7 días"]

    export_dir = tmp_path / "out"
    page_dir = export_dir / "foto-cv"
    page_dir.mkdir(parents=True)
    page_dir.joinpath("index.html").write_text(
        "<!doctype html><html><body><p>"
        + " ".join(claims_without_retention)
        + "</p></body></html>",
        encoding="utf-8",
    )

    violations = find_claim_violations({"ad_groups": [group]}, export_dir)
    assert any("7 días" in v for v in violations), violations
    for other_claim in claims_without_retention:
        assert not any(f"'{other_claim}'" in v for v in violations), (
            f"{other_claim!r} was staged on the page and must not be reported missing"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
