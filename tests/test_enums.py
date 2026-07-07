"""Tests for the enum tables and the per-type knob-label tables."""

from __future__ import annotations

import pytest

from me80_tone_gen import enums

_BLOCK_CASES = [
    (enums.COMP_FX1_KNOBS, enums.COMP_FX1_TYPES, 3),
    (enums.MOD_KNOBS, enums.MOD_TYPES, 3),
    (enums.EQ_FX2_KNOBS, enums.EQ_FX2_TYPES, 4),
]


@pytest.mark.parametrize("table,types,n_knobs", _BLOCK_CASES)
def test_knob_tables_reference_only_legal_types(
    table: dict[str, tuple[str, ...]], types: tuple[str, ...], n_knobs: int
) -> None:
    """A typo'd type name in a knob table would silently never match."""
    legal = {t.upper() for t in types}
    for type_name in table:
        assert type_name in legal, f"{type_name!r} is not a legal type"


@pytest.mark.parametrize("table,types,n_knobs", _BLOCK_CASES)
def test_knob_tables_have_full_label_sets(
    table: dict[str, tuple[str, ...]], types: tuple[str, ...], n_knobs: int
) -> None:
    """Each entry must label every knob — the renderer zips strictly."""
    for type_name, labels in table.items():
        assert len(labels) == n_knobs, f"{type_name}: {len(labels)} labels, want {n_knobs}"


def test_knob_labels_known_type() -> None:
    assert enums.knob_labels(enums.MOD_KNOBS, "CHORUS", 3) == ("RATE", "DEPTH", "E.LEVEL")


def test_knob_labels_is_case_insensitive() -> None:
    assert enums.knob_labels(enums.MOD_KNOBS, "chorus", 3) == ("RATE", "DEPTH", "E.LEVEL")


def test_knob_labels_unknown_type_falls_back_to_generic() -> None:
    """Types without verified labels must render generically, never wrongly."""
    assert enums.knob_labels(enums.MOD_KNOBS, "OVERTONE", 3) == ("knob1", "knob2", "knob3")
    assert enums.knob_labels(enums.EQ_FX2_KNOBS, "BOOST", 4) == (
        "knob1", "knob2", "knob3", "knob4",
    )


def test_knob_meanings_by_position_groups_types() -> None:
    line = enums.knob_meanings_by_position(enums.MOD_KNOBS, 0)
    assert "RATE" in line
    assert "KEY (HARMONIST)" in line
    assert "TIME (DELAY)" in line
    assert "PITCH (PITCH SHIFT)" in line
