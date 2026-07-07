"""Artist / song / style recipes — a tiny RAG layer.

The LLM has general taste ("metal sounds bright/scooped") but not reliable
factoid recall ("for Master of Puppets, gain ~70, T-SCREAM in front"). Curated
recipes act as an answer key: when a description mentions a known tone, we
inject the recipe into the prompt as a seed and the LLM tweaks from there
rather than guessing from scratch.

Matching strategy: whole-word substring scoring against each recipe's `aliases`
list. Highest score wins; ties broken by longest matched alias (more specific
match). Plenty for ~100 recipes — no vector DB needed at this scale.

Aliases only match at word boundaries. Bare substring matching caused real
false positives at 100+ recipes: "nin" (Nine Inch Nails) matched inside
"evening" and "morning", "creep" matched inside "creepy". Short aliases are
safe only because of the boundary check — keep it.
"""

from __future__ import annotations

import json
import re
from importlib.resources import files
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .schema import (
    CompBlock,
    DelayBlock,
    EqFx2Block,
    ModBlock,
    OdDsBlock,
    PedalFxBlock,
    PreampBlock,
    ReverbBlock,
)


class RecipePatch(BaseModel):
    """The seed patch settings — same shape as SemanticPatch minus name/rationale."""

    preamp: PreampBlock
    od_ds: OdDsBlock
    comp: CompBlock
    mod: ModBlock
    eq_fx2: EqFx2Block
    delay: DelayBlock
    reverb: ReverbBlock
    pedal_fx: PedalFxBlock


class Recipe(BaseModel):
    id: str = Field(min_length=1)
    aliases: list[str] = Field(min_length=1)
    description: str
    patch: RecipePatch
    # Curated values seeded by Claude default to "untested" until ear-verified
    # through the pedal — see CLAUDE.md anti-patterns.
    confidence: Literal["tested", "untested"] = "untested"
    tags: list[str] = Field(default_factory=list)


class RecipeBook(BaseModel):
    recipes: list[Recipe]


def load_recipes(path: Path | None = None) -> list[Recipe]:
    """Load recipes from disk (packaged default if path is None)."""
    if path is None:
        with files("me80_tone_gen").joinpath("recipes.json").open(
            "r", encoding="utf-8"
        ) as f:
            raw = json.load(f)
    else:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return RecipeBook.model_validate(raw).recipes


def _alias_present(alias: str, text: str) -> bool:
    """True if `alias` appears in `text` as whole words.

    Lookarounds rather than \\b so aliases that start or end with non-word
    characters ("ac/dc", "b.b. king") still anchor correctly.
    """
    return re.search(rf"(?<!\w){re.escape(alias.lower())}(?!\w)", text) is not None


def match_recipe(description: str, recipes: list[Recipe]) -> Recipe | None:
    """Return the best-matching recipe for a description, or None.

    Scoring: number of aliases present (whole-word) in `description.lower()`.
    Ties broken by longest matched alias (more specific match wins).
    """
    text = description.lower()
    best: tuple[int, int, Recipe] | None = None  # (hit_count, longest_alias_len, recipe)
    for r in recipes:
        hits = [a for a in r.aliases if _alias_present(a, text)]
        if not hits:
            continue
        longest = max(len(a) for a in hits)
        key = (len(hits), longest)
        if best is None or key > best[:2]:
            best = (key[0], key[1], r)
    return best[2] if best else None
