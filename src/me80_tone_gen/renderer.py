"""Human-readable knob list — useful as a CLI output and a hardware dial-in aid.

When the ME-80 loads a patch the physical knobs **don't move** to match the new
values until you touch them. So the knob list is the printable "settings card"
that lets Cameron dial the patch in by hand if needed.

Source labels: spec §3.3 (effect-block table) + §4 (enum names).
"""

from __future__ import annotations

from typing import Any

from . import enums

# Each row: (display label, switch key, type key, type-name table,
#            [(knob label, knob param key), ...])
_BLOCKS: list[tuple[str, str, str, tuple[str, ...] | None, list[tuple[str, str]]]] = [
    ("PEDAL FX", "pdlfx_sw", "pdlfx_type", enums.PEDAL_FX_TYPES, []),
    ("COMP/FX1", "comp_sw", "comp_type", enums.COMP_FX1_TYPES, [
        ("knob1", "comp1"), ("knob2", "comp2"), ("knob3", "comp3"),
    ]),
    ("OD/DS", "odds_sw", "odds_type", enums.OD_DS_TYPES, [
        ("DRIVE", "odds1"), ("TONE", "odds2"), ("LEVEL", "odds3"),
    ]),
    ("PREAMP", "amp_sw", "amp_type", enums.PREAMP_TYPES, [
        ("GAIN", "amp1"), ("BASS", "amp2"), ("MIDDLE", "amp3"),
        ("TREBLE", "amp4"), ("LEVEL", "amp5"),
    ]),
    ("MOD", "mod_sw", "mod_type", enums.MOD_TYPES, [
        ("knob1", "mod1"), ("knob2", "mod2"), ("knob3", "mod3"),
    ]),
    ("EQ/FX2", "fx2_sw", "fx2_type", enums.EQ_FX2_TYPES, [
        ("knob1", "fx2_1"), ("knob2", "fx2_2"),
        ("knob3", "fx2_3"), ("knob4", "fx2_4"),
    ]),
    ("DELAY", "dly_sw", "dly_type", enums.DELAY_TYPES, [
        ("TIME", "dly1"), ("FEEDBACK", "dly2"), ("E.LEVEL", "dly3"),
    ]),
    ("REVERB", "rev_sw", "rev_type", enums.REVERB_TYPES, [
        ("LEVEL", "rev"),
    ]),
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

    for label, sw_key, type_key, type_table, knobs in _BLOCKS:
        on = params.get(sw_key) == "1"
        type_name = _type_name(params.get(type_key, "0"), type_table)
        head = f"  [{'ON ' if on else 'off'}] {label:<9} {type_name}"
        if not on or not knobs:
            lines.append(head)
            continue
        lines.append(head)
        for klabel, kparam in knobs:
            lines.append(f"           {klabel:<8} {params.get(kparam, '?')}")
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
