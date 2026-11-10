"""Phase 7 regression coverage for the reliability areas named in the
Phase 7 task. Plumbing only -- FakeEngine/FakeWebSocket, no model. The
real-ASR side of the same checklist lives in test_phase7_asr.py.

Every test here pins CURRENT behaviour. Several of them assert that a
*proposed* improvement (previous-audio context overlap) does NOT exist yet,
so that implementing it later is a deliberate, test-visible decision rather
than an accident.
"""
import asyncio
import json

import numpy as np

import core.speaker_session as speaker_session_module
from core.session_manager import SessionRegistry
from core.speaker_session import run_speaker_session

from .conftest import FakeEngine, FakeWebSocket, make_speech_chunk
from .test_speaker_session import _buf

SPEECH = dict(amplitude=0.5, seconds=0.1)
QUIET = dict(amplitude=0.001, seconds=0.1)


def _const_chunk(value: int, seconds: float = 0.1, sample_rate: int = 16000) -> bytes:
    """Constant-valued PCM frame. Amplitude is chosen by the caller so the
    chunk is identifiable inside a snapshot (markers) as well as being
    above/below the RMS silence threshold."""
    return np.full(int(sample_rate * seconds), value, dtype=np.int16).tobytes()


def _payloads(ws):
    return [json.loads(m) for m in ws.sent]


async def _session(ws, session_id, engine, buf, registry):
    task = asyncio.create_task(run_speaker_session(ws, session_id, engine, buf, registry))
    await asyncio.sleep(0.02)
    return task


async def _speak(ws, marker: int, n_speech: int = 3, n_quiet: int = 4):
    """One full utterance: n_speech frames of marker-valued 'speech' then
    enough silence to cross the silence hang."""
    for _ in range(n_speech):
        ws.feed(_const_chunk(marker))
        await asyncio.sleep(0.005)
    for _ in range(n_quiet):
        ws.feed(_const_chunk(10))  # ~0.0003 RMS: silence for every config used here
        await asyncio.sleep(0.005)
    await asyncio.sleep(0.03)


# ------------------------------------------------------- empty decode family
async def test_empty_decode_with_pending_utterance_drops_final_but_session_recovers():
    """The Phase 5 defect shape: the engine returns "" for a pending
    utterance -> no final is sent, the utterance is lost, and the session
    must keep working for the NEXT utterance (no crash, no stuck state)."""
    ws = FakeWebSocket()
    engine = FakeEngine(final_text="")
    registry = SessionRegistry()
    buf = _buf()
    task = await _session(ws, "phase7empty1", engine, buf, registry)

    await _speak(ws, marker=10000)
    await asyncio.sleep(0.05)
    assert _payloads(ws) == [], "an empty decode must not emit a final"
    assert len(engine.final_calls) == 1

    engine._final_text = "recovered text"  # second utterance decodes fine
    await _speak(ws, marker=20000)
    await asyncio.sleep(0.05)
    finals = [p for p in _payloads(ws) if p.get("partial") is False]
    assert [f["text"] for f in finals] == ["recovered text"], \
        "an empty decode must not poison later flushes in the same session"

    ws.disconnect()
    await task
    assert task.exception() is None


async def test_empty_decode_never_constructs_or_sends_a_final(monkeypatch, tmp_path):
    """Diagnostics on: the empty path is recorded as dropped_empty_text and
    nothing reaches the wire. Diagnostics off: identical wire behaviour."""
    log = tmp_path / "d.jsonl"
    monkeypatch.setenv("STT_FLUSH_DIAG_FILE", str(log))
    ws = FakeWebSocket()
    engine = FakeEngine(final_text="")
    buf = _buf()
    task = await _session(ws, None, engine, buf, SessionRegistry())
    await _speak(ws, marker=10000)
    await asyncio.sleep(0.05)

    assert [p for p in _payloads(ws) if p.get("partial") is False] == []
    recs = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
    assert [r["outcome"] for r in recs] == ["dropped_empty_text"]
    assert recs[0]["final_constructed"] is False and recs[0]["final_send_called"] is False
    assert recs[0]["has_pending"] is True and recs[0]["text_empty"] is True

    ws.disconnect()
    await task


