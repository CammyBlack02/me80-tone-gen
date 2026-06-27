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
from .generator import DEFAULT_MODEL, DEFAULT_TEMPERATURE, GenerationError
from .recipes import Recipe, load_recipes, match_recipe
from .renderer import render_knob_list
from .schema import SemanticPatch
from .spotify import (
    SpotifyAuthError,
    SpotifyClient,
    SpotifyError,
    SpotifyNotFoundError,
)
from .writer import build_liveset

app = FastAPI(title="ME-80 AI Tone Generator", version=__version__)

# Recipes are loaded once at startup. The list is small; re-reading per request
# would just add latency. To pick up edits, restart the server (uvicorn --reload
# will do this automatically in dev).
_RECIPES: list[Recipe] = load_recipes()


class GenerateRequest(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    model: str = DEFAULT_MODEL
    temperature: float = Field(default=DEFAULT_TEMPERATURE, ge=0.0, le=2.0)
    retries: int = Field(default=2, ge=0, le=5)
    use_recipes: bool = True
    liveset_name: str = "Generated"
    spotify_track: str | None = Field(default=None, max_length=500)


class GenerateResponse(BaseModel):
    patch: SemanticPatch
    knob_list_text: str
    recipe_matched_id: str | None
    recipe_matched_description: str | None
    liveset: dict[str, Any]
    spotify_features: dict | None = None
    spotify_track_label: str | None = None


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


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

    audio_features = None
    spotify_features_dict = None
    spotify_track_label = None
    if req.spotify_track:
        try:
            client = SpotifyClient()
            value = req.spotify_track.strip()
            if value.startswith(("http://", "https://", "spotify:")):
                audio_features, info = client.features_from_url(value)
            else:
                audio_features, info = client.features_from_query(value)
        except SpotifyAuthError as exc:
            raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc
        except SpotifyNotFoundError as exc:
            raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
        except SpotifyError as exc:
            raise HTTPException(status_code=502, detail={"message": str(exc)}) from exc
        spotify_track_label = f"{info.name} — {info.artist}"
        spotify_features_dict = {
            "tempo": audio_features.tempo,
            "energy": audio_features.energy,
            "loudness": audio_features.loudness,
            "key": audio_features.key,
            "mode": audio_features.mode,
            "acousticness": audio_features.acousticness,
            "instrumentalness": audio_features.instrumentalness,
            "valence": audio_features.valence,
        }

    try:
        patch = generator.generate_patch(
            req.description,
            model=req.model,
            temperature=req.temperature,
            retries=req.retries,
            recipe_seed=seed,
            audio_features=audio_features,
        )
    except GenerationError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": str(exc), "last_error": exc.last_error},
        ) from exc

    liveset = build_liveset([patch], req.liveset_name)
    return GenerateResponse(
        patch=patch,
        knob_list_text=render_knob_list(liveset["patchList"][0]),
        recipe_matched_id=recipe.id if recipe else None,
        recipe_matched_description=recipe.description if recipe else None,
        liveset=liveset,
        spotify_features=spotify_features_dict,
        spotify_track_label=spotify_track_label,
    )


# --- Static page ---

_STATIC_INDEX = files("me80_tone_gen").joinpath("static", "index.html")


@app.get("/")
def index() -> FileResponse:
    """Serve the single-page UI."""
    return FileResponse(str(_STATIC_INDEX), media_type="text/html")


# --- Console-script entrypoint ---

def serve() -> None:
    """Console script: `tone-gen-serve` → starts uvicorn on localhost:8765."""
    import uvicorn

    uvicorn.run(
        "me80_tone_gen.web:app",
        host="127.0.0.1",
        port=8765,
        reload=False,
    )
