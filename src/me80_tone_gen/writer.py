"""semantic → ME-80 params → .tsl writer.

Pipeline:
    SemanticPatch  →  82-key params dict  →  patch object  →  liveset object  →  JSON file

Everything here is pure (no I/O) except `write_tsl`, which is the one filesystem
touch-point.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from . import enums
from .defaults import default_params
from .schema import SemanticPatch


def encode_name(name: str) -> tuple[dict[str, str], str]:
    """Encode a patch name three ways at once.

    The ME-80 stores the name as 16 separate ASCII-code strings (`name1`–`name16`)
    AND as a 16-char `patchname` string AND as the patch-level `name` field. All
    three must agree, so we compute them together.

    Returns: (name1..name16 mapping, 16-char space-padded string).
    """
    padded = name[:16].ljust(16)
    codes = {f"name{i + 1}": str(ord(c)) for i, c in enumerate(padded)}
    return codes, padded


def new_id(rng: random.Random | None = None) -> str:
    """Generate a 10-digit numeric string id (matches real exports)."""
    r = rng or random
    return str(r.randint(10**9, 10**10 - 1))


def _clamp_knob(v: int) -> str:
    """Clamp a knob value to 0..99 and stringify (the .tsl storage form).

    The ME-80 hardware writes 99 when a knob is at physical maximum (verified
    against a deliberate max-knob export from Cameron's pedal). BTS will accept
    100 on import, but we match hardware behaviour to keep round-trips clean.
    """
    return str(max(0, min(99, int(v))))


def _sw(enabled: bool) -> str:
    return "1" if enabled else "0"


def semantic_to_params(semantic: SemanticPatch) -> dict[str, Any]:
    """Translate a SemanticPatch into the 82-key params dict.

    Starts from the §3.4 default template; overrides the slots the LLM specified.
    Type names map to decimal-string indices via the §4 enum tables.
    """
    p = default_params()

    name_codes, padded = encode_name(semantic.patch_name)
    p.update(name_codes)
    p["patchname"] = padded

    # Preamp (always on)
    p["amp_sw"] = _sw(semantic.preamp.enabled)
    p["amp_type"] = enums.name_to_index(semantic.preamp.type, enums.PREAMP_INDEX)
    p["amp1"] = _clamp_knob(semantic.preamp.gain)
    p["amp2"] = _clamp_knob(semantic.preamp.bass)
    p["amp3"] = _clamp_knob(semantic.preamp.middle)
    p["amp4"] = _clamp_knob(semantic.preamp.treble)
    p["amp5"] = _clamp_knob(semantic.preamp.level)

    # OD/DS
    p["odds_sw"] = _sw(semantic.od_ds.enabled)
    p["odds_type"] = enums.name_to_index(semantic.od_ds.type, enums.OD_DS_INDEX)
    p["odds1"] = _clamp_knob(semantic.od_ds.drive)
    p["odds2"] = _clamp_knob(semantic.od_ds.tone)
    p["odds3"] = _clamp_knob(semantic.od_ds.level)

    # Comp / FX1 (generic 3-slot knobs — meanings vary by type)
    p["comp_sw"] = _sw(semantic.comp.enabled)
    p["comp_type"] = enums.name_to_index(semantic.comp.type, enums.COMP_FX1_INDEX)
    p["comp1"] = _clamp_knob(semantic.comp.knob1)
    p["comp2"] = _clamp_knob(semantic.comp.knob2)
    p["comp3"] = _clamp_knob(semantic.comp.knob3)

    # Mod
    p["mod_sw"] = _sw(semantic.mod.enabled)
    p["mod_type"] = enums.name_to_index(semantic.mod.type, enums.MOD_INDEX)
    p["mod1"] = _clamp_knob(semantic.mod.knob1)
    p["mod2"] = _clamp_knob(semantic.mod.knob2)
    p["mod3"] = _clamp_knob(semantic.mod.knob3)

    # EQ / FX2
    p["fx2_sw"] = _sw(semantic.eq_fx2.enabled)
    p["fx2_type"] = enums.name_to_index(semantic.eq_fx2.type, enums.EQ_FX2_INDEX)
    p["fx2_1"] = _clamp_knob(semantic.eq_fx2.knob1)
    p["fx2_2"] = _clamp_knob(semantic.eq_fx2.knob2)
    p["fx2_3"] = _clamp_knob(semantic.eq_fx2.knob3)
    p["fx2_4"] = _clamp_knob(semantic.eq_fx2.knob4)

    # Delay
    p["dly_sw"] = _sw(semantic.delay.enabled)
    p["dly_type"] = enums.name_to_index(semantic.delay.type, enums.DELAY_INDEX)
    p["dly1"] = _clamp_knob(semantic.delay.time)
    p["dly2"] = _clamp_knob(semantic.delay.feedback)
    p["dly3"] = _clamp_knob(semantic.delay.e_level)

    # Reverb (single-knob LEVEL)
    p["rev_sw"] = _sw(semantic.reverb.enabled)
    p["rev_type"] = enums.name_to_index(semantic.reverb.type, enums.REVERB_INDEX)
    p["rev"] = _clamp_knob(semantic.reverb.level)

    # Pedal FX (no stored knob trio)
    p["pdlfx_sw"] = _sw(semantic.pedal_fx.enabled)
    p["pdlfx_type"] = enums.name_to_index(semantic.pedal_fx.type, enums.PEDAL_FX_INDEX)

    return p


def build_patch(
    semantic: SemanticPatch,
    order: int,
    liveset_id: str,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Wrap a SemanticPatch in the .tsl patch envelope."""
    params = semantic_to_params(semantic)
    padded_name = params["patchname"]
    return {
        "params": params,
        "orderNumber": order,
        "id": new_id(rng),
        "patchNo": None,
        "patchID": None,
        "logPatchName": None,
        "tcPatch": False,
        "liveSetId": liveset_id,
        "note": None,
        "name": padded_name,
    }


def build_liveset(
    patches: list[SemanticPatch],
    liveset_name: str,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Wrap a list of patches in the top-level liveset envelope.

    All patches share the same `liveSetId` — that's the spec invariant.
    """
    liveset_id = new_id(rng)
    patch_objs = [
        build_patch(s, i + 1, liveset_id, rng=rng) for i, s in enumerate(patches)
    ]
    return {
        "device": "ME-80",
        "patchList": patch_objs,
        "liveSetData": {
            "orderNumber": 1,
            "url": None,
            "id": liveset_id,
            "image": None,
            "path": None,
            "name": liveset_name,
        },
        "version": "1.0.0",
    }


def write_tsl(
    patches: list[SemanticPatch],
    liveset_name: str,
    out_path: str | Path,
    rng: random.Random | None = None,
) -> Path:
    """Write a .tsl liveset to disk and return the path."""
    liveset = build_liveset(patches, liveset_name, rng=rng)
    path = Path(out_path)
    path.write_text(json.dumps(liveset, ensure_ascii=False), encoding="utf-8")
    return path


def liveset_to_json(liveset: dict[str, Any]) -> str:
    """Serialize a liveset to a JSON string (no file write).

    Match the on-disk format (compact, no extra whitespace, UTF-8 safe).
    """
    return json.dumps(liveset, ensure_ascii=False)