# ----------------------------------------------------------- flush families
async def test_normal_non_empty_final_is_sent_exactly_once():
    ws = FakeWebSocket()
    engine = FakeEngine(final_text="a single clean final")
    buf = _buf()
    task = await _session(ws, "phase7final1", engine, buf, SessionRegistry())
    await _speak(ws, marker=10000)
    await asyncio.sleep(0.05)

    finals = [p for p in _payloads(ws) if p.get("partial") is False]
    assert [f["text"] for f in finals] == ["a single clean final"]
    assert len(engine.final_calls) == 1

    ws.disconnect()
    await task


async def test_silence_hang_flush_reports_reason_silence_hang(monkeypatch, tmp_path):
    log = tmp_path / "d.jsonl"
    monkeypatch.setenv("STT_FLUSH_DIAG_FILE", str(log))
    ws = FakeWebSocket()
    buf = _buf()
    task = await _session(ws, None, FakeEngine(final_text="hang"), buf, SessionRegistry())
    await _speak(ws, marker=10000)  # speech then >= 0.3s silence
    await asyncio.sleep(0.05)

    recs = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
    assert recs and recs[0]["reason"] == "silence_hang" and recs[0]["outcome"] == "final_sent"

    ws.disconnect()
    await task


async def test_forced_cap_flush_reports_reason_forced_cap(monkeypatch, tmp_path):
    log = tmp_path / "d.jsonl"
    monkeypatch.setenv("STT_FLUSH_DIAG_FILE", str(log))
    ws = FakeWebSocket()
    buf = _buf(max_utterance_seconds=0.5)
    task = await _session(ws, None, FakeEngine(final_text="capped"), buf, SessionRegistry())
    for _ in range(6):  # 0.6s of unbroken speech, no pause at all
        ws.feed(_const_chunk(10000))
        await asyncio.sleep(0.005)
    await asyncio.sleep(0.05)

    recs = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
    assert recs and recs[0]["reason"] == "forced_cap" and recs[0]["outcome"] == "final_sent"
    assert [p for p in _payloads(ws) if p.get("partial") is False][0]["text"] == "capped"

    ws.disconnect()
    await task


async def test_trailing_disconnect_flush_after_a_clean_end_is_not_pending(monkeypatch, tmp_path):
    """Trailing silence left in the buffer at disconnect: no decode, no
    final, logged as dropped_not_pending."""
    log = tmp_path / "d.jsonl"
    monkeypatch.setenv("STT_FLUSH_DIAG_FILE", str(log))
    ws = FakeWebSocket()
    buf = _buf()
    task = await _session(ws, None, FakeEngine(final_text="x"), buf, SessionRegistry())
    await _speak(ws, marker=10000)          # flush #1 -> final_sent
    for _ in range(4):                      # silence only, no speech after it
        ws.feed(_const_chunk(10))
        await asyncio.sleep(0.005)
    ws.disconnect()
    await task

    recs = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
    assert [r["outcome"] for r in recs] == ["final_sent", "dropped_not_pending"]
    assert recs[1]["decode_attempted"] is False
    assert len([p for p in _payloads(ws) if p.get("partial") is False]) == 1


