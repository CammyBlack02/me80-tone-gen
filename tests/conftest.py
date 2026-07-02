"""Shared test fixtures for the me80-tone-gen suite."""

from __future__ import annotations

import json as _json
from typing import Any

from me80_tone_gen.schema import SemanticPatch


def _valid_patch_payload(**overrides: Any) -> dict[str, Any]:
    """The canonical 'valid semantic patch' payload used across test files.

    Kept here so schema changes only need one fixture update.
    """
    payload: dict[str, Any] = {
        "patch_name": "TEST PATCH",
        "preamp": {"enabled": True, "type": "LEAD", "gain": 60, "bass": 50,
                   "middle": 60, "treble": 55, "level": 50},
        "od_ds": {"enabled": True, "type": "OVERDRIVE", "drive": 35,
                  "tone": 55, "level": 55},
        "comp": {"enabled": False, "type": "COMP", "knob1": 50, "knob2": 50, "knob3": 50},
        "mod": {"enabled": False, "type": "CHORUS", "knob1": 50, "knob2": 50, "knob3": 50},
        "eq_fx2": {"enabled": False, "type": "EQ", "knob1": 50, "knob2": 50,
                   "knob3": 50, "knob4": 50},
        "delay": {"enabled": False, "type": "100-600 ms", "time": 50,
                  "feedback": 50, "e_level": 50},
        "reverb": {"enabled": True, "type": "SPRING", "level": 30},
        "pedal_fx": {"enabled": False, "type": "WAH"},
        "rationale": "test",
    }
    payload.update(overrides)
    return payload


def valid_patch(**overrides: Any) -> SemanticPatch:
    """Validated SemanticPatch instance with sensible defaults."""
    return SemanticPatch.model_validate(_valid_patch_payload(**overrides))


def valid_patch_json(**overrides: Any) -> str:
    """JSON-string form of a valid semantic patch (for fake Ollama responses)."""
    return _json.dumps(_valid_patch_payload(**overrides))
