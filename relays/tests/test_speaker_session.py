import asyncio
import json

import core.speaker_session as speaker_session_module
from core.audio_processor import UtteranceBuffer
from core.session_manager import SessionRegistry
from core.speaker_session import run_speaker_session

from .conftest import FakeEngine, FakeWebSocket, make_speech_chunk


def _buf(**overrides):
    defaults = dict(
        sample_rate=16000, bytes_per_sample=2, silence_rms_threshold=0.01,
        silence_hang_seconds=0.3, min_utterance_seconds=0.2, max_utterance_seconds=8.0,
    )
    defaults.update(overrides)
    return UtteranceBuffer(**defaults)


async def _run_until_done(ws, session_id, engine, buf, registry):
    task = asyncio.create_task(run_speaker_session(ws, session_id, engine, buf, registry))
    await asyncio.sleep(0.02)
    return task


def _sent_payloads(ws):
    return [json.loads(m) for m in ws.sent]


async def test_pause_triggered_final_flush_sends_final_message():
    ws = FakeWebSocket()
    engine = FakeEngine(final_text="ask not what your country can do for you")
    registry = SessionRegistry()
    buf = _buf()
    task = await _run_until_done(ws, "speakertest1", engine, buf, registry)

    for _ in range(3):  # 0.3s speech, above min_utterance_seconds
        ws.feed(make_speech_chunk(amplitude=0.5, seconds=0.1))
        await asyncio.sleep(0.01)
    for _ in range(4):  # 0.4s silence, above silence_hang_seconds
        ws.feed(make_speech_chunk(amplitude=0.001, seconds=0.1))
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)

    payloads = _sent_payloads(ws)
    finals = [p for p in payloads if p.get("partial") is False]
    assert len(finals) == 1
    assert finals[0]["text"] == "ask not what your country can do for you"
    assert len(engine.final_calls) == 1

    ws.disconnect()
    await task


async def test_disconnect_with_pending_utterance_still_flushes():
    """The core Phase 1 fix: speech in progress, no pause yet, then an
    abrupt disconnect -- the final must still be computed and sent (to
    any viewers) rather than silently dropped."""
    ws = FakeWebSocket()
    engine = FakeEngine(final_text="the last thing said before disconnecting")
    registry = SessionRegistry()
    buf = _buf()
    task = await _run_until_done(ws, "disconnecttest1", engine, buf, registry)

    for _ in range(3):
        ws.feed(make_speech_chunk(amplitude=0.5, seconds=0.1))
        await asyncio.sleep(0.01)
    # No trailing silence -- disconnect immediately mid-utterance.
    ws.disconnect()
    await task

    assert len(engine.final_calls) == 1, "final transcription must still be computed on disconnect"
    # The speaker's own socket is already closed by the time flush()
    # resolves (matches the real scenario this guards against: the relay's
    # send() swallows ConnectionClosed to the speaker itself and still
    # broadcasts to any viewers) -- what matters here is that the engine
    # call happened at all instead of being abandoned mid-flight.


async def test_malformed_audio_frame_does_not_crash_session():
    ws = FakeWebSocket()
    engine = FakeEngine()
    registry = SessionRegistry()
    buf = _buf()
    task = await _run_until_done(ws, "malformedtest1", engine, buf, registry)

    ws.feed(b'\x01\x02\x03')  # odd length, not a multiple of 2
    await asyncio.sleep(0.02)
    # Session must still be alive and able to process a normal chunk after.
    ws.feed(make_speech_chunk(amplitude=0.5, seconds=0.1))
    await asyncio.sleep(0.02)
    assert not task.done(), "a malformed frame must not crash the session task"

    ws.disconnect()
    await task
    assert task.exception() is None


async def test_engine_failure_on_final_does_not_crash_session():
    ws = FakeWebSocket()
    engine = FakeEngine(raise_on_final=True)
    registry = SessionRegistry()
    buf = _buf()
    task = await _run_until_done(ws, "enginefailtest1", engine, buf, registry)

    for _ in range(3):
        ws.feed(make_speech_chunk(amplitude=0.5, seconds=0.1))
        await asyncio.sleep(0.01)
    for _ in range(4):
        ws.feed(make_speech_chunk(amplitude=0.001, seconds=0.1))
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)

    assert not task.done(), "an engine exception must not crash the session task"
    payloads = _sent_payloads(ws)
    assert all(p.get("partial") is not False for p in payloads), "no final message should be sent when the engine raised"

    ws.disconnect()
    await task


async def test_partial_updates_sent_for_engine_that_supports_them(monkeypatch):
    monkeypatch.setattr(speaker_session_module, "PARTIAL_CYCLE_SECONDS", 0.05)
    ws = FakeWebSocket()
    engine = FakeEngine(supports_partial=True, partial_words=["hello"])
    registry = SessionRegistry()
    buf = _buf(min_utterance_seconds=0.05)
    task = await _run_until_done(ws, "partialtest1", engine, buf, registry)

    ws.feed(make_speech_chunk(amplitude=0.5, seconds=0.1))
    await asyncio.sleep(0.15)  # let at least one partial cycle fire

    payloads = _sent_payloads(ws)
    partials = [p for p in payloads if p.get("partial") is True]
    assert len(partials) >= 1
    assert partials[0]["text"] == "hello"

    ws.disconnect()
    await task


async def test_partial_updates_never_sent_for_engine_without_support(monkeypatch):
    monkeypatch.setattr(speaker_session_module, "PARTIAL_CYCLE_SECONDS", 0.05)
    ws = FakeWebSocket()
    engine = FakeEngine(supports_partial=False)  # whisper.cpp / openai-whisper style
    registry = SessionRegistry()
    buf = _buf(min_utterance_seconds=0.05)
    task = await _run_until_done(ws, "nopartialtest1", engine, buf, registry)

    ws.feed(make_speech_chunk(amplitude=0.5, seconds=0.1))
    await asyncio.sleep(0.15)

    payloads = _sent_payloads(ws)
    assert not any(p.get("partial") is True for p in payloads)
    assert len(engine.partial_calls) == 0, "transcribe_partial must never be called for a non-partial engine"

    ws.disconnect()
    await task


async def test_session_max_duration_ends_session_proactively(monkeypatch):
    monkeypatch.setattr(speaker_session_module, "SESSION_MAX_DURATION_SECONDS", 0.05)
    ws = FakeWebSocket()
    engine = FakeEngine()
    registry = SessionRegistry()
    buf = _buf()
    task = asyncio.create_task(run_speaker_session(ws, "expiretest1", engine, buf, registry))

    await asyncio.sleep(0.02)
    for _ in range(10):
        ws.feed(make_speech_chunk(amplitude=0.001, seconds=0.02))
        await asyncio.sleep(0.02)

    await asyncio.wait_for(task, timeout=1.0)
    assert ws.close_code == 1000
    assert ws.close_reason == "session time limit reached"


async def test_speaker_connected_and_disconnected_tracked_in_registry():
    ws = FakeWebSocket()
    engine = FakeEngine()
    registry = SessionRegistry()
    buf = _buf()
    task = await _run_until_done(ws, "registrytest1", engine, buf, registry)
    assert "registrytest1" in registry.active_speakers

    ws.disconnect()
    await task
    assert "registrytest1" not in registry.active_speakers
