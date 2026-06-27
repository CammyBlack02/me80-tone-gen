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
