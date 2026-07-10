"""FastAPI web UI — thin wrapper around the core module.

Routes:
- GET  /              → serves the single-page UI
- POST /api/generate  → semantic patch + knob list + recipe match + liveset JSON
- GET  /api/recipes   → the loaded recipe set (so the UI can show what's available)

Business logic stays in writer/renderer/generator/recipes. The routes only
marshal request/response shapes.
"""

from __future__ import annotations

from importlib.resources import files
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import __version__, generator
from .generator import DEFAULT_MODEL, GenerationError
from .recipes import Recipe, load_recipes, match_recipe
from .renderer import render_knob_list
from .schema import SemanticPatch
from .writer import build_liveset

app = FastAPI(title="ME-80 AI Tone Generator", version=__version__)

# Recipes are loaded once at startup. The list is small; re-reading per request
# would just add latency. To pick up edits, restart the server (uvicorn --reload
# will do this automatically in dev).
_RECIPES: list[Recipe] = load_recipes()


class GenerateRequest(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    model: str = DEFAULT_MODEL
    retries: int = Field(default=2, ge=0, le=5)
    use_recipes: bool = True
    liveset_name: str = "Generated"
    variants: int = Field(default=1, ge=1, le=5)


class VariantResult(BaseModel):
    patch: SemanticPatch
    knob_list_text: str
    liveset: dict[str, Any]


class GenerateResponse(BaseModel):
    variants: list[VariantResult]
    recipe_matched_id: str | None
    recipe_matched_description: str | None


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/api/ready")
def ready(model: str = DEFAULT_MODEL) -> dict[str, Any]:
    """Preflight probe: is Ollama reachable and the target model pulled?

    Always 200 — readiness is state, not an error. The UI keys off `ready`.
    """
    return generator.probe_ready(model)


@app.get("/api/recipes")
def list_recipes() -> dict[str, Any]:
    """Return id, aliases, and description for each loaded recipe."""
    return {
        "recipes": [
            {"id": r.id, "aliases": r.aliases, "description": r.description}
            for r in _RECIPES
        ]
    }


@app.post("/api/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest) -> GenerateResponse:
    recipe = match_recipe(req.description, _RECIPES) if req.use_recipes else None
    seed = recipe.model_dump(exclude={"aliases"}) if recipe else None

    try:
        patches = generator.generate_variants(
            req.description,
            n=req.variants,
            model=req.model,
            retries=req.retries,
            recipe_seed=seed,
        )
    except GenerationError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": str(exc), "last_error": exc.last_error},
        ) from exc

    variant_results: list[VariantResult] = []
    for patch in patches:
        liveset = build_liveset([patch], req.liveset_name)
        variant_results.append(
            VariantResult(
                patch=patch,
                knob_list_text=render_knob_list(liveset["patchList"][0]),
                liveset=liveset,
            )
        )

    return GenerateResponse(
        variants=variant_results,
        recipe_matched_id=recipe.id if recipe else None,
        recipe_matched_description=recipe.description if recipe else None,
    )


# --- Static page ---

_STATIC_INDEX = files("me80_tone_gen").joinpath("static", "index.html")


@app.get("/")
def index() -> FileResponse:
    """Serve the single-page UI."""
    return FileResponse(str(_STATIC_INDEX), media_type="text/html")
