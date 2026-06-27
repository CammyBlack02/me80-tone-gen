"""Tests for the Spotify integration. HTTP is mocked at urlopen; no network."""

from __future__ import annotations

import dataclasses

import pytest

from me80_tone_gen.spotify import (
    AudioFeatures,
    SpotifyAuthError,
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
