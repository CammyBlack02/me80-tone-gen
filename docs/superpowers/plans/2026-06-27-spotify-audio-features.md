# Spotify audio-features integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users attach a Spotify track URL or song name to a tone-generation request so the LLM gets real audio-features (tempo, energy, loudness, key, mode, acousticness, instrumentalness, valence) as grounding signal — opt-in, base flow unchanged.

**Architecture:** New core module `spotify.py` (stdlib-only HTTP, Client Credentials Flow, in-memory token cache) exposes `AudioFeatures`, `TrackInfo`, and `SpotifyClient`. `generator.generate_patch` gains an `audio_features` kwarg that injects a formatted block into the user prompt. CLI gets `--spotify-track` / `--spotify-song` flags. FastAPI gets a `spotify_track` request field; the route resolves it via the client and threads features through. README documents the env-var setup. All HTTP is mocked in tests at the `urllib.request.urlopen` boundary.

**Tech Stack:** Python 3.11+ stdlib (`urllib.request`, `base64`, `json`, `dataclasses`), Pydantic 2 (for the request/response models on the web layer), FastAPI (web), pytest + `unittest.mock` (tests). No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-06-27-spotify-audio-features-design.md`

**Test convention for this plan:** Per `CLAUDE.md`, tests are written *alongside* new behaviour, not in a strict red/green/refactor cycle. Each task adds the tests and the implementation in the same commit and runs the suite once at the end. We're not chasing TDD ceremony; we are guaranteeing every new code path lands with coverage.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `src/me80_tone_gen/spotify.py` | **new** | `AudioFeatures`, `TrackInfo`, `SpotifyClient`, error types, URL parsing, qualitative-label helper |
| `src/me80_tone_gen/generator.py` | modify | `audio_features` kwarg on `generate_patch`, prompt formatting, SYSTEM_PROMPT addendum |
| `src/me80_tone_gen/cli.py` | modify | `--spotify-track` / `--spotify-song` flags, stderr summary, batch incompatibility |
| `src/me80_tone_gen/web.py` | modify | `spotify_track` request field, response fields, route handler wiring |
| `src/me80_tone_gen/static/index.html` | modify | Optional input below the description, chip in the results panel |
| `tests/test_spotify.py` | **new** | URL parsing, token caching, features parsing, search, error paths |
| `tests/test_generator.py` | modify | Prompt-formatting test when `audio_features` is supplied |
| `tests/fixtures/spotify_audio_features.json` | **new** | Sample features-endpoint JSON |
| `tests/fixtures/spotify_track.json` | **new** | Sample track-endpoint JSON (for name/artist) |
| `tests/fixtures/spotify_search.json` | **new** | Sample search-endpoint JSON |
| `README.md` | modify | New "Spotify integration (optional)" section |

The web frontend changes go in `index.html` because that's where the existing UI lives (single-file SPA). We follow the existing structure — labels, cards, error rendering — rather than restructure.

---

## Task 1: SpotifyClient foundation — URL parsing, dataclasses, error types

**Files:**
- Create: `src/me80_tone_gen/spotify.py`
- Create: `tests/test_spotify.py`

The smallest unit that has tests of its own: the dataclasses, the error classes, and `_parse_track_id` (a private helper used by both `features_from_url` and URL normalization). Auth and HTTP land in Task 2.

- [ ] **Step 1: Create `src/me80_tone_gen/spotify.py` with the dataclasses, error types, and URL parser.**

```python
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
```

- [ ] **Step 2: Create `tests/test_spotify.py` with the URL-parsing tests.**

```python
"""Tests for the Spotify integration. HTTP is mocked at urlopen; no network."""

from __future__ import annotations

import pytest

from me80_tone_gen.spotify import (
    AudioFeatures,
    SpotifyAuthError,
    SpotifyNotFoundError,
    TrackInfo,
    _parse_track_id,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp", "3n3Ppam7vgaVa1iaRUc9Lp"),
        ("https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp?si=abc123", "3n3Ppam7vgaVa1iaRUc9Lp"),
        ("http://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp", "3n3Ppam7vgaVa1iaRUc9Lp"),
        ("spotify:track:3n3Ppam7vgaVa1iaRUc9Lp", "3n3Ppam7vgaVa1iaRUc9Lp"),
        ("  spotify:track:3n3Ppam7vgaVa1iaRUc9Lp  ", "3n3Ppam7vgaVa1iaRUc9Lp"),
    ],
)
def test_parse_track_id_accepts_canonical_forms(value: str, expected: str) -> None:
    assert _parse_track_id(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "https://open.spotify.com/album/3n3Ppam7vgaVa1iaRUc9Lp",
        "https://open.spotify.com/artist/3n3Ppam7vgaVa1iaRUc9Lp",
        "https://example.com/track/3n3Ppam7vgaVa1iaRUc9Lp",
        "spotify:album:3n3Ppam7vgaVa1iaRUc9Lp",
        "just some text",
        "",
    ],
)
def test_parse_track_id_rejects_non_track_urls(value: str) -> None:
    with pytest.raises(SpotifyNotFoundError):
        _parse_track_id(value)


def test_dataclasses_are_frozen() -> None:
    """Frozen so callers can't mutate them after the client returns them."""
    af = AudioFeatures(
        tempo=120.0, energy=0.5, loudness=-8.0, key=0, mode=1,
        acousticness=0.1, instrumentalness=0.0, valence=0.5,
    )
    with pytest.raises(Exception):
        af.tempo = 130.0  # type: ignore[misc]

    info = TrackInfo(id="abc", name="Track", artist="Artist")
    with pytest.raises(Exception):
        info.name = "Other"  # type: ignore[misc]


