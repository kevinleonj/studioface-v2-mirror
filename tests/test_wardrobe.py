"""The customer picks the clothes. We never ask, infer or store their gender.

The bug: guards.STYLES hard-coded one wardrobe per style, and all three were menswear
-- "a dark navy blazer over a plain white shirt", "a smart-casual light blue shirt, no
tie". Every customer got men's clothing whoever they were. The mujer-40 demo pair shows
it: a 40-year-old woman in a man's button-down.

The fix could have been a gender question. It is deliberately not one.

  - Asking the person means collecting an identity attribute to sell a 19,99 EUR
    photograph. GDPR Art. 9 does not name gender identity among the special categories
    (only "sex life or sexual orientation"), so it is arguably ordinary personal data
    -- but "arguably" is not a position worth defending when the alternative costs
    nothing. Spain's Ley 4/2023 also makes self-declared sex legally authoritative,
    which makes a verified-looking field faintly absurd.
  - Asking about the OUTPUT collects nothing about the person at all. It is also
    strictly more useful: a man who wants the tailored jacket and a woman who wants
    the blazer and shirt both get what they asked for, and neither has to answer a
    question about themselves to buy a photograph.
  - It matches the one competitor in this exact category we could verify: Aragon.ai
    sells "Choice of 1 attire / 2 attires / All attires included" and never asks.

So the field is a garment, the labels name garments, and no option is labelled by
gender. The default stays what it was, so nothing breaks for an order placed before
this existed.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import Order  # noqa: E402
from app.guards import STYLES, WARDROBES, build_prompt  # noqa: E402

GENDER_WORDS = (
    "hombre",
    "mujer",
    "man",
    "woman",
    "male",
    "female",
    "masculino",
    "femenino",
    "gender",
    "sexo",
    "género",
)


# ---------------------------------------------------------------- the catalogue


def test_there_is_more_than_one_wardrobe_and_they_are_not_all_the_same_garment():
    assert len(WARDROBES) >= 4
    assert len({w["prompt"] for w in WARDROBES.values()}) == len(WARDROBES)


def test_no_wardrobe_is_labelled_by_gender():
    """The whole point. An option called 'Femenino' is the question we refused to ask,
    wearing a different hat."""
    for key, w in WARDROBES.items():
        blob = f"{key} {w['label']}".lower()
        for word in GENDER_WORDS:
            assert word not in blob, f"wardrobe {key!r} is labelled by gender: {w['label']!r}"


def test_every_wardrobe_has_a_spanish_label_a_customer_could_choose_from():
    for key, w in WARDROBES.items():
        assert w["label"].strip(), key
        # A label is for a person choosing clothes, not a prompt fragment.
        assert len(w["label"]) < 40, f"{key}: label reads like a prompt, not a choice"


def test_the_catalogue_covers_both_tailored_and_relaxed_options():
    prompts = " ".join(w["prompt"] for w in WARDROBES.values()).lower()
    assert "blazer" in prompts or "jacket" in prompts
    assert "blouse" in prompts, "no option for anyone who does not want a men's shirt"
    assert "crew-neck" in prompts or "t-shirt" in prompts


# ---------------------------------------------------------------- the prompt


def test_the_chosen_wardrobe_reaches_the_prompt():
    for key, w in WARDROBES.items():
        prompt = build_prompt("corporativo", 0, wardrobe=key)
        assert w["prompt"] in prompt, f"{key} never reached the prompt"


def test_the_wardrobe_is_independent_of_the_style():
    """Style sets the scene, wardrobe sets the clothes. Picking a blouse must not drag
    the linkedin office backdrop into the corporativo backdrop."""
    corporativo = build_prompt("corporativo", 0, wardrobe="blusa-sastre")
    assert STYLES["corporativo"]["env"] in corporativo
    assert STYLES["linkedin"]["env"] not in corporativo


def test_omitting_the_wardrobe_keeps_exactly_the_old_prompt():
    """Expand-contract: orders placed before this field existed must generate the same
    images they would have generated yesterday."""
    for style in STYLES:
        for variant in range(4):
            assert build_prompt(style, variant) == build_prompt(style, variant, wardrobe=None)
            assert STYLES[style]["wardrobe"] in build_prompt(style, variant)


def test_an_unknown_wardrobe_is_refused_rather_than_silently_ignored():
    """Silently falling back would let a typo in the browser sell someone the wrong
    clothes, and they would only find out after paying."""
    with pytest.raises(KeyError):
        build_prompt("corporativo", 0, wardrobe="esmoquin-dorado")


def test_the_four_variants_still_differ_with_a_wardrobe_chosen():
    prompts = {build_prompt("linkedin", i, wardrobe="camisa-azul") for i in range(4)}
    assert len(prompts) == 4, "the four photographs would be four runs of one prompt"


# ---------------------------------------------------------------- the order


def test_an_order_carries_the_wardrobe_and_defaults_to_none():
    plain = Order(
        id="o1", email="a@b.com", source_image_urls=[], style="corporativo", amount_cents=1999
    )
    assert plain.wardrobe is None
    chosen = Order(
        id="o2",
        email="a@b.com",
        source_image_urls=[],
        style="corporativo",
        amount_cents=1999,
        wardrobe="blusa-sastre",
    )
    assert chosen.wardrobe == "blusa-sastre"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
