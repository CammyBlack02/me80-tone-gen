"""Tests for the knob-list renderer's per-type labels."""

from __future__ import annotations

from me80_tone_gen.renderer import render_knob_list
from me80_tone_gen.schema import SemanticPatch
from me80_tone_gen.writer import semantic_to_params
from tests.conftest import valid_patch_json


def _params(**overrides: dict) -> dict:
    payload = valid_patch_json(**overrides)
    return semantic_to_params(SemanticPatch.model_validate_json(payload))


def test_enabled_chorus_renders_real_knob_names() -> None:
    params = _params(
        mod={"enabled": True, "type": "CHORUS", "knob1": 40, "knob2": 65, "knob3": 55},
    )
    text = render_knob_list(params)
    assert "RATE" in text and "DEPTH" in text and "E.LEVEL" in text
    assert "knob1" not in text


def test_unverified_type_falls_back_to_generic_knob_names() -> None:
    params = _params(
        mod={"enabled": True, "type": "OVERTONE", "knob1": 40, "knob2": 65, "knob3": 55},
    )
    text = render_knob_list(params)
    assert "knob1" in text and "knob2" in text and "knob3" in text


def test_off_blocks_render_single_line_without_knobs() -> None:
    params = _params(
        mod={"enabled": False, "type": "CHORUS", "knob1": 40, "knob2": 65, "knob3": 55},
    )
    text = render_knob_list(params)
    mod_lines = [ln for ln in text.splitlines() if "MOD" in ln and "CHORUS" in ln]
    assert len(mod_lines) == 1
    assert "[off]" in mod_lines[0]
    assert "RATE" not in text
