"""Web API tests via FastAPI's TestClient.

We patch `generator.generate_variants` so no real Ollama call is made.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from me80_tone_gen import web
from me80_tone_gen.schema import SemanticPatch


def _valid_patch(**overrides: Any) -> SemanticPatch:
    payload = {
        "patch_name": "TEST",
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


@pytest.fixture
def client() -> TestClient:
    return TestClient(web.app)


def test_generate_single_variant_response_shape(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "me80_tone_gen.web.generator.generate_variants",
        lambda description, **kw: [_valid_patch(patch_name="ONE")],
    )
    response = client.post("/api/generate", json={"description": "bluesy lead"})
    assert response.status_code == 200
    body = response.json()
    assert "variants" in body
    assert len(body["variants"]) == 1
    v = body["variants"][0]
    assert v["patch"]["patch_name"] == "ONE"
    assert "knob_list_text" in v
    assert "liveset" in v


def test_generate_multi_variant_response_shape(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    variants = [_valid_patch(patch_name=f"V{i+1}") for i in range(3)]
    monkeypatch.setattr(
        "me80_tone_gen.web.generator.generate_variants",
        lambda description, **kw: variants,
    )
    response = client.post(
        "/api/generate",
        json={"description": "bluesy lead", "variants": 3},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["variants"]) == 3
    assert [v["patch"]["patch_name"] for v in body["variants"]] == ["V1", "V2", "V3"]
    for v in body["variants"]:
        assert v["liveset"]["patchList"], "each variant must carry its own single-patch liveset"


def test_generate_variants_field_validation(client: TestClient) -> None:
    response = client.post(
        "/api/generate",
        json={"description": "bluesy lead", "variants": 99},
    )
    assert response.status_code == 422  # over the ge/le=5 bound
