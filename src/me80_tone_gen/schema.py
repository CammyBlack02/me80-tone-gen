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

from typing import Annotated, Literal

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
    knob1: Knob
    knob2: Knob
    knob3: Knob


class ModBlock(BaseModel):
    enabled: bool
    type: Literal[*enums.MOD_TYPES]  # type: ignore[valid-type]
    knob1: Knob
    knob2: Knob
    knob3: Knob


class EqFx2Block(BaseModel):
    enabled: bool
    type: Literal[*enums.EQ_FX2_TYPES]  # type: ignore[valid-type]
    knob1: Knob
    knob2: Knob
    knob3: Knob
    knob4: Knob


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

    patch_name: Annotated[str, Field(min_length=1, max_length=16)]
    preamp: PreampBlock
    od_ds: OdDsBlock
    comp: CompBlock
    mod: ModBlock
    eq_fx2: EqFx2Block
    delay: DelayBlock
    reverb: ReverbBlock
    pedal_fx: PedalFxBlock
    rationale: str
