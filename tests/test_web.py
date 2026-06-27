"""Tests for the web API's Spotify integration. The Spotify and generator
modules are both monkeypatched; this verifies the request/response shape."""

from __future__ import annotations

from typing import Any

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
                        lambda *a, **kw: SemanticPatch(**_valid_patch_dict()))
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
    def fake_gen(*a, **kw):
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

    def _result():
        return (
            AudioFeatures(120.0, 0.7, -8.0, 9, 0, 0.05, 0.2, 0.5),
            TrackInfo(id="abc", name="X", artist="Y"),
        )

    class FakeClient:
        def features_from_url(self, url: str):
            calls["url"] += 1
            return _result()
        def features_from_query(self, q: str):
            calls["query"] += 1
            return _result()

    monkeypatch.setattr(web, "SpotifyClient", lambda: FakeClient())
    monkeypatch.setattr(web.generator, "generate_patch",
                        lambda *a, **kw: SemanticPatch(**_valid_patch_dict()))

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
