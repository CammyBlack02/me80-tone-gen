"""tone-gen CLI — thin shell over the core module.

Machine-speakable: --json emits the semantic patch as JSON, description can be
piped via stdin, real exit codes (0 ok, 1 generation failure, 2 usage error).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import generator
from .generator import DEFAULT_MODEL, DEFAULT_TEMPERATURE, GenerationError
from .recipes import Recipe, load_recipes, match_recipe
from .renderer import render_knob_list
from .schema import SemanticPatch
from .writer import build_liveset, liveset_to_json, write_tsl


def _read_description(args: argparse.Namespace) -> str:
    if args.description and args.description != "-":
        return args.description
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    raise SystemExit("error: provide a description as an argument or via stdin")


def _read_batch(path: Path) -> list[str]:
    lines = [
        ln.strip()
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    if not lines:
        raise SystemExit(f"error: batch file {path} contains no descriptions")
    return lines


def _generate_one(
    description: str,
    args: argparse.Namespace,
    recipes: list[Recipe],
) -> tuple[SemanticPatch, Recipe | None]:
    recipe = None if args.no_recipes else match_recipe(description, recipes)
    seed = recipe.model_dump(exclude={"aliases"}) if recipe else None
    patch = generator.generate_patch(
        description,
        model=args.model,
        temperature=args.temp,
        retries=args.retries,
        recipe_seed=seed,
    )
    return patch, recipe


def _liveset_name_from(args: argparse.Namespace) -> str:
    if args.liveset_name:
        return args.liveset_name
    if args.output:
        return Path(args.output).stem
    return "Generated"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tone-gen",
        description="Natural-language → Boss ME-80 patch (.tsl) generator.",
    )
    parser.add_argument(
        "description",
        nargs="?",
        help="Tone description (or '-' / omit to read from stdin).",
    )
    parser.add_argument(
        "-o", "--output",
        help="Write a .tsl liveset to this path.",
    )
    parser.add_argument(
        "--liveset-name",
        help="Name embedded in the liveset (default: output filename stem, or 'Generated').",
    )
    parser.add_argument(
        "--batch",
        type=Path,
        help="Read one description per line from this file → single multi-patch liveset.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit the semantic patch (or liveset) as JSON to stdout; no knob-list.",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Ollama model id (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--temp", type=float, default=DEFAULT_TEMPERATURE,
        help=f"Sampling temperature (default: {DEFAULT_TEMPERATURE}).",
    )
    parser.add_argument(
        "--retries", type=int, default=2,
        help="Max retries on invalid LLM output (default: 2).",
    )
    parser.add_argument(
        "--recipes", type=Path, default=None,
        help="Path to a custom recipes.json (default: packaged starter set).",
    )
    parser.add_argument(
        "--no-recipes", action="store_true",
        help="Disable recipe matching; rely purely on model knowledge.",
    )
    parser.add_argument(
        "--variants", type=int, default=1,
        help="Generate N variants at different temperatures; user picks one (default: 1).",
    )
    parser.add_argument(
        "--pick", type=int, default=None,
        help="1-indexed variant to save when --variants > 1 (non-interactive).",
    )
    parser.add_argument(
        "--temperatures", type=str, default=None,
        help="Comma-separated per-variant temperatures (must match --variants count).",
    )

    args = parser.parse_args(argv)

    recipes = [] if args.no_recipes else load_recipes(args.recipes)

    try:
        if args.batch:
            descriptions = _read_batch(args.batch)
            results = [_generate_one(d, args, recipes) for d in descriptions]
        else:
            description = _read_description(args)
            results = [_generate_one(description, args, recipes)]
    except GenerationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if exc.last_error:
            print(f"  last validation error: {exc.last_error}", file=sys.stderr)
        return 1

    patches = [r[0] for r in results]
    matched = [r[1] for r in results]

    liveset_name = _liveset_name_from(args)

    if args.output:
        out = write_tsl(patches, liveset_name, args.output)
        if not args.json:
            print(f"Wrote {out}", file=sys.stderr)

    if args.json:
        liveset = build_liveset(patches, liveset_name)
        print(liveset_to_json(liveset))
        return 0

    # Human-readable: render each patch's knob list paired with its rationale.
    liveset = build_liveset(patches, liveset_name)
    for semantic, patch, recipe in zip(patches, liveset["patchList"], matched, strict=True):
        if recipe:
            print(f"  Recipe matched: {recipe.id}")
        print(render_knob_list(patch))
        if semantic.rationale:
            print(f"  Rationale: {semantic.rationale}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
