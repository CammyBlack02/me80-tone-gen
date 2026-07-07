"""Pydantic models — the LLM's output contract.

The model emits human-meaningful type *names* (e.g. "METAL", "T-SCREAM") and
0-100 knob values. `writer.semantic_to_params` translates this into the 82-key
params dict the `.tsl` format requires.

Why semantic shape (not raw indices): keeps the prompt readable, lets the LLM
think in concepts ("scooped-mid high-gain"), and centralises clamping/mapping in
the writer where we can unit-test it.

Why no field defaults: every default we add becomes "optional" in the JSON
schema, and structured-output models will skip those fields. Then the rationale
brags about spring reverb that isn't actually enabled. Forcing the model to
commit to every block produces drastically better tone choices.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from . import enums

Knob = Annotated[
    int,
    Field(
        ge=0,
        le=99,
        description="0-99; 50 is mid. The ME-80 hardware caps a max-position knob at 99, not 100.",
    ),
]


def _knob_field(table: dict[str, tuple[str, ...]], position: int) -> Any:
    """A required Knob field whose description says what it controls per type.

    The generic slots (knob1..knob4) mean different things per effect type;
    surfacing the per-type meaning in the JSON schema is what lets the model
    set them deliberately instead of guessing. No default is set — every knob
    stays required (see module docstring).
    """
    meanings = enums.knob_meanings_by_position(table, position)
    return Field(description=f"Meaning by type — {meanings}. Types not listed: generic depth/amount.")


class PreampBlock(BaseModel):
    enabled: Literal[True] = True  # Preamp is always on by hardware design.
    type: Literal[*enums.PREAMP_TYPES]  # type: ignore[valid-type]
    gain: Knob
    bass: Knob
    middle: Knob
    treble: Knob
    level: Knob


class OdDsBlock(BaseModel):
    enabled: bool
    type: Literal[*enums.OD_DS_TYPES]  # type: ignore[valid-type]
    drive: Knob
    tone: Knob
    level: Knob


class CompBlock(BaseModel):
    enabled: bool
    type: Literal[*enums.COMP_FX1_TYPES]  # type: ignore[valid-type]
    knob1: Knob = _knob_field(enums.COMP_FX1_KNOBS, 0)
    knob2: Knob = _knob_field(enums.COMP_FX1_KNOBS, 1)
    knob3: Knob = _knob_field(enums.COMP_FX1_KNOBS, 2)


class ModBlock(BaseModel):
    enabled: bool
    type: Literal[*enums.MOD_TYPES]  # type: ignore[valid-type]
    knob1: Knob = _knob_field(enums.MOD_KNOBS, 0)
    knob2: Knob = _knob_field(enums.MOD_KNOBS, 1)
    knob3: Knob = _knob_field(enums.MOD_KNOBS, 2)


class EqFx2Block(BaseModel):
    enabled: bool
    type: Literal[*enums.EQ_FX2_TYPES]  # type: ignore[valid-type]
    knob1: Knob = _knob_field(enums.EQ_FX2_KNOBS, 0)
    knob2: Knob = _knob_field(enums.EQ_FX2_KNOBS, 1)
    knob3: Knob = _knob_field(enums.EQ_FX2_KNOBS, 2)
    knob4: Knob = _knob_field(enums.EQ_FX2_KNOBS, 3)


class DelayBlock(BaseModel):
    enabled: bool
    type: Literal[*enums.DELAY_TYPES]  # type: ignore[valid-type]
    time: Knob
    feedback: Knob
    e_level: Knob


class ReverbBlock(BaseModel):
    enabled: bool
    type: Literal[*enums.REVERB_TYPES]  # type: ignore[valid-type]
    level: Knob


class PedalFxBlock(BaseModel):
    enabled: bool
    type: Literal[*enums.PEDAL_FX_TYPES]  # type: ignore[valid-type]


class SemanticPatch(BaseModel):
    """The LLM's output. Translates to ME-80 params via writer.semantic_to_params."""

    # Printable ASCII only: the name is stored as per-character ASCII codes
    # (name1..16) and the pedal's display has no wider charset.
    patch_name: Annotated[str, Field(min_length=1, max_length=16, pattern=r"^[ -~]+$")]
    preamp: PreampBlock
    od_ds: OdDsBlock
    comp: CompBlock
    mod: ModBlock
    eq_fx2: EqFx2Block
    delay: DelayBlock
    reverb: ReverbBlock
    pedal_fx: PedalFxBlock
    rationale: str
