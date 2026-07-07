"""Human-readable knob list — useful as a CLI output and a hardware dial-in aid.

When the ME-80 loads a patch the physical knobs **don't move** to match the new
values until you touch them. So the knob list is the printable "settings card"
that lets you dial the patch in by hand if needed.

Source labels: spec §3.3 (effect-block table) + §4 (enum names). The generic
knob slots (comp1..3, mod1..3, fx2_1..4) get per-type labels from the enums
knob tables where known, so the card says "RATE 40", not "knob1 40".
"""

from __future__ import annotations

from typing import Any

from . import enums

# Each row: (display label, switch key, type key, type-name table,
#            per-type knob-label table or None, [knob param keys])
_BLOCKS: list[
    tuple[str, str, str, tuple[str, ...] | None, dict[str, tuple[str, ...]] | None, list[str]]
] = [
    ("PEDAL FX", "pdlfx_sw", "pdlfx_type", enums.PEDAL_FX_TYPES, None, []),
    ("COMP/FX1", "comp_sw", "comp_type", enums.COMP_FX1_TYPES, enums.COMP_FX1_KNOBS,
     ["comp1", "comp2", "comp3"]),
    ("OD/DS", "odds_sw", "odds_type", enums.OD_DS_TYPES,
     {t: ("DRIVE", "TONE", "LEVEL") for t in enums.OD_DS_TYPES},
     ["odds1", "odds2", "odds3"]),
    ("PREAMP", "amp_sw", "amp_type", enums.PREAMP_TYPES,
     {t: ("GAIN", "BASS", "MIDDLE", "TREBLE", "LEVEL") for t in enums.PREAMP_TYPES},
     ["amp1", "amp2", "amp3", "amp4", "amp5"]),
    ("MOD", "mod_sw", "mod_type", enums.MOD_TYPES, enums.MOD_KNOBS,
     ["mod1", "mod2", "mod3"]),
    ("EQ/FX2", "fx2_sw", "fx2_type", enums.EQ_FX2_TYPES, enums.EQ_FX2_KNOBS,
     ["fx2_1", "fx2_2", "fx2_3", "fx2_4"]),
    ("DELAY", "dly_sw", "dly_type", enums.DELAY_TYPES,
     {t: ("TIME", "FEEDBACK", "E.LEVEL") for t in enums.DELAY_TYPES},
     ["dly1", "dly2", "dly3"]),
    ("REVERB", "rev_sw", "rev_type", enums.REVERB_TYPES,
     {t: ("LEVEL",) for t in enums.REVERB_TYPES},
     ["rev"]),
]


def _type_name(idx_str: str, table: tuple[str, ...] | None) -> str:
    if table is None:
        return idx_str
    try:
        return table[int(idx_str)]
    except (ValueError, IndexError):
        return f"?({idx_str})"


def render_knob_list(patch_or_params: dict[str, Any]) -> str:
    """Render a single patch (full patch dict or just its params) as a knob list.

    Off blocks render as a single dim line so the chain shape stays visible.
    """
    params = patch_or_params.get("params", patch_or_params)
    name = params.get("patchname", "").rstrip()

    lines: list[str] = []
    lines.append(f"Patch: {name!r}")
    lines.append("Signal chain: IN → " + " → ".join(b[0] for b in _BLOCKS) + " → OUT")
    lines.append("")

    for label, sw_key, type_key, type_table, knob_table, knob_params in _BLOCKS:
        on = params.get(sw_key) == "1"
        type_name = _type_name(params.get(type_key, "0"), type_table)
        head = f"  [{'ON ' if on else 'off'}] {label:<9} {type_name}"
        if not on or not knob_params:
            lines.append(head)
            continue
        lines.append(head)
        knob_labels = enums.knob_labels(knob_table or {}, type_name, len(knob_params))
        for klabel, kparam in zip(knob_labels, knob_params, strict=True):
            lines.append(f"           {klabel:<9} {params.get(kparam, '?')}")
    lines.append("")
    lines.append(f"  NS threshold: {params.get('ns_thresh', '?')}")
    return "\n".join(lines)


def render_liveset(liveset: dict[str, Any]) -> str:
    """Render every patch in a liveset, separated by horizontal rules."""
    name = liveset.get("liveSetData", {}).get("name", "")
    blocks = [f"Liveset: {name!r}  ({len(liveset.get('patchList', []))} patches)", ""]
    for patch in liveset.get("patchList", []):
        blocks.append(render_knob_list(patch))
        blocks.append("-" * 60)
    return "\n".join(blocks)
