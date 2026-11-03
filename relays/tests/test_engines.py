import wave
from pathlib import Path

import pytest

from core.transcript_manager import collapse_repetition
from engines.base_engine import TranscriptionEngine

from .conftest import FakeEngine

JFK_WAV = Path(__file__).resolve().parent.parent.parent / "whisper.cpp" / "samples" / "jfk.wav"


def test_fake_engine_satisfies_interface():
    engine = FakeEngine()
    assert isinstance(engine, TranscriptionEngine)
    assert hasattr(engine, "supports_partial")


async def test_base_engine_transcribe_partial_default_raises_not_implemented():
    class MinimalEngine(TranscriptionEngine):
        async def transcribe_final(self, pcm_bytes: bytes) -> str:
            return "ok"

    engine = MinimalEngine()
    assert engine.supports_partial is False
    with pytest.raises(NotImplementedError):
        await engine.transcribe_partial(b"")


async def test_base_engine_shutdown_default_is_noop():
    class MinimalEngine(TranscriptionEngine):
        async def transcribe_final(self, pcm_bytes: bytes) -> str:
            return "ok"

    await MinimalEngine().shutdown()  # must not raise


async def test_fake_engine_records_calls_and_returns_scripted_text():
    engine = FakeEngine(final_text="scripted response")
    result = await engine.transcribe_final(b"\x00\x00")
    assert result == "scripted response"
    assert engine.final_calls == [b"\x00\x00"]


async def test_fake_engine_raises_when_configured_to():
    engine = FakeEngine(raise_on_final=True)
    with pytest.raises(RuntimeError):
        await engine.transcribe_final(b"\x00\x00")


@pytest.mark.skipif(not JFK_WAV.exists(), reason="sample audio not available")
def test_fasterwhisper_engine_real_transcription():
    """Real integration test against the actual model (already cached in
    this environment from earlier benchmarking) -- not mocked. Skips
    cleanly in environments without the sample audio rather than failing
    the whole suite over a missing fixture.
    """
    try:
        from engines.fasterwhisper_engine import FasterWhisperEngine
    except ImportError:
        pytest.skip("faster_whisper not installed in this environment")

    import asyncio
    import numpy as np

    with wave.open(str(JFK_WAV), "rb") as f:
        assert f.getframerate() == 16000
        pcm = f.readframes(f.getnframes())

    engine = FasterWhisperEngine()
    text = asyncio.run(engine.transcribe_final(pcm))
    normalized = text.lower()
    # Real assertion against real inference output, not a mock -- the JFK
    # clip's well-known line.
    assert "country" in normalized
    assert "ask" in normalized
    assert text == collapse_repetition(text), "engine output should already be repetition-collapsed"
