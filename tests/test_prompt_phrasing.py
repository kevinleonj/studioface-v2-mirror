"""The prompt describes what the photograph IS, never what it must not contain.

Google's image-generation guidance is explicit, and we were doing the opposite:

    "When excluding elements, use semantic negative prompts that describe the scene
     positively (e.g., 'an empty street') rather than stating what not to include"
    -- https://ai.google.dev/gemini-api/docs/image-generation

Our clause read "No text, no logo, no watermark, no hands, no extra people, no
over-smoothed skin, no cartoon or painting effect", and the identity block ended "Do
not beautify, slim, age or de-age the face." nano-banana-2 is a Gemini-family model
with no separate negative-conditioning input, so every one of those nouns was simply
more subject matter in the prompt. "No hands" is the textbook way to get hands.

Rewritten as scene facts: the person is alone, framed chest-up, the backdrop is plain,
the skin keeps its texture, the image is a photograph. Same ground covered, phrased the
way the vendor says to phrase it.

This test is deliberately crude — it greps for exclusion words. A crude rule that holds
is worth more here than a subtle one nobody runs.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.guards import IDENTITY, STYLES, WARDROBES, build_prompt  # noqa: E402

# Phrasings that name a thing in order to forbid it. Word-boundary matched so
# "another", "nose" and "notes" do not trip it.
EXCLUSIONS = (
    r"\bno\b",
    r"\bnot\b",
    r"\bnone\b",
    r"\bnever\b",
    r"\bwithout\b",
    r"\bavoid\b",
    r"\bdo not\b",
    r"\bdon't\b",
    r"\bfree of\b",
    r"\bexclude\b",
)


def every_prompt() -> list[tuple[str, str]]:
    out = []
    for style in STYLES:
        for variant in range(4):
            out.append((f"{style}/{variant}", build_prompt(style, variant)))
            for wardrobe in WARDROBES:
                out.append(
                    (f"{style}/{variant}/{wardrobe}", build_prompt(style, variant, wardrobe))
                )
    return out


def test_no_prompt_states_what_to_leave_out():
    """The one change in this file with a primary-source citation behind it."""
    for name, prompt in every_prompt():
        low = prompt.lower()
        for pattern in EXCLUSIONS:
            hit = re.search(pattern, low)
            assert not hit, (
                f"{name}: prompt excludes rather than describes — {hit.group(0)!r} in "
                f"...{low[max(0, hit.start() - 60) : hit.end() + 60]}..."
            )


def test_the_identity_block_asks_for_preservation_not_prohibition():
    """Google's own detail-preservation pattern is 'Ensure the features remain
    completely unchanged' — an instruction to keep, not a list of things not to do."""
    low = IDENTITY.lower()
    for pattern in EXCLUSIONS:
        assert not re.search(pattern, low), f"IDENTITY still forbids: {IDENTITY}"
    assert "same" in low or "unchanged" in low


def test_the_scene_facts_that_replaced_the_exclusions_are_all_present():
    """Each affirmative clause stands in for one of the old prohibitions. If one is
    dropped, the prompt quietly stops asking for it at all."""
    prompt = build_prompt("corporativo", 0).lower()
    assert "alone" in prompt, "replaced 'no extra people'"
    assert "chest up" in prompt or "chest-up" in prompt, "replaced 'no hands'"
    assert "plain" in prompt or "clean" in prompt, "replaced 'no text, no logo'"
    assert "pores" in prompt or "texture" in prompt, "replaced 'no over-smoothed skin'"
    assert "photograph" in prompt, "replaced 'no cartoon or painting effect'"


def test_the_prompt_still_follows_the_documented_template_order():
    """Google's recommended shape: 'A photorealistic [shot] of a [subject] in a
    [setting]. [Light]. Shot from a [angle] with a [lens].'"""
    prompt = build_prompt("linkedin", 2)
    assert prompt.startswith("A photorealistic ")
    assert prompt.index("illuminated") > prompt.index("set in")


def test_the_four_variants_are_still_four_different_prompts():
    assert len({build_prompt("creativo", i) for i in range(4)}) == 4


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