# ------------------------------------------- context overlap / duplication
async def test_consecutive_utterances_do_not_share_audio():
    """CURRENT behaviour, deliberately: each flush decodes only the audio
    since the previous take(). No previous-context overlap exists. If a
    context-overlap feature is approved, this test must be updated on
    purpose -- it is the guard that makes that change visible."""
    class RecordingEngine(FakeEngine):
        async def transcribe_final(self, pcm_bytes: bytes) -> str:
            self.final_calls.append(pcm_bytes)
            return "ok"

    ws = FakeWebSocket()
    engine = RecordingEngine()
    buf = _buf()
    task = await _session(ws, "phase7overlap1", engine, buf, SessionRegistry())

    await _speak(ws, marker=10000)
    await asyncio.sleep(0.05)
    await _speak(ws, marker=20000)
    await asyncio.sleep(0.05)

    assert len(engine.final_calls) == 2
    first = set(np.frombuffer(engine.final_calls[0], dtype=np.int16).tolist())
    second = set(np.frombuffer(engine.final_calls[1], dtype=np.int16).tolist())
    assert 10000 in first and 20000 not in first
    assert 20000 in second and 10000 not in second, \
        "utterance 2 must not contain utterance 1's audio (no overlap today)"
    # marker 10 is the shared trailing silence, present in both by design
    assert first - {10} and second - {10}

    ws.disconnect()
    await task


async def test_consecutive_finals_do_not_duplicate_or_merge_words():
    """Two utterances -> two independent finals, in order, each exactly the
    engine's text for its own audio. The relay must never concatenate
    utterances or echo a previous final."""
    class SequenceEngine(FakeEngine):
        def __init__(self):
            super().__init__()
            self.n = 0

        async def transcribe_final(self, pcm_bytes: bytes) -> str:
            self.final_calls.append(pcm_bytes)
            self.n += 1
            return f"utterance {self.n} words"

    ws = FakeWebSocket()
    engine = SequenceEngine()
    buf = _buf()
    task = await _session(ws, "phase7dupes1", engine, buf, SessionRegistry())

    for i, marker in enumerate((10000, 20000, 30000), start=1):
        await _speak(ws, marker=marker)
        await asyncio.sleep(0.05)

    finals = [p for p in _payloads(ws) if p.get("partial") is False]
    assert [f["text"] for f in finals] == ["utterance 1 words", "utterance 2 words", "utterance 3 words"]
    assert all(len(f["text"].split()) == 3 for f in finals), "no final may absorb a neighbour's words"

    ws.disconnect()
    await task


# --------------------------------------------- partial <-> final reconciliation
async def test_partial_accumulator_resets_across_a_final(monkeypatch):
    """Relay half of partial-to-final reconciliation: after a final, the
    next utterance's partials must start from empty, not append to the
    words already finalized."""
    monkeypatch.setattr(speaker_session_module, "PARTIAL_CYCLE_SECONDS", 0.05)
    ws = FakeWebSocket()
    engine = FakeEngine(supports_partial=True, partial_words=["alpha", "beta"],
                        final_text="alpha beta")
    buf = _buf(min_utterance_seconds=0.05)
    task = await _session(ws, "phase7reconc1", engine, buf, SessionRegistry())

    await _speak(ws, marker=10000, n_speech=4, n_quiet=5)
    await asyncio.sleep(0.05)
    engine._partial_words = ["next"]
    engine._final_text = "next words"
    await _speak(ws, marker=20000, n_speech=4, n_quiet=5)
    await asyncio.sleep(0.05)

    payloads = _payloads(ws)
    partial_texts = [p["text"] for p in payloads if p.get("partial") is True]
    finals = [p["text"] for p in payloads if p.get("partial") is False]
    assert partial_texts, "expected partials for at least the first utterance"
    assert partial_texts[0] == "alpha beta"
    assert finals == ["alpha beta", "next words"]
    assert partial_texts[-1] == "next", \
        f"post-final partial must restart from empty, got {partial_texts!r}"
    assert not any(t.startswith("alpha") for t in partial_texts[1:]), \
        "words from a finalized utterance must not leak into later partials"

    ws.disconnect()
    await task


