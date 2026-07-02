"""Generator tests with a fake Ollama client — no real model required.

These verify the retry-on-invalid-JSON loop and the error-payload propagation.
End-to-end with a real model is a manual smoke test, not a unit test.
"""

from __future__ import annotations

import json
import threading
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


class ThreadSafeFakeOllama:
    """Fake Ollama client whose response depends on the temperature it was called with.

    Use this when `generate_variants` calls chat() from multiple threads — the
    stock FakeOllama pops from a list which races. Keyed by temperature so tests
    can verify order-preservation and per-variant temperature dispatch.
    """

    def __init__(self, responses_by_temp: dict[float, str]) -> None:
        self.responses_by_temp = responses_by_temp
        self.calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def chat(self, **kwargs: Any) -> dict[str, Any]:
        with self._lock:
            self.calls.append(kwargs)
        temp = kwargs["options"]["temperature"]
        if temp not in self.responses_by_temp:
            raise AssertionError(
                f"ThreadSafeFakeOllama got temperature {temp}, "
                f"expected one of {sorted(self.responses_by_temp)}"
            )
        return {"message": {"content": self.responses_by_temp[temp]}}


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
# These tests guard against refactor-drift in the few-shot examples — not
# the model's runtime behaviour (that's a manual smoke).


@pytest.mark.parametrize(
    "label,required,case_insensitive",
    [
        # Six reference genres must appear by name so the few-shot block
        # actually covers the territory we claim it does.
        ("reference genres",
         ["djent", "country", "shoegaze", "post-rock", "funk", "stoner"],
         True),
        # Preamp diversity — at least METAL, CLEAN, LEAD, STACK so the model
        # sees four distinct example shapes, not one repeated.
        ("preamp diversity",
         ["METAL", "CLEAN", "LEAD", "STACK"],
         False),
        # Supporting effects — T-SCREAM (djent-tightening), FUZZ (stoner),
        # CHORUS (shoegaze) prove non-preamp choices are exemplified too.
        ("supporting effects",
         ["T-SCREAM", "FUZZ", "CHORUS"],
         False),
    ],
)
def test_system_prompt_contains(label: str, required: list[str], case_insensitive: bool) -> None:
    haystack = SYSTEM_PROMPT.lower() if case_insensitive else SYSTEM_PROMPT
    needles = [s.lower() if case_insensitive else s for s in required]
    missing = [n for n in needles if n not in haystack]
    assert not missing, f"{label}: missing {missing}"


def test_system_prompt_demonstrates_off_state_concretely() -> None:
    """Each example must show multiple blocks in the off state.

    The biggest pre-few-shot failure mode was the model leaving important
    blocks off (djent missing T-SCREAM) or enabling irrelevant ones (djent
    with delay). Counting `: off` block-lines proves the examples *show*
    off-state rather than only *describing* it — phrase-tolerant guard.
    """
    off_block_lines = SYSTEM_PROMPT.count(": off")
    # 6 examples × at least ~3 off-blocks each is a generous floor; we
    # currently emit 27.
    assert off_block_lines >= 18, (
        f"expected at least 18 ': off' block lines in the few-shot examples, "
        f"got {off_block_lines}"
    )


# ---------- multi-variant helpers ----------

from me80_tone_gen.generator import _evenly_spaced_temperatures


@pytest.mark.parametrize(
    "n,expected",
    [
        (1, [0.2]),
        (2, [0.2, 0.8]),
        (3, [0.2, 0.5, 0.8]),
        (5, [0.2, 0.35, 0.5, 0.65, 0.8]),
    ],
)
def test_evenly_spaced_temperatures(n: int, expected: list[float]) -> None:
    result = _evenly_spaced_temperatures(n)
    assert len(result) == n
    for got, want in zip(result, expected, strict=True):
        assert got == pytest.approx(want, abs=1e-9)


from me80_tone_gen.generator import generate_variants


def test_generate_variants_returns_n_patches() -> None:
    fake = ThreadSafeFakeOllama({
        0.2: _valid_patch_json(patch_name="VARIANT A"),
        0.5: _valid_patch_json(patch_name="VARIANT B"),
        0.8: _valid_patch_json(patch_name="VARIANT C"),
    })
    variants = generate_variants("bluesy lead", n=3, client=fake, retries=0)
    assert len(variants) == 3
    assert all(isinstance(v, SemanticPatch) for v in variants)


def test_generate_variants_preserves_input_order() -> None:
    """Results returned in temperature order, not thread-completion order."""
    fake = ThreadSafeFakeOllama({
        0.2: _valid_patch_json(patch_name="LOW TEMP"),
        0.5: _valid_patch_json(patch_name="MID TEMP"),
        0.8: _valid_patch_json(patch_name="HIGH TEMP"),
    })
    variants = generate_variants("bluesy lead", n=3, client=fake, retries=0)
    assert variants[0].patch_name == "LOW TEMP"
    assert variants[1].patch_name == "MID TEMP"
    assert variants[2].patch_name == "HIGH TEMP"


def test_generate_variants_temperature_per_call() -> None:
    """Each variant call gets its own temperature; all temperatures used exactly once."""
    fake = ThreadSafeFakeOllama({
        0.2: _valid_patch_json(patch_name="A"),
        0.5: _valid_patch_json(patch_name="B"),
        0.8: _valid_patch_json(patch_name="C"),
    })
    generate_variants("bluesy lead", n=3, client=fake, retries=0)
    seen_temps = sorted(call["options"]["temperature"] for call in fake.calls)
    assert seen_temps == [0.2, 0.5, 0.8]


def test_generate_variants_explicit_temperatures() -> None:
    """Explicit temperatures= override the default spacing."""
    fake = ThreadSafeFakeOllama({
        0.1: _valid_patch_json(patch_name="A"),
        0.9: _valid_patch_json(patch_name="B"),
    })
    variants = generate_variants(
        "bluesy lead", n=2, temperatures=[0.1, 0.9], client=fake, retries=0
    )
    assert len(variants) == 2
    seen_temps = sorted(call["options"]["temperature"] for call in fake.calls)
    assert seen_temps == [0.1, 0.9]


def test_generate_variants_temperature_length_mismatch_raises() -> None:
    """Explicit temperatures with wrong length raises before any Ollama call."""
    fake = ThreadSafeFakeOllama({})
    with pytest.raises(ValueError, match="does not match"):
        generate_variants(
            "bluesy lead", n=3, temperatures=[0.2, 0.5], client=fake, retries=0
        )
    assert fake.calls == []  # no calls made
