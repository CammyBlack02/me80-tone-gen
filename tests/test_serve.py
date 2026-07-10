"""Tests for the `tone-gen-serve` console script."""

from __future__ import annotations

from typing import Any

import pytest

from me80_tone_gen import serve


def test_defaults_when_no_flag_no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(serve.ENV_HOST, raising=False)
    monkeypatch.delenv(serve.ENV_PORT, raising=False)
    host, port = serve._parse_args([])
    assert host == serve.DEFAULT_HOST
    assert port == serve.DEFAULT_PORT


def test_flags_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(serve.ENV_HOST, raising=False)
    monkeypatch.delenv(serve.ENV_PORT, raising=False)
    host, port = serve._parse_args(["--host", "0.0.0.0", "--port", "9000"])
    assert (host, port) == ("0.0.0.0", 9000)


def test_env_vars_used_when_no_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(serve.ENV_HOST, "192.168.1.10")
    monkeypatch.setenv(serve.ENV_PORT, "9100")
    host, port = serve._parse_args([])
    assert (host, port) == ("192.168.1.10", 9100)


def test_flag_beats_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(serve.ENV_HOST, "192.168.1.10")
    monkeypatch.setenv(serve.ENV_PORT, "9100")
    host, port = serve._parse_args(["--host", "10.0.0.1", "--port", "7000"])
    assert (host, port) == ("10.0.0.1", 7000)


def test_invalid_port_flag_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(serve.ENV_HOST, raising=False)
    monkeypatch.delenv(serve.ENV_PORT, raising=False)
    with pytest.raises(SystemExit):
        serve._parse_args(["--port", "not-a-number"])


def test_bad_env_port_errors_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(serve.ENV_PORT, "not-a-number")
    with pytest.raises(SystemExit):
        serve._parse_args([])


def test_out_of_range_port_flag_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(serve.ENV_HOST, raising=False)
    monkeypatch.delenv(serve.ENV_PORT, raising=False)
    with pytest.raises(SystemExit):
        serve._parse_args(["--port", "99999"])


def test_main_passes_resolved_host_port_to_uvicorn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end wiring: main() → _parse_args → uvicorn.run receives the right args."""
    pytest.importorskip("uvicorn")
    monkeypatch.setenv(serve.ENV_HOST, "192.168.1.10")
    monkeypatch.delenv(serve.ENV_PORT, raising=False)
    monkeypatch.setattr("sys.argv", ["tone-gen-serve", "--port", "9200"])

    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any) -> None:
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr("uvicorn.run", fake_run)
    serve.main()

    assert captured["kwargs"]["host"] == "192.168.1.10"
    assert captured["kwargs"]["port"] == 9200
    assert captured["args"] == ("me80_tone_gen.web:app",)
