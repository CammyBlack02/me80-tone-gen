"""Tests for the Spotify integration. HTTP is mocked at urlopen; no network."""

from __future__ import annotations

import dataclasses
import io
import json as _json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from me80_tone_gen.spotify import (
    AudioFeatures,
    SpotifyAuthError,
    SpotifyClient,
    SpotifyError,
    SpotifyNotFoundError,
    TrackInfo,
    _parse_track_id,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp", "3n3Ppam7vgaVa1iaRUc9Lp"),
        ("https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp?si=abc123", "3n3Ppam7vgaVa1iaRUc9Lp"),
        ("http://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp", "3n3Ppam7vgaVa1iaRUc9Lp"),
        ("spotify:track:3n3Ppam7vgaVa1iaRUc9Lp", "3n3Ppam7vgaVa1iaRUc9Lp"),
        ("  spotify:track:3n3Ppam7vgaVa1iaRUc9Lp  ", "3n3Ppam7vgaVa1iaRUc9Lp"),
        ("https://open.spotify.com/intl-ja/track/3n3Ppam7vgaVa1iaRUc9Lp", "3n3Ppam7vgaVa1iaRUc9Lp"),
        ("https://open.spotify.com/intl-fr/track/3n3Ppam7vgaVa1iaRUc9Lp?si=abc", "3n3Ppam7vgaVa1iaRUc9Lp"),
        ("https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp#fragment", "3n3Ppam7vgaVa1iaRUc9Lp"),
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
    with pytest.raises(dataclasses.FrozenInstanceError):
        af.tempo = 130.0  # type: ignore[misc]

    info = TrackInfo(id="abc", name="Track", artist="Artist")
    with pytest.raises(dataclasses.FrozenInstanceError):
        info.name = "Other"  # type: ignore[misc]


def test_error_hierarchy() -> None:
    """Both subclasses are catchable as SpotifyError."""
    assert issubclass(SpotifyAuthError, SpotifyError)
    assert issubclass(SpotifyNotFoundError, SpotifyError)


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
        # Context-manager dunders must live on the type, not the instance — CPython
        # looks them up via the type slot and ignores instance attributes.
        idx = call_count["n"]
        call_count["n"] += 1
        Ctx = type(
            "Ctx",
            (),
            {
                "__enter__": lambda self_: _http_response(payloads[idx]),
                "__exit__": lambda self_, *exc: False,
            },
        )
        return Ctx()

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
        payload = payloads[idx["n"]]
        idx["n"] += 1
        Ctx = type(
            "Ctx",
            (),
            {
                "__enter__": lambda self_: _http_response(payload),
                "__exit__": lambda self_, *exc: False,
            },
        )
        return Ctx()
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
        Ctx = type(
            "Ctx",
            (),
            {
                "__enter__": lambda self_: _http_response({"tracks": {"items": []}}),
                "__exit__": lambda self_, *exc: False,
            },
        )
        return Ctx()

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


def test_qual_threshold_boundaries() -> None:
    from me80_tone_gen.spotify import _qual

    # 0.66 is the high threshold (inclusive).
    assert _qual(0.66, "high", "mid", "low") == "high"
    assert _qual(0.65, "high", "mid", "low") == "mid"
    # 0.33 is the mid threshold (inclusive).
    assert _qual(0.33, "high", "mid", "low") == "mid"
    assert _qual(0.32, "high", "mid", "low") == "low"
    # Far-end sanity.
    assert _qual(0.95, "high", "mid", "low") == "high"
    assert _qual(0.0, "high", "mid", "low") == "low"


def test_format_features_prompt_uses_qual_labels() -> None:
    """The formatter must use _qual for each labeled feature."""
    from me80_tone_gen.spotify import format_features_for_prompt

    # energy=0.7 should bucket high; energy=0.1 should bucket low.
    high = AudioFeatures(120, 0.7, -8, 0, 1, 0.05, 0.05, 0.05)
    low = AudioFeatures(120, 0.1, -8, 0, 1, 0.95, 0.95, 0.95)
    assert "energy: 0.70 (high)" in format_features_for_prompt(high)
    assert "energy: 0.10 (low)" in format_features_for_prompt(low)


def test_format_features_one_line_includes_chips() -> None:
    from me80_tone_gen.spotify import format_features_one_line
    features = AudioFeatures(120.0, 0.92, -4.0, 9, 0, 0.04, 0.15, 0.41)
    text = format_features_one_line(features)
    assert "energy=0.92 (high)" in text
    assert "acousticness=0.04 (electric)" in text
    assert "instrumentalness=0.15 (vocal-led)" in text
    assert "valence=0.41 (neutral)" in text
    assert "tempo=120 bpm" in text
