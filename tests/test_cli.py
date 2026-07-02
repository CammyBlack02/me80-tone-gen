"""CLI-level tests for tone-gen.

These exercise argparse handling and the multi-variant execution paths using a
patched generator so no real Ollama call is made.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from me80_tone_gen import cli
from me80_tone_gen.schema import SemanticPatch


def _valid_patch(**overrides: Any) -> SemanticPatch:
    payload = {
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
    return SemanticPatch.model_validate(payload)


def test_batch_and_variants_rejected(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    batch_file = tmp_path / "batch.txt"
    batch_file.write_text("clean lead\ndjent rhythm\n")
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--batch", str(batch_file), "--variants", "3", "-"])
    assert exc_info.value.code != 0
    err = capsys.readouterr().err
    assert "mutually exclusive" in err.lower()
