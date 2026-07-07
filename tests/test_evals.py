"""Data tests for evals/cases.json and the eval harness's check logic.

The harness itself (scripts/run_eval.py) hits real Ollama and is a manual
tool; these tests only pin the parts that can rot silently — assertion paths
that no longer resolve against SemanticPatch, unknown ops, malformed cases.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from tests.conftest import valid_patch

_REPO = Path(__file__).resolve().parent.parent
_CASES = _REPO / "evals" / "cases.json"


def _load_harness():
    spec = importlib.util.spec_from_file_location(
        "run_eval", _REPO / "scripts" / "run_eval.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cases() -> list[dict]:
    return json.loads(_CASES.read_text(encoding="utf-8"))["cases"]


def test_case_ids_unique(cases: list[dict]) -> None:
    ids = [c["id"] for c in cases]
    assert len(set(ids)) == len(ids)


def test_every_assertion_path_resolves_and_op_is_known(cases: list[dict]) -> None:
    """A renamed schema field must fail here, not mid-eval against a live model."""
    harness = _load_harness()
    patch = valid_patch()
    for case in cases:
        assert case["description"].strip()
        for assertion in case["expect"]:
            harness._resolve(patch, assertion["path"])  # raises if the path is stale
            harness._check(patch, assertion)  # raises on unknown op


def test_check_ops_behave() -> None:
    harness = _load_harness()
    patch = valid_patch()  # reverb: SPRING, level 30, enabled True
    assert harness._check(patch, {"path": "reverb.type", "op": "equals", "value": "SPRING"})
    assert harness._check(patch, {"path": "reverb.level", "op": "lte", "value": 30})
    assert not harness._check(patch, {"path": "reverb.level", "op": "gte", "value": 31})
    assert harness._check(patch, {"path": "preamp.type", "op": "in", "value": ["LEAD", "CLEAN"]})
    with pytest.raises(ValueError):
        harness._check(patch, {"path": "reverb.level", "op": "near", "value": 30})
