"""Tests for the recipe matcher and the packaged starter recipes."""

from __future__ import annotations

import pytest

from me80_tone_gen.recipes import Recipe, load_recipes, match_recipe


@pytest.fixture(scope="module")
def recipes() -> list[Recipe]:
    return load_recipes()


def test_packaged_recipes_load_and_validate(recipes: list[Recipe]) -> None:
    """Every starter recipe must be Pydantic-valid (catches schema drift)."""
    assert len(recipes) >= 5
    ids = [r.id for r in recipes]
    assert len(set(ids)) == len(ids), "recipe ids must be unique"


def test_matcher_returns_none_when_no_alias_present(recipes: list[Recipe]) -> None:
    assert match_recipe("warm fingerstyle bossa nova nylon", recipes) is None


def test_matcher_returns_none_for_empty_description(recipes: list[Recipe]) -> None:
    assert match_recipe("", recipes) is None


def test_matcher_finds_master_of_puppets(recipes: list[Recipe]) -> None:
    """The keystone case for RAG — what motivated this whole feature."""
    r = match_recipe("master of puppets rhythm tone", recipes)
    assert r is not None
    assert r.id == "master-of-puppets-rhythm"


def test_matcher_finds_via_band_name_alias(recipes: list[Recipe]) -> None:
    r = match_recipe("ac/dc style rhythm", recipes)
    assert r is not None
    assert r.id == "ac-dc-rhythm"


def test_matcher_finds_srv_via_album_name(recipes: list[Recipe]) -> None:
    r = match_recipe("texas flood blues lead", recipes)
    assert r is not None
    assert r.id == "srv-texas-blues"


def test_matcher_is_case_insensitive(recipes: list[Recipe]) -> None:
    r = match_recipe("MASTER OF PUPPETS rhythm", recipes)
    assert r is not None
    assert r.id == "master-of-puppets-rhythm"


def test_matcher_prefers_more_specific_alias_on_tie() -> None:
    """When two recipes match, the one with the longer matching alias wins."""
    # Construct a synthetic recipe book where two recipes match but one alias
    # is more specific than the other.
    from me80_tone_gen.recipes import RecipeBook

    short = Recipe.model_validate({
        "id": "short-match",
        "aliases": ["rock"],
        "description": "n/a",
        "patch": _minimal_patch(),
    })
    long = Recipe.model_validate({
        "id": "specific-match",
        "aliases": ["classic hard rock rhythm"],
        "description": "n/a",
        "patch": _minimal_patch(),
    })
    book = RecipeBook(recipes=[short, long]).recipes

    r = match_recipe("classic hard rock rhythm tone", book)
    assert r is not None
    assert r.id == "specific-match"


def test_recipe_patches_use_valid_knob_range(recipes: list[Recipe]) -> None:
    """Every knob value in every starter recipe respects the 0-99 hardware range."""
    fields_with_knobs: list[tuple[str, list[str]]] = [
        ("preamp", ["gain", "bass", "middle", "treble", "level"]),
        ("od_ds", ["drive", "tone", "level"]),
        ("comp", ["knob1", "knob2", "knob3"]),
        ("mod", ["knob1", "knob2", "knob3"]),
        ("eq_fx2", ["knob1", "knob2", "knob3", "knob4"]),
        ("delay", ["time", "feedback", "e_level"]),
        ("reverb", ["level"]),
    ]
    for r in recipes:
        patch = r.patch
        for block_name, knobs in fields_with_knobs:
            block = getattr(patch, block_name)
            for k in knobs:
                v = getattr(block, k)
                assert 0 <= v <= 99, f"{r.id}.{block_name}.{k}={v} out of 0-99"


# ---------- confidence + tags schema fields ----------


def test_confidence_defaults_to_untested() -> None:
    r = Recipe.model_validate({
        "id": "x",
        "aliases": ["x"],
        "description": "x",
        "patch": _minimal_patch(),
    })
    assert r.confidence == "untested"


def test_confidence_accepts_tested() -> None:
    r = Recipe.model_validate({
        "id": "x",
        "aliases": ["x"],
        "description": "x",
        "patch": _minimal_patch(),
        "confidence": "tested",
    })
    assert r.confidence == "tested"


def test_confidence_rejects_other_values() -> None:
    """Only 'tested' / 'untested' allowed — protects against typos like 'verified'."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Recipe.model_validate({
            "id": "x",
            "aliases": ["x"],
            "description": "x",
            "patch": _minimal_patch(),
            "confidence": "verified",
        })


def test_tags_default_to_empty_list() -> None:
    r = Recipe.model_validate({
        "id": "x",
        "aliases": ["x"],
        "description": "x",
        "patch": _minimal_patch(),
    })
    assert r.tags == []


def test_tags_accept_list_of_strings() -> None:
    r = Recipe.model_validate({
        "id": "x",
        "aliases": ["x"],
        "description": "x",
        "patch": _minimal_patch(),
        "tags": ["metal", "1980s", "lead"],
    })
    assert r.tags == ["metal", "1980s", "lead"]


def test_packaged_recipes_are_honestly_marked_untested(recipes: list[Recipe]) -> None:
    """Honest signal: every shipped recipe is Claude-seeded, not ear-validated.

    Flip individual recipes to `confidence: "tested"` in recipes.json only after
    the author has actually played them through the pedal. If this test starts
    failing because a recipe is tested=true, that's expected — update the count.
    """
    tested = [r for r in recipes if r.confidence == "tested"]
    untested = [r for r in recipes if r.confidence == "untested"]
    assert len(tested) + len(untested) == len(recipes), "unexpected confidence value"
    # As of #7 landing, the entire starter set ships untested. The author can
    # flip individual recipes to "tested" via direct-to-main commits (per
    # WORKFLOW.md trivial-issue path) as they ear-test them.
    assert len(tested) == 0, (
        f"{len(tested)} recipes marked tested — has anyone actually ear-tested them? "
        f"If yes, update this assertion to the new count and document which were tested."
    )


# --- helper ---

def _minimal_patch() -> dict:
    return {
        "preamp": {"enabled": True, "type": "CLEAN", "gain": 50, "bass": 50, "middle": 50, "treble": 50, "level": 50},
        "od_ds": {"enabled": False, "type": "OVERDRIVE", "drive": 50, "tone": 50, "level": 50},
        "comp": {"enabled": False, "type": "COMP", "knob1": 50, "knob2": 50, "knob3": 50},
        "mod": {"enabled": False, "type": "CHORUS", "knob1": 50, "knob2": 50, "knob3": 50},
        "eq_fx2": {"enabled": False, "type": "EQ", "knob1": 50, "knob2": 50, "knob3": 50, "knob4": 50},
        "delay": {"enabled": False, "type": "100-600 ms", "time": 50, "feedback": 50, "e_level": 50},
        "reverb": {"enabled": False, "type": "ROOM", "level": 50},
        "pedal_fx": {"enabled": False, "type": "WAH"},
    }