def test_error_hierarchy() -> None:
    """Both subclasses are catchable as SpotifyError."""
    from me80_tone_gen.spotify import SpotifyError

    assert issubclass(SpotifyAuthError, SpotifyError)
    assert issubclass(SpotifyNotFoundError, SpotifyError)
```

- [ ] **Step 3: Run the tests.**

Run: `pytest tests/test_spotify.py -v`
Expected: all tests pass.

- [ ] **Step 4: Commit.**

```bash
git add src/me80_tone_gen/spotify.py tests/test_spotify.py
git commit -m "Add Spotify module skeleton — dataclasses, errors, URL parser

Foundation for the audio-features integration (#9). HTTP client and
endpoint methods land in subsequent commits.

Refs #9.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: SpotifyClient — auth, token caching, HTTP helper

**Files:**
- Modify: `src/me80_tone_gen/spotify.py`
- Modify: `tests/test_spotify.py`

This task adds the `SpotifyClient` class with the credentials resolution, token endpoint call, in-memory cache, and a private `_get` helper that every endpoint method will use.

- [ ] **Step 1: Append the `SpotifyClient` class to `src/me80_tone_gen/spotify.py`.**

```python
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
```

- [ ] **Step 2: Append auth + caching tests to `tests/test_spotify.py`.**

```python
import io
import json as _json
from unittest.mock import patch

from me80_tone_gen.spotify import SpotifyClient, SpotifyError


def _http_response(payload: dict, status: int = 200) -> io.BytesIO:
    body = _json.dumps(payload).encode()
    buf = io.BytesIO(body)
    buf.headers = {}
    buf.status = status
    return buf


def _http_error(code: int) -> "urllib.error.HTTPError":
    import urllib.error
    return urllib.error.HTTPError("url", code, "msg", {}, io.BytesIO(b""))


def test_client_raises_when_credentials_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    with pytest.raises(SpotifyAuthError):
        SpotifyClient()


def test_client_reads_credentials_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "env-id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "env-secret")
    # Should not raise.
    client = SpotifyClient()
    assert client._client_id == "env-id"
    assert client._client_secret == "env-secret"


def test_client_constructor_args_override_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "env-id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "env-secret")
    client = SpotifyClient(client_id="ctor-id", client_secret="ctor-secret")
    assert client._client_id == "ctor-id"
    assert client._client_secret == "ctor-secret"


def test_token_is_cached_within_ttl() -> None:
    client = SpotifyClient(client_id="id", client_secret="secret")
    token_payload = {"access_token": "abc", "expires_in": 3600}
    with patch("me80_tone_gen.spotify.urllib.request.urlopen") as mock_open:
        mock_open.return_value.__enter__.return_value = _http_response(token_payload)
        first = client._ensure_token()
        second = client._ensure_token()
        assert first == "abc"
        assert second == "abc"
        assert mock_open.call_count == 1


def test_token_is_refreshed_after_expiry() -> None:
    client = SpotifyClient(client_id="id", client_secret="secret")
    payloads = [
        {"access_token": "first", "expires_in": 60},   # will appear expired below
        {"access_token": "second", "expires_in": 3600},
    ]
    call_count = {"n": 0}

    def fake_urlopen(*args, **kwargs):
        ctx = type("Ctx", (), {})()
        ctx.__enter__ = lambda self_=None: _http_response(payloads[call_count["n"]])
        ctx.__exit__ = lambda *exc: False
        call_count["n"] += 1
        return ctx

    with patch("me80_tone_gen.spotify.urllib.request.urlopen", side_effect=fake_urlopen):
        client._ensure_token()
        # Force the cache to look expired by mutating the expiry time.
        client._token_expires_at = 0.0
        token = client._ensure_token()
        assert token == "second"
        assert call_count["n"] == 2


def test_token_endpoint_401_raises_auth_error() -> None:
    client = SpotifyClient(client_id="id", client_secret="secret")
    with patch(
        "me80_tone_gen.spotify.urllib.request.urlopen",
        side_effect=_http_error(401),
    ):
        with pytest.raises(SpotifyAuthError):
            client._ensure_token()


def test_get_translates_http_errors() -> None:
    client = SpotifyClient(client_id="id", client_secret="secret")
    client._token = "abc"
    client._token_expires_at = time.time() + 3600

    with patch("me80_tone_gen.spotify.urllib.request.urlopen", side_effect=_http_error(404)):
        with pytest.raises(SpotifyNotFoundError):
            client._get("/audio-features/missing")

    with patch("me80_tone_gen.spotify.urllib.request.urlopen", side_effect=_http_error(401)):
        with pytest.raises(SpotifyAuthError):
            client._get("/audio-features/missing")

    with patch("me80_tone_gen.spotify.urllib.request.urlopen", side_effect=_http_error(500)):
        with pytest.raises(SpotifyError) as exc_info:
            client._get("/audio-features/missing")
        assert not isinstance(exc_info.value, (SpotifyAuthError, SpotifyNotFoundError))
```

Add `import time` to the test imports if not already there.

- [ ] **Step 3: Run the tests.**

Run: `pytest tests/test_spotify.py -v`
Expected: all tests pass, including the new auth/cache ones.

- [ ] **Step 4: Commit.**

```bash
git add src/me80_tone_gen/spotify.py tests/test_spotify.py
git commit -m "Add SpotifyClient with Client Credentials Flow and token cache

Auth via base64 client_id:client_secret to /api/token; bearer token cached
in memory with a 60s safety buffer. HTTPErrors map to AuthError/NotFoundError
where appropriate.

Refs #9.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `features_from_url` and `features_from_query`

**Files:**
- Modify: `src/me80_tone_gen/spotify.py`
- Modify: `tests/test_spotify.py`
- Create: `tests/fixtures/spotify_audio_features.json`
- Create: `tests/fixtures/spotify_track.json`
- Create: `tests/fixtures/spotify_search.json`

- [ ] **Step 1: Add the fixture files.**

Create `tests/fixtures/spotify_audio_features.json`:

```json
{
  "danceability": 0.421,
  "energy": 0.918,
  "key": 9,
  "loudness": -4.213,
  "mode": 0,
  "speechiness": 0.052,
  "acousticness": 0.014,
  "instrumentalness": 0.183,
  "liveness": 0.221,
  "valence": 0.337,
  "tempo": 140.012,
  "type": "audio_features",
  "id": "3n3Ppam7vgaVa1iaRUc9Lp",
  "uri": "spotify:track:3n3Ppam7vgaVa1iaRUc9Lp",
  "duration_ms": 215000,
  "time_signature": 4
}
```

Create `tests/fixtures/spotify_track.json`:

```json
{
  "id": "3n3Ppam7vgaVa1iaRUc9Lp",
  "name": "Sample Track",
  "artists": [
    {"name": "First Artist"},
    {"name": "Second Artist"}
  ],
  "type": "track"
}
```

Create `tests/fixtures/spotify_search.json`:

```json
{
  "tracks": {
    "items": [
      {
        "id": "3n3Ppam7vgaVa1iaRUc9Lp",
        "name": "Sample Track",
        "artists": [{"name": "First Artist"}],
        "type": "track"
      }
    ]
  }
}
```

- [ ] **Step 2: Append the public methods and label helper to `src/me80_tone_gen/spotify.py`.**

```python
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
    return (
        f"tempo={features.tempo:.0f} bpm  energy={features.energy:.2f}  "
        f"loudness={features.loudness:.1f} dB  "
        f"acousticness={features.acousticness:.2f}  "
        f"instrumentalness={features.instrumentalness:.2f}  "
        f"valence={features.valence:.2f}"
    )
```

- [ ] **Step 3: Append endpoint tests to `tests/test_spotify.py`.**

```python
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _seeded_client() -> SpotifyClient:
    client = SpotifyClient(client_id="id", client_secret="secret")
    client._token = "abc"
    client._token_expires_at = time.time() + 3600
    return client


def _mock_urlopen_sequence(*payload_paths: str):
    """Returns a side_effect that returns each fixture in turn."""
    payloads = [_json.loads((FIXTURES / p).read_text()) for p in payload_paths]
    idx = {"n": 0}

    def factory(*args, **kwargs):
        ctx = type("Ctx", (), {})()
        ctx.__enter__ = lambda self_=None: _http_response(payloads[idx["n"]])
        ctx.__exit__ = lambda *exc: False
        idx["n"] += 1
        return ctx
    return factory


def test_features_from_url_returns_features_and_info() -> None:
    client = _seeded_client()
    with patch(
        "me80_tone_gen.spotify.urllib.request.urlopen",
        side_effect=_mock_urlopen_sequence("spotify_audio_features.json", "spotify_track.json"),
    ):
        features, info = client.features_from_url(
            "https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp"
        )

    assert features.tempo == pytest.approx(140.012)
    assert features.energy == pytest.approx(0.918)
    assert features.key == 9
    assert features.mode == 0
    assert info.id == "3n3Ppam7vgaVa1iaRUc9Lp"
    assert info.name == "Sample Track"
    assert info.artist == "First Artist, Second Artist"


def test_features_from_query_uses_top_search_result() -> None:
    client = _seeded_client()
    with patch(
        "me80_tone_gen.spotify.urllib.request.urlopen",
        side_effect=_mock_urlopen_sequence("spotify_search.json", "spotify_audio_features.json"),
    ):
        features, info = client.features_from_query("Sample Track First Artist")
    assert info.name == "Sample Track"
    assert features.energy == pytest.approx(0.918)


def test_features_from_query_raises_on_empty_results() -> None:
    client = _seeded_client()

    def fake_urlopen(*args, **kwargs):
        ctx = type("Ctx", (), {})()
        ctx.__enter__ = lambda self_=None: _http_response({"tracks": {"items": []}})
        ctx.__exit__ = lambda *exc: False
        return ctx

    with patch("me80_tone_gen.spotify.urllib.request.urlopen", side_effect=fake_urlopen):
        with pytest.raises(SpotifyNotFoundError):
            client.features_from_query("a track that does not exist")


def test_format_features_for_prompt_contains_all_fields() -> None:
    from me80_tone_gen.spotify import format_features_for_prompt

    features = AudioFeatures(
        tempo=140.012, energy=0.918, loudness=-4.213,
        key=9, mode=0,
        acousticness=0.014, instrumentalness=0.183, valence=0.337,
    )
    text = format_features_for_prompt(features)
    assert "tempo: 140 bpm" in text
    assert "energy: 0.92" in text
    assert "A" in text                     # key label
    assert "minor" in text
    assert "very low — electric" in text   # acousticness=0.014 → low bucket
    assert "neutral" in text               # valence=0.337 → mid bucket


def test_format_features_qualitative_buckets() -> None:
    """Sanity-check the thresholds: 0.7→high, 0.5→mid, 0.1→low."""
    from me80_tone_gen.spotify import format_features_for_prompt

    high = AudioFeatures(120, 0.7, -8, 0, 1, 0.7, 0.7, 0.7)
    mid = AudioFeatures(120, 0.5, -8, 0, 1, 0.5, 0.5, 0.5)
    low = AudioFeatures(120, 0.1, -8, 0, 1, 0.1, 0.1, 0.1)
    assert "high" in format_features_for_prompt(high)
    assert "mixed" in format_features_for_prompt(mid)
    assert "very low — electric" in format_features_for_prompt(low)
```

- [ ] **Step 4: Run the tests.**

Run: `pytest tests/test_spotify.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit.**

```bash
git add src/me80_tone_gen/spotify.py tests/test_spotify.py tests/fixtures/spotify_audio_features.json tests/fixtures/spotify_track.json tests/fixtures/spotify_search.json
git commit -m "Implement features_from_url, features_from_query, prompt formatters

URL form fetches audio-features and track endpoints, joins the artist names
for display. Query form searches and takes the top result. Two prompt
formatters: a multi-line block for the LLM, a one-line summary for CLI stderr.

Refs #9.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Generator integration — `audio_features` kwarg + prompt addendum

**Files:**
- Modify: `src/me80_tone_gen/generator.py`
- Modify: `tests/test_generator.py`

- [ ] **Step 1: Update `generator.py`.**

Add the SYSTEM_PROMPT addendum just before the closing triple-quote (after the final paragraph). Locate the existing end:

```python
When you generate, ask yourself per block: would this style HAVE this effect on?
Many genres are defined by what's OFF as much as what's on. Don't enable blocks
"just to fill space" — and don't leave a defining effect off because you forgot.

Output a single JSON object matching the schema. Every block MUST appear in the
output. No prose outside the `rationale` field.
"""
```

Insert a new paragraph immediately before `Output a single JSON object...`:

```text
If the user provides "Track audio features" below, treat them as grounding
signal alongside the description. High energy and low acousticness mean push
the gain; high acousticness means CLEAN preamp and lighter effects; low
instrumentalness (vocal-led) means the tone should sit in the mix, not stand
out. Use loudness, tempo, and valence as supporting context for how aggressive
or restrained the tone should be. Features inform — they do not override the
description or recipe.
```

Update the imports and signature:

```python
from .schema import SemanticPatch
from .spotify import AudioFeatures, format_features_for_prompt
```

Change `_user_prompt`:

```python
def _user_prompt(
    description: str,
    recipe_seed: dict | None,
    audio_features: "AudioFeatures | None" = None,
) -> str:
    parts = [f"Tone description: {description}"]
    if recipe_seed:
        recipe_id = recipe_seed.get("id", "unknown")
        recipe_desc = recipe_seed.get("description", "")
        patch = recipe_seed.get("patch", recipe_seed)
        parts.append(
            f"A curated reference recipe matches this description (id: {recipe_id}).\n"
            f"Notes: {recipe_desc}\n\n"
            "Use this recipe's preamp type and effect-type choices as your anchor — "
            "do not deviate from them unless the user's description explicitly "
            "contradicts. Knob values below are starting points; you may adjust "
            "them to fit any extra detail in the description (e.g. 'more reverb', "
            "'tighter low end').\n\n"
            "Reference recipe patch settings:"
        )
        parts.append(json.dumps(patch, indent=2))
    if audio_features is not None:
        parts.append(format_features_for_prompt(audio_features))
    return "\n\n".join(parts)
```

Change `generate_patch` to accept and forward `audio_features`:

```python
def generate_patch(
    description: str,
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    retries: int = DEFAULT_RETRIES,
    recipe_seed: dict | None = None,
    audio_features: "AudioFeatures | None" = None,
    client: "object | None" = None,
) -> SemanticPatch:
    if client is None:
        import ollama
        client = ollama.Client()

    schema = SemanticPatch.model_json_schema()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _user_prompt(description, recipe_seed, audio_features)},
    ]
    # ... rest unchanged
```

- [ ] **Step 2: Add prompt-shape tests to `tests/test_generator.py`.**

Append:

```python
from me80_tone_gen.generator import _user_prompt
from me80_tone_gen.spotify import AudioFeatures


def test_user_prompt_without_audio_features_omits_block() -> None:
    text = _user_prompt("warm bluesy lead", recipe_seed=None, audio_features=None)
    assert "Track audio features" not in text
    assert "Tone description: warm bluesy lead" in text


def test_user_prompt_with_audio_features_includes_block() -> None:
    features = AudioFeatures(
        tempo=140.0, energy=0.92, loudness=-4.2,
        key=9, mode=0,
        acousticness=0.01, instrumentalness=0.18, valence=0.34,
    )
    text = _user_prompt("warm bluesy lead", recipe_seed=None, audio_features=features)
    assert "Track audio features" in text
    assert "tempo: 140 bpm" in text
    assert "energy: 0.92" in text


def test_generate_patch_forwards_audio_features_to_prompt() -> None:
    fake = FakeOllama([_valid_patch_json()])
    features = AudioFeatures(120, 0.5, -8, 0, 1, 0.5, 0.5, 0.5)
    generate_patch("test", client=fake, retries=0, audio_features=features)
    user_msg = fake.calls[0]["messages"][-1]["content"]
    assert "Track audio features" in user_msg


def test_system_prompt_includes_audio_features_guidance() -> None:
    assert "Track audio features" in SYSTEM_PROMPT
    assert "acousticness" in SYSTEM_PROMPT.lower()
```

- [ ] **Step 3: Run the full test suite (this changes the system prompt, regression-checking the rest).**

Run: `pytest -v`
Expected: all previously passing tests still pass; new ones pass.

- [ ] **Step 4: Commit.**

```bash
git add src/me80_tone_gen/generator.py tests/test_generator.py
git commit -m "Thread audio_features through generator into the user prompt

Adds an audio_features kwarg to generate_patch; _user_prompt appends a
formatted features block when supplied. SYSTEM_PROMPT gains a paragraph on
how to read the features.

Refs #9.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: CLI flags — `--spotify-track`, `--spotify-song`

**Files:**
- Modify: `src/me80_tone_gen/cli.py`

The CLI doesn't yet have dedicated unit tests. We add a small `tests/test_cli.py` here, focused only on the new flags and their wiring — argparse behaviour and the stderr summary path. Generator and SpotifyClient are both monkeypatched.

- [ ] **Step 1: Modify `src/me80_tone_gen/cli.py`.**

Add the imports at the top:

```python
from .spotify import (
    SpotifyClient,
    SpotifyError,
    format_features_one_line,
)
```

Inside `main()`, add the flags after `--no-recipes`:

```python
    spotify_group = parser.add_mutually_exclusive_group()
    spotify_group.add_argument(
        "--spotify-track",
        help="Spotify track URL or URI; its audio features are injected into the prompt.",
    )
    spotify_group.add_argument(
        "--spotify-song",
        help="Free-text song query; the top Spotify search match's features are used.",
    )
```

After `args = parser.parse_args(argv)`, add the batch-incompatibility check:

```python
    if args.batch and (args.spotify_track or args.spotify_song):
        parser.error(
            "--spotify-track / --spotify-song cannot be combined with --batch; "
            "per-track playlist support is tracked separately."
        )
```

Resolve features (only when a flag was supplied) before generation:

```python
    audio_features = None
    track_label = None
    if args.spotify_track or args.spotify_song:
        try:
            client = SpotifyClient()
            if args.spotify_track:
                audio_features, info = client.features_from_url(args.spotify_track)
            else:
                audio_features, info = client.features_from_query(args.spotify_song)
        except SpotifyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        track_label = f"{info.name} — {info.artist}"
        print(f"Spotify track: {track_label}", file=sys.stderr)
        print(f"  {format_features_one_line(audio_features)}", file=sys.stderr)
```

Update `_generate_one` to accept and pass `audio_features`:

```python
def _generate_one(
    description: str,
    args: argparse.Namespace,
    recipes: list[Recipe],
    audio_features=None,
) -> tuple[SemanticPatch, Recipe | None]:
    recipe = None if args.no_recipes else match_recipe(description, recipes)
    seed = recipe.model_dump(exclude={"aliases"}) if recipe else None
    patch = generator.generate_patch(
        description,
        model=args.model,
        temperature=args.temp,
        retries=args.retries,
        recipe_seed=seed,
        audio_features=audio_features,
    )
    return patch, recipe
```

And forward it at call sites — both for `--batch` and single. (Batch is guarded above so `audio_features` will be `None` there, but the parameter passes through cleanly either way.)

```python
    try:
        if args.batch:
            descriptions = _read_batch(args.batch)
            results = [_generate_one(d, args, recipes) for d in descriptions]
        else:
            description = _read_description(args)
            results = [_generate_one(description, args, recipes, audio_features)]
    except GenerationError as exc:
        ...
```

- [ ] **Step 2: Create `tests/test_cli.py`.**

```python
"""CLI-specific tests for the Spotify flags. Generator and Spotify clients
are both mocked; we only check argparse wiring and stderr output here."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from me80_tone_gen import cli
from me80_tone_gen.spotify import AudioFeatures, SpotifyAuthError, TrackInfo


def _stub_features() -> tuple[AudioFeatures, TrackInfo]:
    return (
        AudioFeatures(120.0, 0.7, -8.0, 9, 0, 0.05, 0.2, 0.5),
        TrackInfo(id="abc", name="Sample Track", artist="Sample Artist"),
    )


def test_spotify_track_and_song_are_mutually_exclusive(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main([
            "any description",
            "--spotify-track", "https://open.spotify.com/track/abc",
            "--spotify-song", "anything",
        ])
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "not allowed with" in err or "mutually exclusive" in err


def test_spotify_with_batch_errors(tmp_path, capsys) -> None:
    batch = tmp_path / "b.txt"
    batch.write_text("warm bluesy lead\n")
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--batch", str(batch), "--spotify-track", "https://open.spotify.com/track/abc"])
    assert exc_info.value.code == 2
    assert "--spotify-" in capsys.readouterr().err


def test_spotify_flag_prints_summary_to_stderr(capsys, monkeypatch) -> None:
    monkeypatch.setattr(cli, "SpotifyClient", lambda: type("C", (), {
        "features_from_url": lambda self, url: _stub_features(),
    })())

    fake_patch = type("P", (), {"patch_name": "TEST", "rationale": "r"})()

    def fake_generate(description, **kw):
        # Confirm audio features got forwarded.
        assert kw["audio_features"] is not None
        return fake_patch

    monkeypatch.setattr(cli.generator, "generate_patch", fake_generate)
    monkeypatch.setattr(cli, "build_liveset", lambda patches, name: {"patchList": [{"name": "TEST"}]})
    monkeypatch.setattr(cli, "render_knob_list", lambda p: "knob list")
    monkeypatch.setattr(cli, "match_recipe", lambda d, r: None)
    monkeypatch.setattr(cli, "load_recipes", lambda p=None: [])

    rc = cli.main(["warm bluesy lead", "--spotify-track", "https://open.spotify.com/track/abc"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "Spotify track: Sample Track — Sample Artist" in err
    assert "tempo=120" in err


def test_spotify_auth_error_exits_1(capsys, monkeypatch) -> None:
    def raising_client():
        raise SpotifyAuthError("creds missing")
    monkeypatch.setattr(cli, "SpotifyClient", raising_client)
    monkeypatch.setattr(cli, "load_recipes", lambda p=None: [])
    rc = cli.main(["warm bluesy lead", "--spotify-track", "https://open.spotify.com/track/abc"])
    assert rc == 1
    assert "creds missing" in capsys.readouterr().err
```

- [ ] **Step 3: Run the test suite.**

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 4: Commit.**

```bash
git add src/me80_tone_gen/cli.py tests/test_cli.py
git commit -m "Add --spotify-track and --spotify-song CLI flags

Mutually exclusive; cannot be combined with --batch. On resolution, prints
a one-line track + features summary to stderr (kept off stdout so --json
output stays clean). Spotify errors exit 1 with a clear message.

Refs #9.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Web API — `spotify_track` request field and response data

**Files:**
- Modify: `src/me80_tone_gen/web.py`

- [ ] **Step 1: Modify `src/me80_tone_gen/web.py`.**

Imports:

```python
from .spotify import (
    SpotifyAuthError,
    SpotifyClient,
    SpotifyError,
    SpotifyNotFoundError,
)
```

Update `GenerateRequest`:

```python
class GenerateRequest(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    model: str = DEFAULT_MODEL
    temperature: float = Field(default=DEFAULT_TEMPERATURE, ge=0.0, le=2.0)
    retries: int = Field(default=2, ge=0, le=5)
    use_recipes: bool = True
    liveset_name: str = "Generated"
    spotify_track: str | None = Field(default=None, max_length=500)
```

Update `GenerateResponse`:

```python
class GenerateResponse(BaseModel):
    patch: SemanticPatch
    knob_list_text: str
    recipe_matched_id: str | None
    recipe_matched_description: str | None
    liveset: dict[str, Any]
    spotify_features: dict | None = None
    spotify_track_label: str | None = None
```

Rewrite the `/api/generate` body:

```python
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
```

- [ ] **Step 2: Create `tests/test_web.py`.**

```python
"""Tests for the web API's Spotify integration. The Spotify and generator
modules are both monkeypatched; this verifies the request/response shape."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient   # noqa: E402

from me80_tone_gen import web   # noqa: E402
from me80_tone_gen.spotify import (   # noqa: E402
    AudioFeatures,
    SpotifyAuthError,
    SpotifyNotFoundError,
    TrackInfo,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(web.app)


def _valid_patch_dict() -> dict[str, Any]:
    return {
        "patch_name": "BLUES LEAD",
        "preamp": {"enabled": True, "type": "LEAD", "gain": 60, "bass": 50, "middle": 60, "treble": 55, "level": 50},
        "od_ds": {"enabled": False, "type": "OVERDRIVE", "drive": 50, "tone": 50, "level": 50},
        "comp": {"enabled": False, "type": "COMP", "knob1": 50, "knob2": 50, "knob3": 50},
        "mod": {"enabled": False, "type": "CHORUS", "knob1": 50, "knob2": 50, "knob3": 50},
        "eq_fx2": {"enabled": False, "type": "EQ", "knob1": 50, "knob2": 50, "knob3": 50, "knob4": 50},
        "delay": {"enabled": False, "type": "100-600 ms", "time": 50, "feedback": 50, "e_level": 50},
        "reverb": {"enabled": False, "type": "SPRING", "level": 30},
        "pedal_fx": {"enabled": False, "type": "WAH"},
        "rationale": "test",
    }


def test_generate_without_spotify_field_is_unchanged(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from me80_tone_gen.schema import SemanticPatch
    monkeypatch.setattr(web.generator, "generate_patch",
                        lambda **kw: SemanticPatch(**_valid_patch_dict()))
    resp = client.post("/api/generate", json={"description": "warm bluesy lead"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["spotify_features"] is None
    assert body["spotify_track_label"] is None


def test_generate_with_spotify_track_returns_features(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from me80_tone_gen.schema import SemanticPatch

    class FakeClient:
        def features_from_url(self, url: str):
            return (
                AudioFeatures(120.0, 0.7, -8.0, 9, 0, 0.05, 0.2, 0.5),
                TrackInfo(id="abc", name="Sample Track", artist="Sample Artist"),
            )
        def features_from_query(self, q: str):
            return self.features_from_url(q)

    monkeypatch.setattr(web, "SpotifyClient", lambda: FakeClient())
    captured: dict[str, Any] = {}
    def fake_gen(**kw):
        captured.update(kw)
        return SemanticPatch(**_valid_patch_dict())
    monkeypatch.setattr(web.generator, "generate_patch", fake_gen)

    resp = client.post("/api/generate", json={
        "description": "warm bluesy lead",
        "spotify_track": "https://open.spotify.com/track/abc",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["spotify_track_label"] == "Sample Track — Sample Artist"
    assert body["spotify_features"]["tempo"] == pytest.approx(120.0)
    assert captured["audio_features"] is not None


def test_generate_spotify_missing_creds_returns_400(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_auth():
        raise SpotifyAuthError("creds missing")
    monkeypatch.setattr(web, "SpotifyClient", raise_auth)
    resp = client.post("/api/generate", json={
        "description": "warm bluesy lead",
        "spotify_track": "https://open.spotify.com/track/abc",
    })
    assert resp.status_code == 400
    assert "creds missing" in resp.json()["detail"]["message"]


def test_generate_spotify_track_not_found_returns_404(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def features_from_url(self, url: str):
            raise SpotifyNotFoundError("track missing")
        def features_from_query(self, q: str):
            raise SpotifyNotFoundError("query empty")
    monkeypatch.setattr(web, "SpotifyClient", lambda: FakeClient())

    resp = client.post("/api/generate", json={
        "description": "warm bluesy lead",
        "spotify_track": "no results for this",
    })
    assert resp.status_code == 404
    assert "query empty" in resp.json()["detail"]["message"]


def test_generate_routes_url_vs_query(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """URL-shaped input hits features_from_url; bare text hits features_from_query."""
    from me80_tone_gen.schema import SemanticPatch
    calls = {"url": 0, "query": 0}

    class FakeClient:
        def features_from_url(self, url: str):
            calls["url"] += 1
            return (
                AudioFeatures(120.0, 0.7, -8.0, 9, 0, 0.05, 0.2, 0.5),
                TrackInfo(id="abc", name="X", artist="Y"),
            )
        def features_from_query(self, q: str):
            calls["query"] += 1
            return self.features_from_url(q)

    monkeypatch.setattr(web, "SpotifyClient", lambda: FakeClient())
    monkeypatch.setattr(web.generator, "generate_patch",
                        lambda **kw: SemanticPatch(**_valid_patch_dict()))

    client.post("/api/generate", json={
        "description": "x", "spotify_track": "https://open.spotify.com/track/abc",
    })
    client.post("/api/generate", json={
        "description": "x", "spotify_track": "spotify:track:abc",
    })
    client.post("/api/generate", json={
        "description": "x", "spotify_track": "Texas Flood by SRV",
    })
    assert calls == {"url": 2, "query": 1}
```

- [ ] **Step 3: Run the suite.**

Run: `pytest -v`
Expected: all tests pass. (If `fastapi` isn't installed in the env, `test_web.py` is skipped via `importorskip`.)

- [ ] **Step 4: Commit.**

```bash
git add src/me80_tone_gen/web.py tests/test_web.py
git commit -m "Wire Spotify field through the /api/generate route

Adds spotify_track on the request; resolves URL vs query by scheme prefix;
returns spotify_features + spotify_track_label on the response. Auth, 404,
and other Spotify errors map to 400, 404, and 502 respectively.

Refs #9.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Web frontend — input field and results-panel chip

**Files:**
- Modify: `src/me80_tone_gen/static/index.html`

No tests; this is HTML/JS rendering against the existing endpoint we just covered. We will eyeball it in the browser during the verification step.

- [ ] **Step 1: Add the Spotify input below the description textarea.**

Find this block in `src/me80_tone_gen/static/index.html` (around line 105–109):

```html
    <label class="field">
      <span class="label">Describe the tone</span>
      <textarea id="description" placeholder="e.g. warm bluesy lead with spring reverb"
                autofocus required></textarea>
    </label>
```

Add directly after it:

```html
    <label class="field">
      <span class="label">Spotify track (URL or song name) — optional</span>
      <input type="text" id="spotify-track"
             placeholder="e.g. https://open.spotify.com/track/... or 'Texas Flood by SRV'" />
    </label>
```

- [ ] **Step 2: Add a chip in the results panel for the Spotify summary.**

Find the results card (around line 139–149):

```html
  <section id="results" class="results">
    <div class="card">
      <div id="recipe-badge"></div>
      <p class="patch-name" id="patch-name"></p>
```

Insert a new element after `<div id="recipe-badge"></div>`:

```html
      <div id="spotify-badge" style="display:none;"></div>
```

Add minimal CSS for the badge inside the existing `<style>` block — place it directly after the `.card` rule (around line 32 of the current file):

```css
  #spotify-badge { font-family: var(--mono); font-size: 12px; color: var(--text-dim);
    background: var(--panel-2); border: 1px solid var(--border); border-radius: 6px;
    padding: 8px 10px; margin-bottom: 10px; }
  #spotify-badge .title { color: var(--accent); margin-right: 6px; }
```

- [ ] **Step 3: Include `spotify_track` in the request payload.**

Find this object in the submit handler (around line 247–254):

```javascript
      body: JSON.stringify({
        description: $("description").value.trim(),
        model: $("model").value.trim(),
        temperature: parseFloat($("temperature").value),
        retries: parseInt($("retries").value, 10),
        use_recipes: $("use-recipes").checked,
        liveset_name: $("liveset-name").value.trim() || "Generated",
      }),
```

Add `spotify_track`:

```javascript
      body: JSON.stringify({
        description: $("description").value.trim(),
        model: $("model").value.trim(),
        temperature: parseFloat($("temperature").value),
        retries: parseInt($("retries").value, 10),
        use_recipes: $("use-recipes").checked,
        liveset_name: $("liveset-name").value.trim() || "Generated",
        spotify_track: $("spotify-track").value.trim() || null,
      }),
```

- [ ] **Step 4: Render the Spotify badge in `renderResult`.**

Find the `renderResult` function in `index.html` (search for `function renderResult` — should be just above the submit handler around line 200). After it renders the recipe badge, add the Spotify badge population. The patch is similar in spirit to the recipe badge:

If the existing renderResult looks like this:

```javascript
function renderResult(data) {
  lastResult = data;
  $("patch-name").textContent = data.patch.patch_name;
  $("rationale").textContent = data.patch.rationale || "";
  $("knob-list").textContent = data.knob_list_text;
  const badge = $("recipe-badge");
  if (data.recipe_matched_id) {
    badge.textContent = "Recipe: " + data.recipe_matched_id;
    badge.style.display = "";
  } else {
    badge.style.display = "none";
  }
  $("results").classList.add("visible");
}
```

Add this Spotify block right before `$("results").classList.add("visible");`:

```javascript
  const sbadge = $("spotify-badge");
  if (data.spotify_track_label) {
    const f = data.spotify_features;
    sbadge.innerHTML =
      `<span class="title">Spotify:</span> ${data.spotify_track_label}<br/>` +
      `tempo=${Math.round(f.tempo)} bpm  energy=${f.energy.toFixed(2)}  ` +
      `loudness=${f.loudness.toFixed(1)} dB  ` +
      `acousticness=${f.acousticness.toFixed(2)}  ` +
      `valence=${f.valence.toFixed(2)}`;
    sbadge.style.display = "";
  } else {
    sbadge.style.display = "none";
  }
```

(If the exact `renderResult` shape differs, follow the same pattern as the recipe badge already in place.)

- [ ] **Step 5: Manual smoke test.**

```bash
tone-gen-serve &
SERVER_PID=$!
sleep 2
open http://127.0.0.1:8765    # or curl the page
# In a browser: enter a description, leave Spotify empty → generate works as before.
# Then enter a description + a Spotify URL (will 400 if creds aren't set, that's fine —
# we're checking the field renders and the error surfaces).
kill $SERVER_PID
```

(If `SPOTIFY_CLIENT_ID`/`SPOTIFY_CLIENT_SECRET` aren't set locally, the 400-with-message path is what we're verifying.)

- [ ] **Step 6: Commit.**

```bash
git add src/me80_tone_gen/static/index.html
git commit -m "Add Spotify track input and features chip to the web UI

Optional text input below the description (accepts URL or query); the
response's spotify_track_label and spotify_features render as a chip in the
results card. UI degrades cleanly when the field is left empty.

Refs #9.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: README documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a "Spotify integration (optional)" section.**

Locate the existing "Usage" section. After it (before the next major section — likely "Requirements" or "Install" depending on order; place the new section in the order that flows best, typically after Usage/CLI and before "Recipe authoring" or similar), insert:

```markdown
### Spotify integration (optional)

You can attach a Spotify track to give the model real audio context (tempo, energy, loudness, key, acousticness, instrumentalness, valence). It nudges the model — it doesn't override your description or a matched recipe.

**Setup (one-time):**

1. Create a free Spotify developer app at [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard).
2. Copy the Client ID and Client Secret.
3. Export them in your shell:

   ```bash
   export SPOTIFY_CLIENT_ID="..."
   export SPOTIFY_CLIENT_SECRET="..."
   ```

   (Add to your `~/.zshrc` / `~/.bashrc` to persist, or source a `.env` file before running.)

**CLI:**

```bash
# By URL
tone-gen "warm bluesy lead" --spotify-track "https://open.spotify.com/track/<id>"

# By song name (top search result is used)
tone-gen "warm bluesy lead" --spotify-song "Texas Flood by SRV"
```

The track name and a one-line features summary are printed to stderr; the patch goes to stdout. The two flags are mutually exclusive and cannot be combined with `--batch`.

**Web UI:**

A "Spotify track (URL or song name)" input sits below the description box. Leave it empty for the base flow; when filled, the resolved features appear in the results panel.

**Without credentials configured:** the base flow is unaffected. Spotify code paths only run when you opt in, and you get a clear error if credentials are missing.
```

- [ ] **Step 2: Commit.**

```bash
git add README.md
git commit -m "Document Spotify integration in README

Setup (Spotify dev app + env vars), CLI usage for both flag variants, and
the web UI surface. Notes the opt-in nature and graceful no-creds behavior.

Refs #9.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Final verification

**Files:** none — verification only.

- [ ] **Step 1: Run the full test suite.**

Run: `pytest -v`
Expected: all tests pass. Without `data/Contra_1.tsl`, expect ~25/34 prior tests passing + 9 skipped + however many new tests we added, all passing.

- [ ] **Step 2: Confirm base CLI flow still works.**

Run: `tone-gen --help`
Expected: `--spotify-track` and `--spotify-song` are listed in the help output. Other flags unchanged.

- [ ] **Step 3: Smoke test base flow (no Spotify) end-to-end if Ollama is available.**

Run: `tone-gen "warm bluesy lead with spring reverb"`
Expected: a knob list prints; no Spotify chatter on stderr.

- [ ] **Step 4: If credentials are available, smoke test a Spotify URL.**

Run: `tone-gen "warm bluesy lead" --spotify-track "https://open.spotify.com/track/<a-real-id>"`
Expected: stderr shows the track name + features one-liner; stdout shows the patch.

- [ ] **Step 5: Web UI eyeball.**

```bash
tone-gen-serve
# Open http://127.0.0.1:8765 in a browser
# Generate without Spotify — confirm unchanged.
# Generate with Spotify filled — confirm chip renders or a clear error appears.
```

---

## Self-review notes

Coverage map vs. the spec:

| Spec requirement | Where |
|---|---|
| `AudioFeatures` / `TrackInfo` / error types | Task 1 |
| Stdlib HTTP + Client Credentials Flow + token cache | Task 2 |
| `features_from_url` / `features_from_query` | Task 3 |
| Prompt formatter + qualitative labels | Task 3 |
| `audio_features` kwarg on `generate_patch` | Task 4 |
| SYSTEM_PROMPT addendum | Task 4 |
| CLI `--spotify-track` / `--spotify-song` (mutex, batch incompat, stderr) | Task 5 |
| `GenerateRequest.spotify_track` + URL/query routing | Task 6 |
| `GenerateResponse.spotify_features` / `spotify_track_label` | Task 6 |
| Web UI input + chip | Task 7 |
| README docs | Task 8 |
| Manual verification of acceptance criteria | Task 9 |

No placeholders. All snippets are complete. Method names match across tasks (`features_from_url`, `features_from_query`, `format_features_for_prompt`, `format_features_one_line`, `_parse_track_id`). Error types are consistent (`SpotifyError` parent; `SpotifyAuthError`, `SpotifyNotFoundError` children).
