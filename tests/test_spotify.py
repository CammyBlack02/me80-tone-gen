"""Tests for the Spotify integration. HTTP is mocked at urlopen; no network."""

from __future__ import annotations

import dataclasses
import io
import json as _json
import time
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
        # Context-manager dunders must live on the type, not the instance,
        # for Python 3.11+ to honor the `with` protocol.
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
