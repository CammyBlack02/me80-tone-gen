"""Tests for the recipe matcher and the packaged starter recipes."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from me80_tone_gen.recipes import Recipe, RecipeBook, load_recipes, match_recipe


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


def test_matcher_requires_word_boundaries() -> None:
    """Short aliases must not match inside unrelated words.

    Regression: with bare substring matching, "nin" (Nine Inch Nails) matched
    inside "evening" and "morning", sending gentle clean descriptions to an
    industrial-distortion seed.
    """
    nin = Recipe.model_validate(_minimal_recipe(id="nin", aliases=["nin", "creep"]))
    book = [nin]
    assert match_recipe("warm evening clean tone", book) is None
    assert match_recipe("gentle morning acoustic vibe", book) is None
    assert match_recipe("creepy ambient horror tone", book) is None
    assert match_recipe("nin style industrial tone", book) is nin


def test_matcher_boundary_handles_punctuated_aliases() -> None:
    """Aliases that start or end with non-word characters still match."""
    acdc = Recipe.model_validate(_minimal_recipe(id="acdc", aliases=["ac/dc"]))
    bb = Recipe.model_validate(_minimal_recipe(id="bb", aliases=["b.b. king"]))
    assert match_recipe("ac/dc style rhythm", [acdc]) is acdc
    assert match_recipe("smooth b.b. king lead", [bb]) is bb


@pytest.mark.parametrize(
    "description",
    [
        "warm evening clean tone",
        "gentle morning acoustic vibe",
        "a tone that would suit soft dinner music",
        "creepy ambient horror soundtrack tone",
        "make it sound alive and open",
        "plush warm clean tone",
        "bright sparkly clean with a touch of delay",
        "dark heavy detuned wall of distortion",
    ],
)
def test_innocent_descriptions_hit_no_artist_recipe(
    recipes: list[Recipe], description: str
) -> None:
    """Generic descriptions must not be routed to a specific artist/song seed.

    A genre fallback recipe (id ending in "-fallback") is acceptable; an artist
    or song recipe is not — its seed would override the user's description.
    """
    r = match_recipe(description, recipes)
    assert r is None or r.id.endswith("-fallback"), (
        f"{description!r} matched {r.id}"
    )


def test_aliases_unique_across_recipes(recipes: list[Recipe]) -> None:
    """A duplicated alias would make routing depend on recipe order."""
    seen: dict[str, str] = {}
    for r in recipes:
        for a in r.aliases:
            key = a.lower()
            assert key not in seen, f"alias {a!r} in both {seen[key]} and {r.id}"
            seen[key] = r.id


def test_matcher_prefers_more_specific_alias_on_tie() -> None:
    """When two recipes match, the one with the longer matching alias wins."""
    short = Recipe.model_validate(_minimal_recipe(id="short-match", aliases=["rock"]))
    long = Recipe.model_validate(
        _minimal_recipe(id="specific-match", aliases=["classic hard rock rhythm"])
    )
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


@pytest.mark.parametrize(
    "override,field,expected",
    [
        ({}, "confidence", "untested"),
        ({"confidence": "tested"}, "confidence", "tested"),
        ({}, "tags", []),
        ({"tags": ["metal", "1980s", "lead"]}, "tags", ["metal", "1980s", "lead"]),
    ],
)
def test_recipe_optional_field_default_or_override(override: dict, field: str, expected: object) -> None:
    r = Recipe.model_validate(_minimal_recipe(**override))
    assert getattr(r, field) == expected


def test_confidence_rejects_other_values() -> None:
    """Only 'tested' / 'untested' allowed — protects against typos like 'verified'."""
    with pytest.raises(ValidationError):
        Recipe.model_validate(_minimal_recipe(confidence="verified"))


def test_packaged_recipe_tags_survive_round_trip(recipes: list[Recipe]) -> None:
    """The `tags` field name must match between recipes.json and the schema.

    If someone typos `tags` to `tag` in the JSON, Pydantic silently defaults to
    `[]` and no other test would catch it. Asserting at least one recipe has
    non-empty tags confirms the field round-trips through the JSON load.
    """
    assert any(r.tags for r in recipes), (
        "no recipe has a non-empty tags list — has the field name drifted between "
        "recipes.json and the Recipe model?"
    )


# --- helpers ---

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


def _minimal_recipe(**overrides: object) -> dict:
    """Build a minimal valid Recipe payload, with any field optionally overridden."""
    base = {"id": "x", "aliases": ["x"], "description": "x", "patch": _minimal_patch()}
    base.update(overrides)
    return base
