"""Console-script entrypoint for the web UI.

Kept import-light on purpose: `tone-gen-serve` is installed even when the
`web` extra is not, so this module must not import FastAPI or uvicorn at the
top level — a missing extra should produce an install instruction, not a
traceback.
"""

from __future__ import annotations

import sys


def main() -> None:
    """Console script: `tone-gen-serve` → starts uvicorn on localhost:8765."""
    try:
        import uvicorn

        from . import web  # noqa: F401  -- proves fastapi is importable too
    except ImportError:
        print(
            "The web interface needs extra dependencies that are not installed.\n"
            "Install them with: pip install 'me80-tone-gen[web]'",
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    uvicorn.run(
        "me80_tone_gen.web:app",
        host="127.0.0.1",
        port=8765,
        reload=False,
    )
