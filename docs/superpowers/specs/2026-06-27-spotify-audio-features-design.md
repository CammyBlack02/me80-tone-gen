# Spotify audio-features integration — design

Issue: [#9](https://github.com/CammyBlack02/me80-tone-gen/issues/9). Part of the tone-accuracy umbrella ([#6](https://github.com/CammyBlack02/me80-tone-gen/issues/6)).

## Goal

Give the LLM real, grounded signal about a song when the user asks for a tone in the context of one. Spotify's audio-features endpoint returns numeric descriptors (tempo, energy, loudness, key, acousticness, instrumentalness, valence) for any track, free, structured, instant. Not enough to recreate a tone — enough to *inform* the model when no curated recipe matches.

The base flow (no Spotify) stays untouched. The feature is opt-in via CLI flag or web UI field. No credentials are consulted unless the user invokes it.

## Non-goals

- **User-playlist access.** That requires Authorization Code Flow with user login; it's deferred to issue #5's Spotify support.
- **On-disk caching of features.** Issue marks this out-of-scope; small upgrade if proven useful later.
- **Retry/backoff on Spotify rate limits.** Local single-user use, one call per generation. Surface a clear error instead.

## Module layout

New core module `src/me80_tone_gen/spotify.py`. Same shape as the rest of the core: business logic here; CLI and web are thin shells over it.

```python
@dataclass(frozen=True)
class AudioFeatures:
    tempo: float            # bpm
    energy: float           # 0.0–1.0
    loudness: float         # dB, typically -60 to 0
    key: int                # 0=C, 1=C#/Db, …, 11=B; -1 if unknown
    mode: int               # 0=minor, 1=major
    acousticness: float     # 0.0–1.0
    instrumentalness: float # 0.0–1.0
    valence: float          # 0.0–1.0 (musical positivity)


@dataclass(frozen=True)
class TrackInfo:
    id: str
    name: str
    artist: str             # primary artist, comma-joined if multiple


class SpotifyError(Exception): ...
class SpotifyAuthError(SpotifyError): ...      # missing/invalid creds
class SpotifyNotFoundError(SpotifyError): ...  # no track for query / 404 on URL


class SpotifyClient:
    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        ...

    def features_from_url(self, track_url: str) -> tuple[AudioFeatures, TrackInfo]: ...
    def features_from_query(self, query: str) -> tuple[AudioFeatures, TrackInfo]: ...
```

Implementation notes:

- **Stdlib HTTP only.** `urllib.request` + `json` + `base64`. Two endpoints (`/api/token`, `/v1/audio-features/{id}`, `/v1/tracks/{id}`, `/v1/search`) and a handful of fields. Adding `requests` or `httpx` for ~80 lines of HTTP is a poor trade.
- **Client Credentials Flow.** POST to `https://accounts.spotify.com/api/token` with `grant_type=client_credentials` and Basic-auth header `base64(client_id:client_secret)`. Response gives `access_token` and `expires_in` (seconds).
- **Token caching.** In-memory only. Cache `(token, expires_at)`. Reuse until `now > expires_at - 60s`, then re-auth. No persistence to disk.
- **Credential resolution.** Constructor args → env vars `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET`. Missing creds → `SpotifyAuthError` with a message pointing at the env var names.
- **URL parsing.** Accept `https://open.spotify.com/track/<id>` (with or without query string) and `spotify:track:<id>` URI form. Anything else → `SpotifyNotFoundError("not a Spotify track URL: …")`.
- **`features_from_query`.** Calls `/v1/search?type=track&limit=1&q=<query>`; takes the top result. If zero results → `SpotifyNotFoundError`.
- **`TrackInfo.artist`.** Spotify returns `artists: [{name: ...}, ...]`; we join with `, ` for display.

The `AudioFeatures` dataclass exposes only the seven fields the LLM prompt uses, even though Spotify returns more (danceability, speechiness, liveness, etc.). Narrowing the type makes the prompt formatter trivial and avoids leaking JSON-shape knowledge into other modules.

## Generator integration

`generator.generate_patch(...)` gains a keyword arg:

```python
def generate_patch(
    description: str,
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    retries: int = DEFAULT_RETRIES,
    recipe_seed: dict | None = None,
    audio_features: AudioFeatures | None = None,   # NEW
    client: object | None = None,
) -> SemanticPatch:
```

`_user_prompt(description, recipe_seed, audio_features)` appends a formatted block when features are present, after any recipe block:

```
Track audio features (real signal about the source song):
- tempo: 140 bpm
- energy: 0.92 (high)
- loudness: -4.2 dB
- key: 9 (A), mode: minor
- acousticness: 0.01 (very low — electric)
- instrumentalness: 0.18 (vocal-led)
- valence: 0.34 (darker)

Use these to adjust your choices. They are advisory, not overrides — the
description and recipe seed still drive type choices.
```

The SYSTEM_PROMPT gets one short paragraph (not a lookup table) at the end explaining how to read features:

> If audio features are provided, treat them as grounding signal. High energy and low acousticness mean push the gain. High acousticness means CLEAN preamp and lighter effects. Low instrumentalness (vocal-heavy) means the tone should sit in the mix — pull back on extreme settings. Use loudness, tempo, and valence as supporting context for how aggressive or restrained the tone should be.

Qualitative labels (`(high)`, `(very low — electric)`) come from a small helper in `spotify.py` that formats each feature with a human-readable suffix using fixed thresholds. The thresholds are an implementation detail; if they're wrong, we tune them once and move on.

## CLI surface

```bash
tone-gen "warm bluesy lead" --spotify-track <url>
tone-gen "warm bluesy lead" --spotify-song "Texas Flood by SRV"
```

- Argparse: a mutually-exclusive group containing `--spotify-track` and `--spotify-song`. Combining either with `--batch` is a usage error (exit 2) — one Spotify track informing ten unrelated descriptions is almost certainly a mistake, and per-line track mapping is the playlist support that's part of #5.
- On resolution, print a one-line summary to **stderr** before the patch:
  ```
  Spotify track: Texas Flood — Stevie Ray Vaughan
    tempo=87 bpm  energy=0.82 (high)  loudness=-8.1 dB
    acousticness=0.04 (very low)  instrumentalness=0.15  valence=0.41
  ```
  Stderr keeps `--json` output clean.
- Errors: `SpotifyAuthError` and `SpotifyNotFoundError` exit 1 with a clear message. They are the same exit code as `GenerationError` because they're both "failed to produce a patch" cases.
- If neither `--spotify-*` flag is given, no Spotify code runs and credentials are not consulted. The base flow is unchanged.

## Web UI

`GenerateRequest` adds:

```python
spotify_track: str | None = Field(default=None, max_length=500)
```

The route detects URL vs query by checking for a scheme (`http://`, `https://`, `spotify:`); URL → `features_from_url`, otherwise → `features_from_query`.

`GenerateResponse` adds:

```python
spotify_features: dict | None       # AudioFeatures fields, serialized
spotify_track_label: str | None     # "Texas Flood — Stevie Ray Vaughan"
```

When creds aren't configured: HTTP 400 with `{"detail": {"message": "Spotify not configured. Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to use this feature."}}`. When a track lookup fails: HTTP 404 with a similar shape.

UI changes: one new optional text input below the description box ("Spotify track (URL or song name) — optional"). When the response includes Spotify data, a small chip is shown in the results panel with the track label and the feature values. If the request fails with a Spotify error, the UI shows the message inline near the input, not as a generic toast.

The route handler stays thin: it instantiates `SpotifyClient` (lazy, only when `spotify_track` is set), fetches features, and passes them through to `generate_patch`. No business logic in `web.py`.

## Tests

New `tests/test_spotify.py`. HTTP is mocked at the `urlopen` boundary via `unittest.mock.patch`. No real network calls.

Covered:
- URL parsing: accepts `open.spotify.com/track/<id>`, `open.spotify.com/track/<id>?si=...`, `spotify:track:<id>`. Rejects album URLs, artist URLs, garbage strings.
- Token caching: a second call within TTL does not re-hit `/api/token`. A call after `expires_at - 60s` does.
- Features parsing: fixture JSON in `tests/fixtures/spotify_audio_features.json` and `spotify_track.json` (small, anonymized samples) → expected `AudioFeatures` and `TrackInfo`.
- Search: query → top result.
- Errors: missing creds → `SpotifyAuthError`; 401 from token endpoint → `SpotifyAuthError`; 404 from features endpoint → `SpotifyNotFoundError`; empty search results → `SpotifyNotFoundError`.

Extend `tests/test_generator.py`:
- When `audio_features=None`, the user prompt looks the same as today (regression guard).
- When `audio_features=<sample>`, the user prompt includes the features block with the qualitative labels.

No real Spotify calls anywhere in `pytest` runs — same discipline as Ollama.

## Docs

README gains a "Spotify integration (optional)" section after the basic usage block:

- Brief blurb on what it adds.
- How to create a Spotify dev app (link to developer.spotify.com/dashboard) and copy the client ID + secret.
- How to set `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` (env vars; mention `.env`-style sourcing without bundling a dotenv loader).
- The two CLI invocations and a one-line web-UI mention.
- The caveat: features are *advisory* — they nudge the model, they don't override recipes or the description.

## Acceptance, mapped from the issue

- [ ] Config: `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` env vars, documented in README.
- [ ] `--spotify-track <url>` and `--spotify-song <query>` work end-to-end.
- [ ] Generated patches differ measurably when features are supplied vs. not. Verified manually post-merge by generating "warm bluesy lead" with and without an acoustic track URL and comparing preamp choices.
- [ ] Graceful fallback if no credentials configured: base flow is unaffected, Spotify code paths only run when the user opts in, and when they do, errors are clear.
