"""Task 95k: docs/ads/ records the Google Ads account as it is live, not a build sheet.

On 23 September 2026 the campaign was built through the Google Ads API (Windsor), not by
hand from CAMPAIGN.md's field-by-field sheet and checklist. The sheet no longer matched
reality (it said 40 negatives; the account has 41, with "gratis"), so CAMPAIGN.md now
records the live state and rsa.json's negatives match the account.

The kill rule must not move while this happens: the "Pre-registered test" section is
pinned byte for byte, as it stood at e2ed132 before this task.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RSA = ROOT / "docs" / "ads" / "rsa.json"
CAMPAIGN = ROOT / "docs" / "ads" / "CAMPAIGN.md"
KILL_RULE_SHA256 = "32ba4b06b1cad04e7ecabf9a1265fab4957bc9035fd03644189fe0e8fe8ea385"

SITELINKS = {
    "Foto para LinkedIn": "https://studioface.app/foto-linkedin/",
    "Cómo funciona": "https://studioface.app/",
    "Condiciones de compra": "https://studioface.app/legal/terminos/",
    "Borrado en 7 días": "https://studioface.app/legal/privacidad/",
}
CALLOUTS = ["Prueba gratis", "Sin registro", "Pago único, IVA incluido", "Listo en dos minutos"]


def _rsa() -> dict:
    return json.loads(RSA.read_text(encoding="utf-8"))


def _campaign() -> str:
    return CAMPAIGN.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_the_negatives_are_the_live_41_including_gratis():
    negatives = _rsa()["negative_keywords_phrase"]
    assert len(negatives) == 41
    assert "gratis" in negatives
    assert len(set(negatives)) == 41, "a duplicate negative"


def test_rsa_json_bidding_is_the_live_setting_not_open():
    assert _rsa()["campaign"]["bidding"] == "Maximize clicks, max CPC bid limit 1,20 EUR"


def test_campaign_md_records_the_live_campaign():
    text = _campaign()
    for fact in (
        "StudioFace CV 2026-09",
        "24285475822",
        "Google Ads API (Windsor)",
        "PAUSED",
        "1,20 EUR",
        "5 EUR",
        "23 September to 2 October 2026",
        "presence only",
        "Spanish",
        "Google Search only",
        "41",
    ):
        assert fact in text, fact


def test_the_four_sitelinks_and_callouts_are_recorded_exactly():
    text = _campaign()
    for label, url in SITELINKS.items():
        assert f"| {label} | {url} |" in text, label
    for callout in CALLOUTS:
        assert f"`{callout}`" in text, callout


def test_the_by_hand_build_sheet_is_gone():
    """Must be refused: instructions for a build that already happened another way."""
    text = _campaign()
    assert "Checklist — tick each one while building the campaign by hand" not in text
    assert "builds the campaign from by hand" not in text
    assert "## Building the CV campaign in Google Ads" not in text


def test_the_kill_rule_section_is_byte_identical():
    text = _campaign()
    start = text.index("## Pre-registered test")
    end = text.index("\n## ", start + 1)
    assert hashlib.sha256(text[start:end].encode("utf-8")).hexdigest() == KILL_RULE_SHA256
