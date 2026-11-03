"""Shared test fixtures for the relay test suite. Runs against the core/
and engines/ modules directly (in-process), not against a live server --
see test_live_relays.py for the subset of tests that do spin up a real
relay process and real websocket connections.
"""
import asyncio
import sys
from pathlib import Path

import pytest
import websockets.exceptions

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engines.base_engine import TranscriptionEngine  # noqa: E402


class FakeWebSocket:
    """Minimal stand-in for a websockets ServerConnection: supports the
    async-iteration-until-closed pattern the relay handlers use, plus
    send()/close() with inspectable results.
    """

    def __init__(self, path: str = "/"):
        self.path = path
        self.request = type("Req", (), {"path": path})()
        self._closed = asyncio.Event()
        self._inbound: asyncio.Queue = asyncio.Queue()
        self.sent: list[str] = []
        self.close_code = None
        self.close_reason = None

    def __aiter__(self):
        return self

    async def __anext__(self):
        get_task = asyncio.ensure_future(self._inbound.get())
        closed_task = asyncio.ensure_future(self._closed.wait())
        done, pending = await asyncio.wait({get_task, closed_task}, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        if get_task in done:
            return get_task.result()
        raise StopAsyncIteration

    def feed(self, message):
        """Queues an inbound message (simulates the remote client sending
        one) for the next `async for` iteration to receive."""
        self._inbound.put_nowait(message)

    async def send(self, message):
        if self._closed.is_set():
            raise websockets.exceptions.ConnectionClosed(None, None)
        self.sent.append(message)

    async def close(self, code=1000, reason=""):
        self.close_code = code
        self.close_reason = reason
        self._closed.set()

    def disconnect(self):
        """Simulates the remote end dropping the connection (not an
        explicit close() from our side)."""
        self._closed.set()


class FakeEngine(TranscriptionEngine):
    """Engine double for testing session orchestration without loading a
    real model. Returns scripted responses and records calls.
    """

    def __init__(self, final_text="hello world", partial_words=None, supports_partial=False, raise_on_final=False):
        self.supports_partial = supports_partial
        self._final_text = final_text
        self._partial_words = partial_words or []
        self._raise_on_final = raise_on_final
        self.final_calls: list[bytes] = []
        self.partial_calls: list[bytes] = []

    async def transcribe_final(self, pcm_bytes: bytes) -> str:
        self.final_calls.append(pcm_bytes)
        if self._raise_on_final:
            raise RuntimeError("simulated engine failure")
        return self._final_text

    async def transcribe_partial(self, pcm_bytes: bytes) -> list[str]:
        self.partial_calls.append(pcm_bytes)
        return self._partial_words


@pytest.fixture
def fake_engine():
    return FakeEngine()


def make_speech_chunk(amplitude=0.5, seconds=0.1, sample_rate=16000):
    """16-bit PCM mono chunk at a given amplitude -- amplitude >=
    SILENCE_RMS_THRESHOLD counts as speech, < counts as silence."""
    import numpy as np
    n = int(sample_rate * seconds)
    samples = (np.full(n, amplitude, dtype=np.float32) * 32767).astype(np.int16)
    return samples.tobytes()