async def test_consecutive_utterance_finals_keep_wire_order(monkeypatch, tmp_path):
    """Ordering: finals arrive in utterance order, and the diagnostics seq
    counter agrees with the wire order."""
    log = tmp_path / "d.jsonl"
    monkeypatch.setenv("STT_FLUSH_DIAG_FILE", str(log))
    ws = FakeWebSocket()
    engine = FakeEngine(final_text="ordered")
    buf = _buf()
    task = await _session(ws, None, engine, buf, SessionRegistry())

    for marker in (10000, 20000, 30000):
        await _speak(ws, marker=marker)
        await asyncio.sleep(0.03)

    finals = [p for p in _payloads(ws) if p.get("partial") is False]
    assert len(finals) == 3 and all(f["text"] == "ordered" for f in finals)
    recs = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
    assert [r["seq"] for r in recs] == [1, 2, 3]
    assert [r["outcome"] for r in recs] == ["final_sent"] * 3
    assert len({r["conn_id"] for r in recs}) == 1

    ws.disconnect()
    await task


# ------------------------------------------------- multiple concurrent speakers
async def test_two_concurrent_speakers_get_only_their_own_finals():
    """Two speaker sessions at once, sharing one engine and one registry
    (exactly how parakeet_relay.py wires it). Each socket must receive only
    the finals produced from its own audio -- no cross-talk, no ordering
    mix-up between sessions."""

    class MarkerEngine(FakeEngine):
        async def transcribe_final(self, pcm_bytes: bytes) -> str:
            self.final_calls.append(pcm_bytes)
            first = int(np.frombuffer(pcm_bytes, dtype=np.int16)[0])
            return f"marker{first}"

    engine = MarkerEngine()
    registry = SessionRegistry()
    ws1, ws2 = FakeWebSocket(), FakeWebSocket()
    task1 = await _session(ws1, "phase7spkAAAA", engine, _buf(), registry)
    task2 = await _session(ws2, "phase7spkBBBB", engine, _buf(), registry)

    async def talk(ws, marker):
        await _speak(ws, marker=marker)

    await asyncio.gather(talk(ws1, 10000), talk(ws2, 30000))
    await asyncio.sleep(0.1)

    f1 = [p["text"] for p in _payloads(ws1) if p.get("partial") is False]
    f2 = [p["text"] for p in _payloads(ws2) if p.get("partial") is False]
    assert f1 == ["marker10000"], f"speaker 1 saw {f1!r}"
    assert f2 == ["marker30000"], f"speaker 2 saw {f2!r}"

    ws1.disconnect()
    ws2.disconnect()
    await asyncio.gather(task1, task2)


# ------------------------------------------- diagnostics on vs off (partials)
async def test_diagnostics_on_off_identical_with_partials(monkeypatch, tmp_path):
    """Phase 4 guarantee re-checked for the partial path as well: turning
    STT_FLUSH_DIAG_FILE on must not change a single outgoing message or
    engine call."""
    monkeypatch.setattr(speaker_session_module, "PARTIAL_CYCLE_SECONDS", 0.05)

    async def run():
        ws = FakeWebSocket()
        engine = FakeEngine(supports_partial=True, partial_words=["one", "two"],
                            final_text="one two")
        buf = _buf(min_utterance_seconds=0.05)
        task = await _session(ws, None, engine, buf, SessionRegistry())
        await _speak(ws, marker=10000, n_speech=4, n_quiet=5)
        await asyncio.sleep(0.05)
        ws.disconnect()
        await task
        # Wire messages and final calls are deterministic (the relay sends
        # each new partial word once and one final per flush). The raw
        # partial_calls list is NOT: its length tracks how many 50 ms cycles
        # happened to fire, so it is only checked for activity below.
        return _payloads(ws), list(engine.final_calls), len(engine.partial_calls)

    monkeypatch.delenv("STT_FLUSH_DIAG_FILE", raising=False)
    off = await run()
    monkeypatch.setenv("STT_FLUSH_DIAG_FILE", str(tmp_path / "d.jsonl"))
    on = await run()
    assert on[0] == off[0], f"wire messages differ:\n on={on[0]!r}\noff={off[0]!r}"
    assert on[1] == off[1], "engine final calls differ between diagnostics on/off"
    assert on[2] > 0 and off[2] > 0, "expected at least one partial decode in each run"
