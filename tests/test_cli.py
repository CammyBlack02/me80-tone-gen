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


def test_variants_flag_calls_generate_variants(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--variants 3 --pick 2 -o file.tsl writes the SECOND variant."""
    variants = [
        _valid_patch(patch_name="VARIANT A"),
        _valid_patch(patch_name="VARIANT B"),
        _valid_patch(patch_name="VARIANT C"),
    ]
    call_args: dict[str, Any] = {}

    def fake_gv(description: str, **kwargs: Any) -> list[SemanticPatch]:
        call_args["description"] = description
        call_args["kwargs"] = kwargs
        return variants

    monkeypatch.setattr("me80_tone_gen.cli.generator.generate_variants", fake_gv)

    output = tmp_path / "picked.tsl"
    rc = cli.main([
        "warm bluesy lead",
        "--variants", "3",
        "--pick", "2",
        "-o", str(output),
        "--no-recipes",
    ])
    assert rc == 0
    assert call_args["kwargs"]["n"] == 3
    assert output.exists()
    written = json.loads(output.read_text())
    patch_name = written["patchList"][0]["name"].rstrip()
    assert patch_name == "VARIANT B"


def test_variants_pick_out_of_range_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    variants = [_valid_patch(patch_name=f"V{i}") for i in range(3)]
    monkeypatch.setattr(
        "me80_tone_gen.cli.generator.generate_variants",
        lambda description, **kw: variants,
    )
    with pytest.raises(SystemExit):
        cli.main([
            "warm bluesy lead",
            "--variants", "3",
            "--pick", "9",
            "--no-recipes",
        ])
    err = capsys.readouterr().err
    assert "pick" in err.lower()


def test_variants_interactive_prompt_picks_input(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """TTY user typing '3' picks the third variant."""
    variants = [_valid_patch(patch_name=f"V{i+1}") for i in range(3)]
    monkeypatch.setattr(
        "me80_tone_gen.cli.generator.generate_variants",
        lambda description, **kw: variants,
    )
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "3")

    output = tmp_path / "picked.tsl"
    rc = cli.main([
        "warm bluesy lead",
        "--variants", "3",
        "-o", str(output),
        "--no-recipes",
    ])
    assert rc == 0
    written = json.loads(output.read_text())
    assert written["patchList"][0]["name"].rstrip() == "V3"


def test_variants_interactive_empty_input_defaults_to_1(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    variants = [_valid_patch(patch_name=f"V{i+1}") for i in range(3)]
    monkeypatch.setattr(
        "me80_tone_gen.cli.generator.generate_variants",
        lambda description, **kw: variants,
    )
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "")

    output = tmp_path / "picked.tsl"
    rc = cli.main([
        "warm bluesy lead",
        "--variants", "3",
        "-o", str(output),
        "--no-recipes",
    ])
    assert rc == 0
    written = json.loads(output.read_text())
    assert written["patchList"][0]["name"].rstrip() == "V1"


def test_variants_json_mode_emits_all(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    variants = [_valid_patch(patch_name=f"V{i+1}") for i in range(3)]
    monkeypatch.setattr(
        "me80_tone_gen.cli.generator.generate_variants",
        lambda description, **kw: variants,
    )
    rc = cli.main([
        "warm bluesy lead",
        "--variants", "3",
        "--json",
        "--no-recipes",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert "variants" in payload
    assert len(payload["variants"]) == 3
    assert [v["patch_name"] for v in payload["variants"]] == ["V1", "V2", "V3"]
