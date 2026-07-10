"""Console-script entrypoint for the web UI.

Kept import-light on purpose: `tone-gen-serve` is installed even when the
`web` extra is not, so this module must not import FastAPI or uvicorn at the
top level — a missing extra should produce an install instruction, not a
traceback.
"""

from __future__ import annotations

import argparse
import os
import sys

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
ENV_HOST = "TONE_GEN_HOST"
ENV_PORT = "TONE_GEN_PORT"


def _parse_args(argv: list[str] | None = None) -> tuple[str, int]:
    """Resolve host + port. Precedence: flag > env var > default."""
    parser = argparse.ArgumentParser(
        prog="tone-gen-serve",
        description="Start the local ME-80 tone generator web UI.",
    )
    parser.add_argument(
        "--host",
        default=None,
        help=f"Interface to bind (default: {DEFAULT_HOST}, or ${ENV_HOST}).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Port to bind (default: {DEFAULT_PORT}, or ${ENV_PORT}).",
    )
    args = parser.parse_args(argv)

    host = args.host or os.environ.get(ENV_HOST) or DEFAULT_HOST
    if args.port is not None:
        port = args.port
    else:
        env_port = os.environ.get(ENV_PORT)
        if env_port:
            try:
                port = int(env_port)
            except ValueError:
                parser.error(f"{ENV_PORT} must be an integer (got {env_port!r})")
        else:
            port = DEFAULT_PORT
    if not 1 <= port <= 65535:
        parser.error(f"port must be in 1..65535 (got {port})")
    return host, port


def main() -> None:
    """Console script: `tone-gen-serve` → start uvicorn on the resolved host/port."""
    host, port = _parse_args()

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
        host=host,
        port=port,
        reload=False,
    )
