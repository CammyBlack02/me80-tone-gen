"""CLI-specific tests for the Spotify flags. Generator and Spotify clients
are both mocked; we only check argparse wiring and stderr output here."""

from __future__ import annotations

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
