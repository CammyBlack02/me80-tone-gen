"""Writer tests anchored to the real Contra_1.tsl export.

Phase 1 / spec §8.1: round-trip a real `.tsl` and prove the writer emits
the same structural shape BTS does. Catches drifts in:
- top-level keys
- patch envelope keys
- the 82-key params set
- name encoding (three places agree)
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from me80_tone_gen.defaults import default_params
from me80_tone_gen.enums import (
    OD_DS_TYPES,
    PREAMP_TYPES,
    REVERB_TYPES,
)
from me80_tone_gen.schema import (
    CompBlock,
    DelayBlock,
    EqFx2Block,
    ModBlock,
    OdDsBlock,
    PedalFxBlock,
    PreampBlock,
    ReverbBlock,
    SemanticPatch,
)
from me80_tone_gen.writer import (
    build_liveset,
    build_patch,
    encode_name,
    semantic_to_params,
)

REFERENCE_TSL = Path(__file__).resolve().parents[1] / "data" / "Contra_1.tsl"


@pytest.fixture(scope="module")
def reference() -> dict:
    """The real Contra_1.tsl liveset, parsed once per test module."""
    return json.loads(REFERENCE_TSL.read_text(encoding="utf-8"))


def _seeded_rng() -> random.Random:
    """Deterministic RNG so tests are reproducible."""
    return random.Random(42)


def _make_semantic(name: str = "TEST", **overrides) -> SemanticPatch:
    """Build a fully-populated SemanticPatch — every block must be present now."""
    defaults: dict = {
        "patch_name": name,
        "preamp": PreampBlock(type="METAL", gain=75, bass=60, middle=35, treble=65, level=50),
        "od_ds": OdDsBlock(enabled=True, type="T-SCREAM", drive=40, tone=60, level=55),
        "comp": CompBlock(enabled=False, type="COMP", knob1=50, knob2=50, knob3=50),
        "mod": ModBlock(enabled=False, type="CHORUS", knob1=50, knob2=50, knob3=50),
        "eq_fx2": EqFx2Block(enabled=False, type="EQ", knob1=50, knob2=50, knob3=50, knob4=50),
        "delay": DelayBlock(enabled=False, type="100-600 ms", time=50, feedback=50, e_level=50),
        "reverb": ReverbBlock(enabled=True, type="ROOM", level=20),
        "pedal_fx": PedalFxBlock(enabled=False, type="WAH"),
        "rationale": "",
    }
    defaults.update(overrides)
    return SemanticPatch(**defaults)


# ---------- structural conformance ----------


def test_reference_file_loads(reference: dict) -> None:
    assert reference["device"] == "ME-80"
    assert len(reference["patchList"]) == 10
    assert reference["version"] == "1.0.0"


def test_top_level_keys_match_reference(reference: dict) -> None:
    """Our liveset envelope has the same top-level keys as a real export."""
    ours = build_liveset([_make_semantic()], "Test", rng=_seeded_rng())
    assert set(ours.keys()) == set(reference.keys())


def test_liveset_data_keys_match_reference(reference: dict) -> None:
    ours = build_liveset([_make_semantic()], "Test", rng=_seeded_rng())
    assert set(ours["liveSetData"].keys()) == set(reference["liveSetData"].keys())


def test_patch_envelope_keys_match_reference(reference: dict) -> None:
    """Every reference patch object has the same envelope keys ours does."""
    ours = build_patch(_make_semantic(), order=1, liveset_id="0000000001", rng=_seeded_rng())
    expected = set(ours.keys())
    for ref_patch in reference["patchList"]:
        assert set(ref_patch.keys()) == expected, (
            f"key mismatch on patch {ref_patch.get('name')!r}"
        )


def test_default_params_keys_match_every_reference_patch(reference: dict) -> None:
    """Our 82-key default template matches each real patch's params key set."""
    expected = set(default_params().keys())
    for ref_patch in reference["patchList"]:
        ref_keys = set(ref_patch["params"].keys())
        missing = expected - ref_keys
        extra = ref_keys - expected
        assert not missing and not extra, (
            f"params key drift on {ref_patch.get('name')!r}: "
            f"missing={sorted(missing)}, extra={sorted(extra)}"
        )


def test_param_value_types_match_reference(reference: dict) -> None:
    """Every params value in a real patch is a str or None — same as ours."""
    ours = semantic_to_params(_make_semantic())
    for ref_patch in reference["patchList"]:
        for k, v in ref_patch["params"].items():
            assert v is None or isinstance(v, str), (
                f"{ref_patch['name']!r}: {k}={v!r} is not str/None"
            )
            our_v = ours.get(k)
            assert our_v is None or isinstance(our_v, str)


# ---------- name encoding ----------


