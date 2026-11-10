"""Capacity gate: past STT_MAX_ACTIVE_STREAMS a new speaker is refused (1013 server_busy) before billing authorization."""
import asyncio
import importlib
import sys

import pytest


class _WS:
    def __init__(self):
        self.closed = None

    async def close(self, code=1000, reason=""):
        self.closed = (code, reason)


class _P:
    session_id = "sess_abc123"
    access_code = None
    token = "t"
    role = "speaker"


@pytest.fixture
def relay(monkeypatch):
    monkeypatch.setenv("STT_ENGINE", "eou120m")
    sys.path.insert(0, ".")
    try:
        return importlib.import_module("parakeet_relay")
    except Exception as e:   # engine import needs the full runtime; skip rather than fake it
        pytest.skip(f"relay module not importable here: {e}")


def test_refused_when_full_and_counter_balanced(relay, monkeypatch):
    monkeypatch.setattr(relay, "STREAMING", True)
    monkeypatch.setattr(relay, "MAX_ACTIVE_STREAMS", 2)
    monkeypatch.setattr(relay, "_active_streams", 2)
    called = []

    async def admitted(ws, p):
        called.append(1)

    monkeypatch.setattr(relay, "_speaker_admitted", admitted)
    ws = _WS()
    asyncio.run(relay._handle_speaker(ws, _P()))
    assert ws.closed == (1013, "server_busy") and not called and relay._active_streams == 2


def test_admitted_counts_and_releases_even_on_error(relay, monkeypatch):
    monkeypatch.setattr(relay, "STREAMING", True)
    monkeypatch.setattr(relay, "MAX_ACTIVE_STREAMS", 2)
    monkeypatch.setattr(relay, "_active_streams", 1)
    seen = []

    async def admitted(ws, p):
        seen.append(relay._active_streams)
        raise RuntimeError("boom")

    monkeypatch.setattr(relay, "_speaker_admitted", admitted)
    with pytest.raises(RuntimeError):
        asyncio.run(relay._handle_speaker(_WS(), _P()))
    assert seen == [2] and relay._active_streams == 1


def test_zero_means_unlimited(relay, monkeypatch):
    monkeypatch.setattr(relay, "STREAMING", True)
    monkeypatch.setattr(relay, "MAX_ACTIVE_STREAMS", 0)
    monkeypatch.setattr(relay, "_active_streams", 99)

    async def admitted(ws, p):
        pass

    monkeypatch.setattr(relay, "_speaker_admitted", admitted)
    ws = _WS()
    asyncio.run(relay._handle_speaker(ws, _P()))
    assert ws.closed is None
