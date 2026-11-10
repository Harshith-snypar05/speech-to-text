import sys
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


PARAKEET_CLI = JFK_WAV.parent.parent / "build" / "bin" / ("parakeet-cli.exe" if sys.platform == "win32" else "parakeet-cli")
PARAKEET_MODEL = JFK_WAV.parent.parent / "models" / "ggml-parakeet-tdt-0.6b-v3-q8_0.bin"


@pytest.mark.skipif(
    not (JFK_WAV.exists() and PARAKEET_CLI.exists() and PARAKEET_MODEL.exists()),
    reason="parakeet-cli binary, model (~669MB, not vendored -- see relays/parakeet_relay.py docstring), or sample audio not available",
)
def test_parakeet_engine_real_transcription():
    """Real integration test against the actual parakeet-cli binary and
    the real nvidia/parakeet-tdt-0.6b-v3 GGML model (ggml-org's MIT-licensed
    conversion) -- not mocked. This is the subprocess-based fallback
    engine (see relays/parakeet_relay.py's docstring); ParakeetNativeEngine
    below is what's actually used when the shared library is built.
    """
    import asyncio

    from engines.parakeet_engine import ParakeetEngine

    with wave.open(str(JFK_WAV), "rb") as f:
        assert f.getframerate() == 16000
        pcm = f.readframes(f.getnframes())

    engine = ParakeetEngine(PARAKEET_CLI, PARAKEET_MODEL, 16000, 2)
    text = asyncio.run(engine.transcribe_final(pcm))
    normalized = text.lower()
    assert "country" in normalized
    assert "ask" in normalized
    assert text == collapse_repetition(text)


SHARED_BUILD_DIR = JFK_WAV.parent.parent / "build-shared" / "bin"
from engines.parakeet_native_engine import find_library  # noqa: E402


@pytest.mark.skipif(
    not (JFK_WAV.exists() and find_library(SHARED_BUILD_DIR) is not None and PARAKEET_MODEL.exists()),
    reason="shared library (libparakeet.dylib/.so or parakeet.dll; build, see parakeet_native_engine.py docstring), model, or sample audio not available",
)
def test_parakeet_native_engine_real_transcription_and_reuses_loaded_model():
    """Real integration test against the ctypes binding -- not mocked.
    Also proves the actual point of this engine over the subprocess one:
    two transcribe_final() calls against the same instance (same loaded
    model, no reload) both succeed and produce correct, consistent
    output -- the real fix for the ~350-520ms per-utterance reload cost
    measured through the subprocess-based engine.
    """
    import asyncio

    from engines.parakeet_native_engine import ParakeetNativeEngine

    with wave.open(str(JFK_WAV), "rb") as f:
        assert f.getframerate() == 16000
        pcm = f.readframes(f.getnframes())

    engine = ParakeetNativeEngine(SHARED_BUILD_DIR, PARAKEET_MODEL)
    try:
        text1 = asyncio.run(engine.transcribe_final(pcm))
        text2 = asyncio.run(engine.transcribe_final(pcm))
        for text in (text1, text2):
            normalized = text.lower()
            assert "country" in normalized
            assert "ask" in normalized
            assert text == collapse_repetition(text)
        assert text1 == text2, "same audio through the same loaded model must produce the same output"
    finally:
        asyncio.run(engine.shutdown())


@pytest.mark.skipif(
    not (JFK_WAV.exists() and find_library(SHARED_BUILD_DIR) is not None and PARAKEET_MODEL.exists()),
    reason="shared library, model, or sample audio not available",
)
def test_parakeet_native_engine_survives_concurrent_partial_and_final_calls():
    """Regression test for a real crash hit during manual testing:
    GGML_ASSERT(!sched->is_alloc) inside the Metal backend scheduler,
    which took the whole relay process down. Root cause was thread
    affinity -- parakeet_full() was being called from whatever OS thread
    Python's shared default executor happened to pick per call (varies
    across calls), and GGML's Metal scheduler doesn't tolerate that, even
    though an asyncio.Lock already serialized call *timing*. Fixed by
    pinning all native calls to a single dedicated worker thread. This
    test fires several transcribe_partial()/transcribe_final() calls
    concurrently via asyncio.gather -- matching how core/speaker_session.py's
    partial_cycle() background task and a flush() can genuinely overlap
    in real usage -- and asserts the process is still alive and every
    call returned a sane result, not just that it didn't hang.
    """
    import asyncio

    from engines.parakeet_native_engine import ParakeetNativeEngine

    with wave.open(str(JFK_WAV), "rb") as f:
        pcm = f.readframes(f.getnframes())
    half = pcm[: len(pcm) // 2]

    engine = ParakeetNativeEngine(SHARED_BUILD_DIR, PARAKEET_MODEL)
    try:
        async def run_concurrent():
            return await asyncio.gather(
                engine.transcribe_partial(half),
                engine.transcribe_final(pcm),
                engine.transcribe_partial(half),
                engine.transcribe_final(pcm),
            )

        partial1, final1, partial2, final2 = asyncio.run(run_concurrent())
        assert isinstance(partial1, list) and len(partial1) > 0
        assert isinstance(partial2, list) and len(partial2) > 0
        for final in (final1, final2):
            normalized = final.lower()
            assert "country" in normalized
            assert "ask" in normalized
    finally:
        asyncio.run(engine.shutdown())
