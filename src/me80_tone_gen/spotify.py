"""Spotify audio-features integration.

Stdlib-only HTTP client over the Spotify Web API using the Client Credentials
Flow. Returns audio features the generator can inject into the LLM prompt as
grounding signal.

Credentials are read from constructor args, falling back to env vars
SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET. The base tone-gen flow does not
import or instantiate this module; it is only touched when the user opts in.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64encode
from dataclasses import dataclass

_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API_BASE = "https://api.spotify.com/v1"
_TOKEN_EXPIRY_BUFFER_SECONDS = 60

_TRACK_URL_PATTERNS = (
    re.compile(r"^https?://open\.spotify\.com/track/(?P<id>[A-Za-z0-9]+)(?:\?.*)?$"),
    re.compile(r"^spotify:track:(?P<id>[A-Za-z0-9]+)$"),
)


@dataclass(frozen=True)
class AudioFeatures:
    """Subset of Spotify's audio-features endpoint that the prompt actually uses."""

    tempo: float
    energy: float
    loudness: float
    key: int
    mode: int
    acousticness: float
    instrumentalness: float
    valence: float


@dataclass(frozen=True)
class TrackInfo:
    id: str
    name: str
    artist: str


class SpotifyError(Exception):
    """Base class for Spotify-integration failures."""


class SpotifyAuthError(SpotifyError):
    """Missing credentials or token-endpoint rejection (401/403)."""


class SpotifyNotFoundError(SpotifyError):
    """Track URL parse failure, 404 from the API, or empty search results."""


def _parse_track_id(value: str) -> str:
    for pattern in _TRACK_URL_PATTERNS:
        m = pattern.match(value.strip())
        if m:
            return m.group("id")
    raise SpotifyNotFoundError(f"not a Spotify track URL or URI: {value!r}")
