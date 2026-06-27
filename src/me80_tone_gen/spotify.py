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
    re.compile(
        r"^https?://open\.spotify\.com/(?:intl-[a-z]{2,3}/)?track/(?P<id>[A-Za-z0-9]+)(?:[/?#].*)?$"
    ),
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
        match = pattern.match(value.strip())
        if match:
            return match.group("id")
    raise SpotifyNotFoundError(f"not a Spotify track URL or URI: {value!r}")


class SpotifyClient:
    """Spotify Web API client using Client Credentials Flow.

    `client_id` and `client_secret` fall back to env vars SPOTIFY_CLIENT_ID
    and SPOTIFY_CLIENT_SECRET. The bearer token is cached in memory until
    its expiry (minus a safety buffer); not persisted to disk.
    """

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self._client_id = client_id or os.environ.get("SPOTIFY_CLIENT_ID")
        self._client_secret = client_secret or os.environ.get("SPOTIFY_CLIENT_SECRET")
        if not self._client_id or not self._client_secret:
            raise SpotifyAuthError(
                "Spotify credentials not configured. Set SPOTIFY_CLIENT_ID and "
                "SPOTIFY_CLIENT_SECRET (or pass them to SpotifyClient())."
            )
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def _ensure_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - _TOKEN_EXPIRY_BUFFER_SECONDS:
            return self._token

        basic = b64encode(f"{self._client_id}:{self._client_secret}".encode()).decode()
        req = urllib.request.Request(
            _TOKEN_URL,
            data=urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(),
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            raise SpotifyAuthError(
                f"Spotify token endpoint returned {exc.code}: check client credentials"
            ) from exc

        self._token = payload["access_token"]
        self._token_expires_at = time.time() + float(payload["expires_in"])
        return self._token

    def _get(self, path: str, params: dict[str, str] | None = None) -> dict:
        token = self._ensure_token()
        url = f"{_API_BASE}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise SpotifyNotFoundError(f"Spotify API 404 for {path}") from exc
            if exc.code in (401, 403):
                raise SpotifyAuthError(
                    f"Spotify API {exc.code} for {path} — credentials rejected"
                ) from exc
            raise SpotifyError(f"Spotify API error {exc.code} for {path}") from exc

    def features_from_url(self, track_url: str) -> tuple[AudioFeatures, TrackInfo]:
        """Resolve a Spotify track URL/URI to its audio features and metadata."""
        track_id = _parse_track_id(track_url)
        features_payload = self._get(f"/audio-features/{track_id}")
        track_payload = self._get(f"/tracks/{track_id}")
        return _features_from_payload(features_payload), _track_from_payload(track_payload)

    def features_from_query(self, query: str) -> tuple[AudioFeatures, TrackInfo]:
        """Search Spotify for `query` and return features for the top result."""
        search = self._get("/search", params={"q": query, "type": "track", "limit": "1"})
        items = search.get("tracks", {}).get("items", [])
        if not items:
            raise SpotifyNotFoundError(f"no Spotify track found for query: {query!r}")
        top = items[0]
        features_payload = self._get(f"/audio-features/{top['id']}")
        return _features_from_payload(features_payload), _track_from_payload(top)


def _features_from_payload(payload: dict) -> AudioFeatures:
    return AudioFeatures(
        tempo=float(payload["tempo"]),
        energy=float(payload["energy"]),
        loudness=float(payload["loudness"]),
        key=int(payload["key"]),
        mode=int(payload["mode"]),
        acousticness=float(payload["acousticness"]),
        instrumentalness=float(payload["instrumentalness"]),
        valence=float(payload["valence"]),
    )


def _track_from_payload(payload: dict) -> TrackInfo:
    artists = ", ".join(a["name"] for a in payload.get("artists", []))
    return TrackInfo(id=payload["id"], name=payload["name"], artist=artists)


_KEY_NAMES = ["C", "C#/Db", "D", "D#/Eb", "E", "F", "F#/Gb",
              "G", "G#/Ab", "A", "A#/Bb", "B"]


def format_features_for_prompt(features: AudioFeatures) -> str:
    """Human-readable block injected into the LLM user prompt."""
    key_label = _KEY_NAMES[features.key] if 0 <= features.key < 12 else "unknown"
    mode_label = "major" if features.mode == 1 else "minor"
    return (
        "Track audio features (real signal about the source song):\n"
        f"- tempo: {features.tempo:.0f} bpm\n"
        f"- energy: {features.energy:.2f} ({_qual(features.energy, 'high', 'medium', 'low')})\n"
        f"- loudness: {features.loudness:.1f} dB\n"
        f"- key: {key_label}, mode: {mode_label}\n"
        f"- acousticness: {features.acousticness:.2f} "
        f"({_qual(features.acousticness, 'high — acoustic', 'mixed', 'very low — electric')})\n"
        f"- instrumentalness: {features.instrumentalness:.2f} "
        f"({_qual(features.instrumentalness, 'instrumental', 'mixed', 'vocal-led')})\n"
        f"- valence: {features.valence:.2f} "
        f"({_qual(features.valence, 'bright', 'neutral', 'dark')})\n\n"
        "Use these to adjust your choices. They are advisory, not overrides — the "
        "description and recipe seed still drive type choices."
    )


def _qual(value: float, high: str, mid: str, low: str) -> str:
    if value >= 0.66:
        return high
    if value >= 0.33:
        return mid
    return low


def format_features_one_line(features: AudioFeatures) -> str:
    """One-line summary suitable for CLI stderr output."""
    energy_chip = _qual(features.energy, "high", "mid", "low")
    acoustic_chip = _qual(features.acousticness, "acoustic", "mixed", "electric")
    instr_chip = _qual(features.instrumentalness, "instrumental", "mixed", "vocal-led")
    valence_chip = _qual(features.valence, "bright", "neutral", "dark")
    return (
        f"tempo={features.tempo:.0f} bpm  "
        f"energy={features.energy:.2f} ({energy_chip})  "
        f"loudness={features.loudness:.1f} dB  "
        f"acousticness={features.acousticness:.2f} ({acoustic_chip})  "
        f"instrumentalness={features.instrumentalness:.2f} ({instr_chip})  "
        f"valence={features.valence:.2f} ({valence_chip})"
    )
