#!/usr/bin/env python3
"""Structural eval harness — measures generation quality against evals/cases.json.

This hits the REAL Ollama server (it is a manual smoke tool, not a unit test)
and scores pass-rates, because generation is stochastic: run each case N times
and report the fraction of assertions that held. Use it to A/B prompt changes,
recipe seeds, or models instead of eyeballing:

    python scripts/run_eval.py                       # default model, 3 runs/case
    python scripts/run_eval.py --runs 5 --no-recipes # measure the raw prompt
    python scripts/run_eval.py --model llama3.1:8b   # compare a model
    python scripts/run_eval.py --only djent-dry-tight
    python scripts/run_eval.py --out before.json     # save for diffing

Interpretation: a case that scores 3/3 on every assertion is solid; one that
flips run-to-run is where the prompt (or a recipe) needs work. Compare --out
snapshots before/after a change to see what moved.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from me80_tone_gen import generator  # noqa: E402
from me80_tone_gen.recipes import load_recipes, match_recipe  # noqa: E402
from me80_tone_gen.schema import SemanticPatch  # noqa: E402

DEFAULT_CASES = Path(__file__).resolve().parent.parent / "evals" / "cases.json"


def _resolve(patch: SemanticPatch, path: str) -> Any:
    value: Any = patch
    for part in path.split("."):
        value = getattr(value, part)
    return value


def _check(patch: SemanticPatch, assertion: dict[str, Any]) -> bool:
    actual = _resolve(patch, assertion["path"])
    op, expected = assertion["op"], assertion["value"]
    if op == "equals":
        return actual == expected
    if op == "in":
        return actual in expected
    if op == "lte":
        return actual <= expected
    if op == "gte":
        return actual >= expected
    raise ValueError(f"unknown op {op!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--model", default=generator.DEFAULT_MODEL)
    parser.add_argument("--runs", type=int, default=3, help="Generations per case (default 3).")
    parser.add_argument("--no-recipes", action="store_true",
                        help="Skip recipe seeding to measure the raw prompt.")
    parser.add_argument("--only", default=None, help="Run a single case by id.")
    parser.add_argument("--out", type=Path, default=None,
                        help="Write per-assertion results as JSON for diffing.")
    args = parser.parse_args(argv)

    cases = json.loads(args.cases.read_text(encoding="utf-8"))["cases"]
    if args.only:
        cases = [c for c in cases if c["id"] == args.only]
        if not cases:
            print(f"error: no case with id {args.only!r}", file=sys.stderr)
            return 2

    recipes = [] if args.no_recipes else load_recipes()

    results: list[dict[str, Any]] = []
    total_passed = total_checks = 0

    for case in cases:
        recipe = match_recipe(case["description"], recipes) if recipes else None
        seed = recipe.model_dump(exclude={"aliases"}) if recipe else None
        tally = {a["path"]: 0 for a in case["expect"]}
        failures = 0

        for _ in range(args.runs):
            try:
                patch = generator.generate_patch(
                    case["description"], model=args.model, recipe_seed=seed,
                )
            except generator.GenerationError as exc:
                print(f"  generation failed: {exc}", file=sys.stderr)
                failures += 1
                continue
            for assertion in case["expect"]:
                if _check(patch, assertion):
                    tally[assertion["path"]] += 1

        completed = args.runs - failures
        case_passed = sum(tally.values())
        case_checks = len(case["expect"]) * completed
        total_passed += case_passed
        total_checks += case_checks

        seed_note = f" [recipe: {recipe.id}]" if recipe else ""
        rate = f"{case_passed}/{case_checks}" if case_checks else "no runs completed"
        print(f"{case['id']:<24} {rate}{seed_note}")
        for assertion in case["expect"]:
            hits = tally[assertion["path"]]
            marker = "ok  " if hits == completed and completed > 0 else "WEAK"
            print(f"    {marker} {assertion['path']} {assertion['op']} "
                  f"{assertion['value']} -> {hits}/{completed}")

        results.append({
            "id": case["id"],
            "recipe": recipe.id if recipe else None,
            "runs": args.runs,
            "generation_failures": failures,
            "assertions": [
                {**a, "passes": tally[a["path"]]} for a in case["expect"]
            ],
        })

    if total_checks:
        print(f"\nOverall: {total_passed}/{total_checks} "
              f"({100 * total_passed / total_checks:.0f}%) — model={args.model}, "
              f"recipes={'off' if args.no_recipes else 'on'}, runs={args.runs}")
    if args.out:
        args.out.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
        print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
