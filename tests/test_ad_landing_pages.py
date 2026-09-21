"""Task 23. The two Google Ads landing pages, /foto-cv/ and /foto-linkedin/.

Keyword Planner (Kevin's account, Spain, Spanish, 20 September 2026) found demand split
into two exact-phrase groups: "foto curriculum"/"foto cv" and "foto linkedin". Each gets
its own landing page, built from ONE shared component
(frontend/src/components/ad-landing.tsx) and ONE content file
(frontend/src/content/ad-pages.ts) so the ad copy and the page never duplicate the
uploader, the slider, or the FAQ markup between the two pages.

Asserts against the BUILT export, same convention as tests/test_seo.py and
tests/test_footer_links.py: run `npm run build` in frontend/ first. CI builds before
this test runs.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "frontend" / "out"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from source_scan import strip_comments  # noqa: E402

pytestmark = pytest.mark.skipif(
    not EXPORT.is_dir(),
    reason="no frontend/out — run `npm run build` in frontend/. CI builds before auditing.",
)

PAGES = {
    "foto-cv": {
        "h1": "Tu foto para el currículum, en dos minutos",
        "h1_needle": "curr",
        "title": "Foto de currículum profesional con IA | StudioFace",
    },
    "foto-linkedin": {
        "h1": "Tu foto profesional para LinkedIn, en dos minutos",
        "h1_needle": "linkedin",
        "title": "Foto profesional para LinkedIn con IA | StudioFace",
    },
}


def html_for(slug: str) -> str:
    path = EXPORT / slug / "index.html"
    assert path.is_file(), f"{path} does not exist — add frontend/src/app/{slug}/page.tsx"
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("slug", PAGES)
def test_the_page_exists_in_the_export(slug):
    html_for(slug)  # asserts inside


@pytest.mark.parametrize("slug", PAGES)
def test_the_h1_is_the_exact_brief_text(slug):
    body = html_for(slug)
    match = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.S)
    assert match, f"{slug}: no <h1> in the built page"
    text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
    assert text == PAGES[slug]["h1"]


@pytest.mark.parametrize("slug", PAGES)
def test_the_h1_contains_the_check_script_needle_lowercased(slug):
    """The definition-of-done check greps the lowercased HTML for this substring inside
    the first <h1>. Pinned here so a copy edit that breaks the live check fails locally
    first."""
    body = html_for(slug).lower()
    match = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.S)
    assert match and PAGES[slug]["h1_needle"] in match.group(1)


@pytest.mark.parametrize("slug", PAGES)
def test_the_canonical_points_at_its_own_address_with_a_trailing_slash(slug):
    body = html_for(slug)
    needle = f'rel="canonical" href="https://studioface.app/{slug}/"'
    assert needle in body, f"{slug}: no self-canonical ({needle!r} not found)"


@pytest.mark.parametrize("slug", PAGES)
def test_the_title_is_its_own_and_not_the_others(slug):
    body = html_for(slug)
    assert f"<title>{PAGES[slug]['title']}</title>" in body
    other = [s for s in PAGES if s != slug][0]
    assert PAGES[other]["title"] not in body


@pytest.mark.parametrize("slug", PAGES)
def test_the_description_is_under_155_chars_and_names_the_free_trial_and_the_price(slug):
    body = html_for(slug)
    match = re.search(r'name="description" content="([^"]*)"', body)
    assert match, f"{slug}: no meta description"
    desc = match.group(1)
    assert len(desc) < 155, f"{slug}: description is {len(desc)} chars"
    assert "prueba gratis, sin registro" in desc
    assert "19,99 €" in desc


@pytest.mark.parametrize("slug", PAGES)
def test_the_intro_is_60_to_90_words(slug):
    body = html_for(slug)
    match = re.search(r"data-subhead[^>]*>([^<]*)<", body)
    assert match, f"{slug}: no [data-subhead] intro paragraph"
    words = len(match.group(1).split())
    assert 60 <= words <= 90, f"{slug}: intro is {words} words"


@pytest.mark.parametrize("slug", PAGES)
def test_the_slider_the_button_the_uploader_and_the_price_are_all_present(slug):
    """The same elements as the home page, reused rather than rebuilt: the before/after
    slider (Comparador), the first-screen call to action (FoldCta), the uploader
    (UploadForm) and the price block."""
    body = html_for(slug)
    assert 'class="sf-ba"' in body, f"{slug}: no comparison slider"
    assert 'data-cta="fold"' in body, f"{slug}: no first-screen call to action"
    assert 'id="sf-files"' in body, f"{slug}: no uploader file input"
    assert "19,99&nbsp;€" in body or "19,99 €" in body, f"{slug}: no visible price"


@pytest.mark.parametrize("slug", PAGES)
def test_every_ai_image_is_disclosed_in_visible_copy_and_alt_text(slug):
    body = html_for(slug)
    assert "generadas con inteligencia artificial" in body or (
        "generada con inteligencia artificial" in body
    ), f"{slug}: no visible AI-generation disclosure"
    assert "generada con ia" in body.lower(), f"{slug}: no AI disclosure in an alt attribute"


@pytest.mark.parametrize("slug", PAGES)
def test_exactly_four_faq_questions_and_they_match_between_the_two_pages(slug):
    """Task 33: the retention question joined the three already here so the ad claim
    'Tus fotos se borran a los 7 días' (docs/ads/rsa.json) actually appears on the page
    the ad points to — see frontend/src/content/ad-pages.ts, SHARED_FAQ."""
    body = html_for(slug)
    questions = re.findall(r"<summary[^>]*>([^<]*)</summary>", body)
    assert len(questions) == 4, f"{slug}: {len(questions)} FAQ questions, expected 4"


def test_the_three_faq_questions_are_identical_on_both_pages():
    bodies = {slug: html_for(slug) for slug in PAGES}
    questions = {
        slug: re.findall(r"<summary[^>]*>([^<]*)</summary>", body) for slug, body in bodies.items()
    }
    assert questions["foto-cv"] == questions["foto-linkedin"]


def test_the_uploader_logic_is_not_duplicated_in_the_source():
    """The brief's hard stop: if UploadForm's logic had been copied rather than reused,
    there would be a second component defining the preview/checkout flow. There is
    exactly one, and the shared ad-landing component is the thing that imports it for
    both ad pages."""
    src = ROOT / "frontend" / "src"
    defs = list(src.glob("components/upload-form*.tsx"))
    assert len(defs) == 1, f"more than one upload-form component: {defs}"
    ad_landing = strip_comments(
        (src / "components" / "ad-landing.tsx").read_text(encoding="utf-8"), language="tsx"
    )
    assert '"@/components/upload-form"' in ad_landing, (
        "ad-landing.tsx does not import the shared UploadForm"
    )


def test_sitemap_lists_both_ad_pages():
    body = (EXPORT / "sitemap.xml").read_text(encoding="utf-8")
    for slug in PAGES:
        assert f"https://studioface.app/{slug}/</loc>" in body, f"sitemap.xml lacks /{slug}/"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
