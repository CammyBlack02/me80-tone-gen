"""ME-80 effect-type enumerations — single source of truth.

Values are stored in `.tsl` files as **decimal strings of the index** (e.g. METAL
amp = "8"). The lists below are positional: index = the stored value.

Source: spec §4, derived from Contra_1.tsl + community parser
(johnsrude/BossToneStudio). Names match BOSS TONE STUDIO's UI labels.
"""

from __future__ import annotations

PREAMP_TYPES: tuple[str, ...] = (
    "AC", "CLEAN", "TWEED", "CRUNCH", "COMBO",
    "LEAD", "DRIVE", "STACK", "METAL",
)

OD_DS_TYPES: tuple[str, ...] = (
    "BOOST", "OVERDRIVE", "T-SCREAM", "BLUES", "TURBO OD",
    "DISTORTION", "TURBO DS", "METAL DS", "CORE", "FUZZ", "OCT FUZZ",
)

COMP_FX1_TYPES: tuple[str, ...] = (
    "COMP", "T.WAH UP", "T.WAH DOWN", "OCTAVE", "SLOW GEAR",
    "DEFRETTER", "RING MOD", "AC SIM", "Single>Hum", "Hum>Single", "SOLO",
)

MOD_TYPES: tuple[str, ...] = (
    "PHASER", "FLANGER", "TREMOLO", "CHORUS", "VIBRATO",
    "PITCH SHIFT", "HARMONIST", "ROTARY", "UNI-V", "DELAY", "OVERTONE",
)

EQ_FX2_TYPES: tuple[str, ...] = (
    "PHASER", "TREMOLO", "BOOST", "DELAY", "CHORUS", "EQ",
)

DELAY_TYPES: tuple[str, ...] = (
    "1-99 ms", "100-600 ms", "500-6000 ms", "ANALOG", "TAPE",
    "MODULATE", "REVERSE", "CHO + DELAY", "TEMPO", "TERA ECHO", "PHRASE LOOP",
)

REVERB_TYPES: tuple[str, ...] = ("ROOM", "HALL", "SPRING")

PEDAL_FX_TYPES: tuple[str, ...] = (
    "WAH", "VOICE", "+1 OCT", "+2 OCT", "-1 OCT",
    "FREEZE", "OSC DELAY", "OD/DS", "MOD RATE", "DELAY LEV",
)


# Per-type knob meanings for the generic-knob blocks. The stored params are
# nameless slots (comp1..3, mod1..3, fx2_1..4), but the hardware assigns each
# type its own knob functions — without these the LLM (and the human reading a
# dial-in card) is setting knobs blind.
#
# Labels use standard BOSS parameter names (owner's manual parameter chart /
# BTS labels). Types absent from a table fall back to generic "knob N"
# everywhere — only add an entry once the labels are verified against spec
# §3.3 or the owner's manual; a wrong label is worse than none. Currently
# unverified and therefore omitted: OCTAVE, Single>Hum, Hum>Single, SOLO
# (COMP/FX1); VIBRATO, OVERTONE (MOD); everything but EQ (EQ/FX2).

COMP_FX1_KNOBS: dict[str, tuple[str, ...]] = {
    "COMP": ("SUSTAIN", "ATTACK", "LEVEL"),
    "T.WAH UP": ("SENS", "PEAK", "LEVEL"),
    "T.WAH DOWN": ("SENS", "PEAK", "LEVEL"),
    "SLOW GEAR": ("SENS", "RISE TIME", "LEVEL"),
    "DEFRETTER": ("SENS", "TONE", "LEVEL"),
    "RING MOD": ("FREQ", "E.LEVEL", "D.LEVEL"),
    "AC SIM": ("TOP", "BODY", "LEVEL"),
}

MOD_KNOBS: dict[str, tuple[str, ...]] = {
    "PHASER": ("RATE", "DEPTH", "RESONANCE"),
    "FLANGER": ("RATE", "DEPTH", "RESONANCE"),
    "TREMOLO": ("RATE", "DEPTH", "WAVE"),
    "CHORUS": ("RATE", "DEPTH", "E.LEVEL"),
    "PITCH SHIFT": ("PITCH", "D.LEVEL", "E.LEVEL"),
    "HARMONIST": ("KEY", "HARMONY", "E.LEVEL"),
    "ROTARY": ("RATE", "DEPTH", "E.LEVEL"),
    "UNI-V": ("RATE", "DEPTH", "E.LEVEL"),
    "DELAY": ("TIME", "FEEDBACK", "E.LEVEL"),
}

EQ_FX2_KNOBS: dict[str, tuple[str, ...]] = {
    "EQ": ("BASS", "MIDDLE", "TREBLE", "LEVEL"),
}

KNOBS_BY_BLOCK: dict[str, dict[str, tuple[str, ...]]] = {
    "COMP/FX1": COMP_FX1_KNOBS,
    "MOD": MOD_KNOBS,
    "EQ/FX2": EQ_FX2_KNOBS,
}


def knob_labels(table: dict[str, tuple[str, ...]], type_name: str, n_knobs: int) -> tuple[str, ...]:
    """Knob labels for a type, falling back to generic names when unknown."""
    labels = table.get(type_name.strip().upper() if type_name else "")
    if labels is not None:
        return labels
    return tuple(f"knob{i + 1}" for i in range(n_knobs))


def knob_meanings_by_position(table: dict[str, tuple[str, ...]], position: int) -> str:
    """One-line summary of what knob `position` (0-indexed) means per type.

    Groups types sharing a label: "RATE (PHASER, FLANGER, ...); KEY (HARMONIST)".
    Used in the LLM schema field descriptions so the model knows what it is
    setting.
    """
    groups: dict[str, list[str]] = {}
    for type_name, labels in table.items():
        if position < len(labels):
            groups.setdefault(labels[position], []).append(type_name)
    parts = [f"{label} ({', '.join(types)})" for label, types in groups.items()]
    return "; ".join(parts)


# Lookup helpers — name (case-insensitive, whitespace-tolerant) -> index string.
def _index_lookup(values: tuple[str, ...]) -> dict[str, str]:
    return {v.upper(): str(i) for i, v in enumerate(values)}


PREAMP_INDEX = _index_lookup(PREAMP_TYPES)
OD_DS_INDEX = _index_lookup(OD_DS_TYPES)
COMP_FX1_INDEX = _index_lookup(COMP_FX1_TYPES)
MOD_INDEX = _index_lookup(MOD_TYPES)
EQ_FX2_INDEX = _index_lookup(EQ_FX2_TYPES)
DELAY_INDEX = _index_lookup(DELAY_TYPES)
REVERB_INDEX = _index_lookup(REVERB_TYPES)
PEDAL_FX_INDEX = _index_lookup(PEDAL_FX_TYPES)


def name_to_index(name: str, table: dict[str, str]) -> str:
    """Resolve a type-name to its stored decimal-string index.

    Raises KeyError with a helpful message if the name isn't valid.
    """
    key = name.strip().upper()
    if key not in table:
        valid = ", ".join(sorted(table.keys()))
        raise KeyError(f"{name!r} not in legal types. Valid: {valid}")
    return table[key]
