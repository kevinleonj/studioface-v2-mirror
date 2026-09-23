"""Task 24. docs/ads/rsa.json now holds TWO ad groups (cv, linkedin), each with its own
headlines, descriptions and path. scripts/check_ad_copy.py must validate every group
independently against Google's Responsive Search Ad limits: 30 characters per headline
(<=15), 90 per description (<=4), 15 per path (<=2), no duplicates inside a group.

Every guard needs one case that must be refused and one that must get through — the
31-character headline is the refused twin; a 30-character headline (the limit itself,
not over it) is the twin that must get through.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_ad_copy import find_violations  # noqa: E402

RSA_JSON = ROOT / "docs" / "ads" / "rsa.json"
CHECK_SCRIPT = ROOT / "scripts" / "check_ad_copy.py"


def _group(**overrides) -> dict:
    base = {
        "name": "cv",
        "final_url": "https://studioface.app/foto-cv/",
        "path": ["foto-cv", "gratis"],
        "headlines": ["Foto para tu CV con IA"],
        "descriptions": ["Sube de 1 a 4 selfies y mira una prueba gratis, sin registro."],
    }
    base.update(overrides)
    return base


def test_a_clean_group_has_no_violations():
    data = {"ad_groups": [_group()]}
    assert find_violations(data) == []


def test_two_clean_groups_have_no_violations():
    data = {
        "ad_groups": [
            _group(name="cv"),
            _group(name="linkedin", final_url="https://studioface.app/foto-linkedin/"),
        ]
    }
    assert find_violations(data) == []


def test_a_31_character_headline_is_refused():
    """The twin that must be refused."""
    headline = "1234567890123456789012345678901"  # 31 characters, one over the limit
    assert len(headline) == 31
    data = {"ad_groups": [_group(headlines=[headline])]}
    violations = find_violations(data)
    assert violations, "a 31-character headline must be reported as a violation"
    assert any("headlines" in v and "cv" in v for v in violations)


def test_a_30_character_headline_gets_through():
    """The twin that must get through: exactly the limit, not over it."""
    headline = "123456789012345678901234567890"  # exactly 30 characters
    assert len(headline) == 30
    data = {"ad_groups": [_group(headlines=[headline])]}
    assert find_violations(data) == []


def test_a_91_character_description_is_refused():
    description = "a" * 91
    data = {"ad_groups": [_group(descriptions=[description])]}
    violations = find_violations(data)
    assert any("descriptions" in v for v in violations)


def test_a_16_character_path_segment_is_refused():
    data = {"ad_groups": [_group(path=["a" * 16, "gratis"])]}
    violations = find_violations(data)
    assert any("path" in v for v in violations)


def test_a_duplicate_headline_inside_a_group_is_refused():
    data = {"ad_groups": [_group(headlines=["Mismo texto", "Mismo texto"])]}
    violations = find_violations(data)
    assert any("duplicate" in v for v in violations)


def test_the_same_headline_text_reused_across_two_groups_is_not_a_duplicate():
    """Duplicates are checked INSIDE a group only — the brief's two groups intentionally
    reuse several identical headlines ("Prueba gratis, sin registro")."""
    data = {
        "ad_groups": [
            _group(name="cv", headlines=["Prueba gratis, sin registro"]),
            _group(name="linkedin", headlines=["Prueba gratis, sin registro"]),
        ]
    }
    assert find_violations(data) == []


def test_too_many_headlines_in_one_group_is_refused():
    data = {"ad_groups": [_group(headlines=[f"Titulo {i}" for i in range(16)])]}
    violations = find_violations(data)
    assert any("headlines" in v and "16 items" in v for v in violations)


def test_a_violation_in_one_group_does_not_hide_a_violation_in_the_other():
    data = {
        "ad_groups": [
            _group(name="cv", headlines=["a" * 31]),
            _group(name="linkedin", descriptions=["b" * 91]),
        ]
    }
    violations = find_violations(data)
    assert any("cv" in v and "headlines" in v for v in violations)
    assert any("linkedin" in v and "descriptions" in v for v in violations)


def test_the_real_rsa_json_has_no_violations():
    data = json.loads(RSA_JSON.read_text(encoding="utf-8"))
    violations = find_violations(data)
    assert violations == [], "\n".join(violations)


def test_the_real_rsa_json_has_exactly_two_ad_groups():
    data = json.loads(RSA_JSON.read_text(encoding="utf-8"))
    names = [g["name"] for g in data["ad_groups"]]
    assert names == ["cv", "linkedin"]


def test_cli_exits_0_on_a_clean_file(tmp_path):
    path = tmp_path / "clean.json"
    path.write_text(json.dumps({"ad_groups": [_group()]}), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(CHECK_SCRIPT), str(path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_cli_exits_1_on_a_31_character_headline():
    """The refused twin, exercised through the real CLI entry point, not just the
    function underneath it."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "bad.json"
        path.write_text(json.dumps({"ad_groups": [_group(headlines=["a" * 31])]}), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(CHECK_SCRIPT), str(path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "FAIL" in result.stdout


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


# ------------------------------------------------ task 95j: a second ad in an ad group

RSA_JSON = ROOT / "docs" / "ads" / "rsa.json"
CV_B_NEW_HEADLINES = [
    "Foto CV profesional con IA",
    "Foto para currículum con IA",
    "Foto de currículum: 19,99 €",
]
CV_B_DESCRIPTIONS = [
    "Sube de 1 a 4 selfies y recibe cuatro retratos listos para tu currículum.",
    "Luz, fondo y ropa de estudio. Tu cara no cambia.",
    "Tus selfies se borran a los 7 días. Sin registro y pago único.",
]


def _extra(**overrides) -> dict:
    base = {
        "name": "cv-b",
        "path": ["foto-cv", "gratis"],
        "headlines": ["Foto CV profesional con IA"],
        "descriptions": ["Luz, fondo y ropa de estudio. Tu cara no cambia."],
    }
    base.update(overrides)
    return base


def test_an_additional_ad_over_the_headline_limit_is_refused():
    too_many = [f"Titular numero {i}" for i in range(16)]
    data = {"ad_groups": [_group(additional_ads=[_extra(headlines=too_many)])]}
    assert "cv/cv-b/headlines: 16 items, limit 15" in find_violations(data)


def test_an_additional_ad_with_a_duplicate_headline_is_refused():
    twice = ["Foto CV profesional con IA", "Foto CV profesional con IA"]
    data = {"ad_groups": [_group(additional_ads=[_extra(headlines=twice)])]}
    assert "cv/cv-b/headlines: duplicate entries" in find_violations(data)


def test_a_clean_additional_ad_passes():
    assert find_violations({"ad_groups": [_group(additional_ads=[_extra()])]}) == []


def test_the_real_cv_group_carries_cv_b_as_specified():
    data = json.loads(RSA_JSON.read_text(encoding="utf-8"))
    cv = next(g for g in data["ad_groups"] if g["name"] == "cv")
    (ad,) = cv["additional_ads"]
    assert ad["name"] == "cv-b"
    assert ad["path"] == ["foto-cv", "gratis"]
    assert ad["headlines"] == cv["headlines"] + CV_B_NEW_HEADLINES
    assert ad["descriptions"] == CV_B_DESCRIPTIONS
    assert "final_url" not in ad, "cv-b uses its group's final_url, /foto-cv/"