def test_name_encoded_three_ways_agree(reference: dict) -> None:
    """In real data, name1..16 / patchname / patch.name encode the same string."""
    for ref_patch in reference["patchList"]:
        params = ref_patch["params"]
        from_codes = "".join(chr(int(params[f"name{i}"])) for i in range(1, 17))
        assert from_codes == params["patchname"] == ref_patch["name"], (
            f"name disagreement on {ref_patch['name']!r}"
        )


def test_encode_name_handles_short_name() -> None:
    codes, padded = encode_name("AC")
    assert padded == "AC" + " " * 14
    assert codes["name1"] == "65"
    assert codes["name2"] == "67"
    assert codes["name3"] == "32"  # space
    assert codes["name16"] == "32"


def test_encode_name_truncates_long_name() -> None:
    codes, padded = encode_name("THIS NAME IS WAY TOO LONG")
    assert padded == "THIS NAME IS WAY"
    assert len(padded) == 16


# ---------- semantic mapping ----------


def test_semantic_to_params_preamp_type_index() -> None:
    """Preamp type names map to the right index from §4."""
    for name in PREAMP_TYPES:
        sem = _make_semantic(
            preamp=PreampBlock(type=name, gain=50, bass=50, middle=50, treble=50, level=50),
        )
        params = semantic_to_params(sem)
        assert params["amp_type"] == str(PREAMP_TYPES.index(name))


def test_semantic_to_params_od_ds_index() -> None:
    for name in OD_DS_TYPES:
        sem = _make_semantic(
            od_ds=OdDsBlock(enabled=True, type=name, drive=50, tone=50, level=50),
        )
        params = semantic_to_params(sem)
        assert params["odds_type"] == str(OD_DS_TYPES.index(name))


def test_semantic_to_params_reverb_index() -> None:
    for name in REVERB_TYPES:
        sem = _make_semantic(
            reverb=ReverbBlock(enabled=True, type=name, level=50),
        )
        params = semantic_to_params(sem)
        assert params["rev_type"] == str(REVERB_TYPES.index(name))


def test_knob_values_clamped_to_hardware_max() -> None:
    """Knob clamps at 99 — verified against a deliberate max-knob export from the pedal."""
    # The schema rejects 100 outright; the writer also clamps anything that
    # might sneak past the schema (e.g. from a recipe seed loaded raw).
    sem = _make_semantic(
        preamp=PreampBlock(type="METAL", gain=99, bass=0, middle=50, treble=50, level=50),
    )
    params = semantic_to_params(sem)
    assert params["amp1"] == "99"
    assert params["amp2"] == "0"


def test_no_reference_knob_value_exceeds_99(reference: dict) -> None:
    """Sanity check: no knob in real exports goes above 99 either."""
    knob_keys = {
        "comp1", "comp2", "comp3", "odds1", "odds2", "odds3",
        "amp1", "amp2", "amp3", "amp4", "amp5",
        "mod1", "mod2", "mod3",
        "fx2_1", "fx2_2", "fx2_3", "fx2_4",
        "dly1", "dly2", "dly3", "rev",
    }
    for ref_patch in reference["patchList"]:
        for key in knob_keys:
            v = ref_patch["params"][key]
            assert 0 <= int(v) <= 99, f"{ref_patch['name']!r}: {key}={v} out of 0-99"


# ---------- liveset invariants ----------


def test_liveset_id_equals_every_patch_liveset_id() -> None:
    """Spec §3.2 invariant: every patch's liveSetId == top liveSetData.id."""
    patches = [_make_semantic(f"P{i}") for i in range(4)]
    ls = build_liveset(patches, "Bank A", rng=_seeded_rng())
    lid = ls["liveSetData"]["id"]
    for patch in ls["patchList"]:
        assert patch["liveSetId"] == lid


def test_reference_liveset_id_invariant_holds(reference: dict) -> None:
    """Sanity check the same invariant on the real file."""
    lid = reference["liveSetData"]["id"]
    for patch in reference["patchList"]:
        assert patch["liveSetId"] == lid


def test_order_numbers_are_one_based_and_dense() -> None:
    patches = [_make_semantic(f"P{i}") for i in range(4)]
    ls = build_liveset(patches, "Bank A", rng=_seeded_rng())
    assert [p["orderNumber"] for p in ls["patchList"]] == [1, 2, 3, 4]


def test_patch_ids_are_unique_within_liveset() -> None:
    patches = [_make_semantic(f"P{i}") for i in range(10)]
    ls = build_liveset(patches, "Big", rng=_seeded_rng())
    ids = [p["id"] for p in ls["patchList"]]
    assert len(set(ids)) == len(ids)


# ---------- json shape (compatibility surface) ----------


def test_writer_output_loads_as_json(tmp_path) -> None:
    """Final smoke: write to disk, read back, structure intact."""
    from me80_tone_gen.writer import write_tsl

    sem = _make_semantic("ROUNDTRIP")
    out = write_tsl([sem], "RTrip", tmp_path / "out.tsl", rng=_seeded_rng())
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["device"] == "ME-80"
    assert data["patchList"][0]["name"].rstrip() == "ROUNDTRIP"
