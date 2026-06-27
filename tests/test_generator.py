"""Generator tests with a fake Ollama client — no real model required.

These verify the retry-on-invalid-JSON loop and the error-payload propagation.
End-to-end with a real model is a manual smoke test, not a unit test.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from me80_tone_gen.generator import SYSTEM_PROMPT, GenerationError, generate_patch
from me80_tone_gen.schema import SemanticPatch


class FakeOllama:
    """Returns successive canned content strings as Ollama responses."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("FakeOllama exhausted")
        return {"message": {"content": self.responses.pop(0)}}


def _valid_patch_json(**overrides: Any) -> str:
    payload = {
        "patch_name": "BLUES LEAD",
        "preamp": {"enabled": True, "type": "LEAD", "gain": 60, "bass": 50, "middle": 60, "treble": 55, "level": 50},
        "od_ds": {"enabled": True, "type": "OVERDRIVE", "drive": 35, "tone": 55, "level": 55},
        "comp": {"enabled": False, "type": "COMP", "knob1": 50, "knob2": 50, "knob3": 50},
        "mod": {"enabled": False, "type": "CHORUS", "knob1": 50, "knob2": 50, "knob3": 50},
        "eq_fx2": {"enabled": False, "type": "EQ", "knob1": 50, "knob2": 50, "knob3": 50, "knob4": 50},
        "delay": {"enabled": False, "type": "100-600 ms", "time": 50, "feedback": 50, "e_level": 50},
        "reverb": {"enabled": True, "type": "SPRING", "level": 30},
        "pedal_fx": {"enabled": False, "type": "WAH"},
        "rationale": "test",
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_generate_patch_returns_validated_semantic() -> None:
    fake = FakeOllama([_valid_patch_json()])
    patch = generate_patch("warm bluesy lead", client=fake, retries=0)
    assert isinstance(patch, SemanticPatch)
    assert patch.patch_name == "BLUES LEAD"
    assert patch.preamp.type == "LEAD"
    assert patch.reverb.type == "SPRING"


def test_generate_patch_retries_on_invalid_json() -> None:
    """First response invalid → second one succeeds. Retry budget consumed."""
    fake = FakeOllama(["not json at all", _valid_patch_json()])
    patch = generate_patch("warm bluesy lead", client=fake, retries=1)
    assert patch.patch_name == "BLUES LEAD"
    assert len(fake.calls) == 2


def test_generate_patch_retries_on_invalid_enum() -> None:
    """Structurally-valid JSON but illegal enum value → triggers retry."""
    bad = _valid_patch_json(
        preamp={"enabled": True, "type": "NOT A REAL AMP", "gain": 50, "bass": 50,
                "middle": 50, "treble": 50, "level": 50},
    )
    fake = FakeOllama([bad, _valid_patch_json()])
    patch = generate_patch("warm bluesy lead", client=fake, retries=1)
    assert patch.preamp.type == "LEAD"
    assert len(fake.calls) == 2


def test_generate_patch_raises_after_retries_exhausted() -> None:
    fake = FakeOllama(["garbage", "still garbage", "more garbage"])
    with pytest.raises(GenerationError) as exc_info:
        generate_patch("warm bluesy lead", client=fake, retries=2)
    err = exc_info.value
    assert "still garbage" in err.last_raw or "more garbage" in err.last_raw
    assert err.last_error


def test_schema_passed_to_ollama_format() -> None:
    """The Pydantic JSON schema must be passed as `format=` for constrained decoding."""
    fake = FakeOllama([_valid_patch_json()])
    generate_patch("test", client=fake, retries=0)
    sent_format = fake.calls[0]["format"]
    assert sent_format["title"] == "SemanticPatch" or "properties" in sent_format


def test_temperature_and_model_propagate() -> None:
    fake = FakeOllama([_valid_patch_json()])
    generate_patch("test", client=fake, model="llama3.1:8b", temperature=0.7, retries=0)
    assert fake.calls[0]["model"] == "llama3.1:8b"
    assert fake.calls[0]["options"]["temperature"] == 0.7


# ---------- system prompt structure ----------
#
# The SYSTEM_PROMPT contains few-shot examples teaching the model the *pattern*
# of which blocks belong on/off per genre. These tests guard the structure
# against accidental drift in refactors. They don't test the model's behavior
# (that's a manual smoke).


def test_system_prompt_contains_each_reference_genre() -> None:
    """Each of the 6 reference genres must appear by name in the prompt."""
    expected_genres = ["djent", "country", "shoegaze", "post-rock", "funk", "stoner"]
    lowered = SYSTEM_PROMPT.lower()
    missing = [g for g in expected_genres if g not in lowered]
    assert not missing, f"missing reference genres: {missing}"


def test_system_prompt_demonstrates_diverse_preamp_choices() -> None:
    """Reference examples should cover distinct preamp types, not just one."""
    # At minimum: METAL (djent/stoner), CLEAN (country/funk/post-rock), LEAD
    # (shoegaze), STACK (stoner). Without these, the model has only one
    # example shape to imitate.
    for preamp_type in ("METAL", "CLEAN", "LEAD", "STACK"):
        assert preamp_type in SYSTEM_PROMPT, f"prompt missing {preamp_type} example"


def test_system_prompt_demonstrates_supporting_effect_choices() -> None:
    """Examples must show specific supporting-effect patterns, not just preamps."""
    # T-SCREAM (the djent-tightening pattern) and FUZZ (stoner) are signature
    # supporting effects in the reference set; CHORUS (shoegaze) covers MOD.
    for effect in ("T-SCREAM", "FUZZ", "CHORUS"):
        assert effect in SYSTEM_PROMPT, f"prompt missing {effect} example"


def test_system_prompt_emphasises_what_blocks_to_leave_off() -> None:
    """Defining-by-absence guidance must be present.

    The biggest failure mode pre-few-shot was the model leaving important
    effects off (djent missing T-SCREAM) or enabling irrelevant ones (djent
    with delay). The prompt now teaches the off-state as actively as the on.
    """
    lowered = SYSTEM_PROMPT.lower()
    assert "off" in lowered
    assert "many genres are defined by what's off" in lowered
