"""The demo pairs, and the rules they are not allowed to break.

Two of these matter more than the rest.

A source photograph that looks good destroys the product's only honest claim. If the
"before" is well lit and sharp, the "after" is not an improvement and the page is
selling nothing. So the source prompts are forbidden the words that produce a nice
photograph, and each must name an imperfection.

And an unlabelled pair is a misleading representation of results under Directive
2005/29/EC and Ley 3/1991, and an undisclosed AI image under AI Act Art. 50. The
people in the "before" images do not exist. Saying so is not a courtesy, and it cannot
be left to whoever writes the component later — so both the caption and the alt text
are asserted here, on every pair, in the built HTML.
"""

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "frontend" / "out"
MUESTRAS = ROOT / "frontend" / "public" / "muestras"


def script():
    spec = importlib.util.spec_from_file_location(
        "make_demo_assets", ROOT / "scripts" / "make_demo_assets.py"
    )
    mod = importlib.util.module_from_spec(spec)
    # Registered BEFORE exec: @dataclass resolves its annotations through
    # sys.modules[cls.__module__].__dict__, so a module loaded by path alone raises
    # AttributeError: 'NoneType' object has no attribute '__dict__'.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- the prompts


def test_three_people_with_distinct_keys_and_styles():
    people = script().PEOPLE
    assert len(people) == 3
    assert len({p.key for p in people}) == 3
    assert len({p.style for p in people}) == 3, "each demo should exercise a different style"


def test_no_source_prompt_uses_a_word_that_makes_it_look_good():
    """The load-bearing rule. A 'professional' source is not a before."""
    mod = script()
    for person in mod.PEOPLE:
        low = person.prompt.lower()
        for word in mod.FORBIDDEN_IN_SOURCE:
            assert word not in low, f"{person.key}: source prompt contains {word!r}"


def test_every_source_prompt_names_the_camera_situation():
    """Not an art style. 'Front camera at arm's length' makes a photograph."""
    for person in script().PEOPLE:
        low = person.prompt.lower()
        assert "front camera" in low or "phone" in low, person.key
        assert "arm's length" in low, person.key


def test_every_source_prompt_names_an_imperfection():
    """Without one the model returns a clean portrait and the comparison collapses."""
    marks = ("blur", "uneven", "off-centre", "grain", "shadow", "underexposed", "soft", "cast")
    for person in script().PEOPLE:
        low = person.prompt.lower()
        assert any(m in low for m in marks), f"{person.key}: no imperfection named"


def test_every_source_prompt_describes_three_situations():
    for person in script().PEOPLE:
        for shot in ("shot one", "shot two", "shot three"):
            assert shot in person.prompt.lower(), f"{person.key}: missing {shot}"


def test_negatives_are_a_separate_clause_not_mixed_in():
    mod = script()
    for person in mod.PEOPLE:
        msg = f"{person.key}: negatives are not a trailing clause of their own"
        assert person.prompt.endswith(mod.NEGATIVE), msg


def test_no_prompt_names_a_brand_a_minor_or_a_medical_claim():
    banned = (
        "nike",
        "adidas",
        "apple",
        "iphone",
        "child",
        "kid",
        "teen",
        "minor",
        "clinic",
        "doctor",
        "medical",
        "treatment",
        "surgery",
    )
    for person in script().PEOPLE:
        low = person.prompt.lower()
        for word in banned:
            assert not re.search(rf"\b{word}\b", low), f"{person.key}: prompt contains {word!r}"


# ---------------------------------------------------------------- the money


def test_the_cost_ceiling_is_three_dollars_and_the_shot_count_is_within_the_api_limit():
    mod = script()
    assert mod.CEILING_USD == 3.00
    assert 1 <= mod.SHOTS_PER_PERSON <= 4, "num_images maximum is 4 (live OpenAPI, verified.md)"


def test_the_endpoint_is_the_verified_one():
    """Two different ids resolve to this schema and the docs contradicted themselves;
    this is the one fal's own code snippet shows."""
    assert script().FAL_APP == "openai/gpt-image-2"


# ---------------------------------------------------------------- labelling


def muestra_keys() -> list[str]:
    return sorted({p.name.rsplit("-", 1)[0] for p in MUESTRAS.glob("*-antes.webp")})


@pytest.mark.skipif(not MUESTRAS.is_dir(), reason="no muestras built yet")
def test_each_pair_has_both_roles_in_both_formats():
    for key in muestra_keys():
        for role in ("antes", "despues"):
            for ext in ("webp", "jpg"):
                path = MUESTRAS / f"{key}-{role}.{ext}"
                assert path.exists(), f"missing {path.name}"


@pytest.mark.skipif(not MUESTRAS.is_dir(), reason="no muestras built yet")
def test_each_pair_stays_inside_the_byte_budget():
    mod = script()
    for key in muestra_keys():
        total = sum((MUESTRAS / f"{key}-{r}.webp").stat().st_size for r in ("antes", "despues"))
        assert total <= mod.PAIR_BUDGET_BYTES, (
            f"{key}: {total / 1024:.0f} KB over the {mod.PAIR_BUDGET_BYTES / 1024:.0f} KB budget"
        )


@pytest.mark.skipif(not (EXPORT / "index.html").exists(), reason="no built export")
def test_the_landing_page_discloses_that_the_source_people_are_generated():
    """The legal one. Directive 2005/29/EC, Ley 3/1991, AI Act Art. 50."""
    html = (EXPORT / "index.html").read_text(encoding="utf-8", errors="ignore")
    if "muestras/" not in html:
        pytest.skip("no muestras on the page yet")
    assert "generada con IA" in html or "generadas con IA" in html, (
        "no visible caption saying the source people are AI-generated"
    )
    assert "mismo proceso" in html, (
        "the caption must say the result came from the same pipeline a customer's photos go through"
    )


@pytest.mark.skipif(not (EXPORT / "index.html").exists(), reason="no built export")
def test_every_muestra_image_carries_alt_text_saying_the_same():
    """A screen reader user is owed the same disclosure as everyone else, so the
    disclosure cannot live only in a caption next to the picture."""
    html = (EXPORT / "index.html").read_text(encoding="utf-8", errors="ignore")
    if "muestras/" not in html:
        pytest.skip("no muestras on the page yet")
    imgs = re.findall(r"<img[^>]*muestras/[^>]*>", html)
    assert imgs, "muestras referenced but no <img> found"
    for tag in imgs:
        alt = re.search(r'alt="([^"]*)"', tag)
        assert alt, f"muestra image with no alt: {tag[:100]}"
        assert "IA" in alt.group(1), f"alt text does not disclose generation: {alt.group(1)!r}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
