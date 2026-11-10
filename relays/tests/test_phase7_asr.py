"""Phase 7 real-ASR regression tests: the actual Parakeet TDT 0.6B v3 q8_0
model through the production ctypes binding (ParakeetNativeEngine), no mocks.

Covers the empty-decode defect family from Phase 5/6 (area A) and a normal
non-empty final, both direct and through the real session loop. The five
`*_dropped_A.wav` slices are the exact utterance buffers Phase 6 replayed
and saw decode to "" with no left context -- they are the reproduction
corpus for the missing-final defect.

Skips when the shared library, model, or fixture audio is absent (same
guard style as test_engines.py). One module-scoped engine: the model is
~668 MB and loading it once for the whole file matters on this machine.

Pinning note: several assertions here encode CURRENT (defective) behaviour --
an empty decode still sends no final. When an empty-decode handling change
is approved, these are the assertions that must be updated deliberately.
"""
import asyncio
import json
import time
import wave
from pathlib import Path

import pytest

from core.session_manager import SessionRegistry
from core.speaker_session import run_speaker_session
from engines.parakeet_native_engine import ParakeetNativeEngine, find_library

from .conftest import FakeWebSocket
from .test_speaker_session import _buf

ROOT = Path(__file__).resolve().parent.parent.parent  # speech-to-text/
SHARED_BUILD_DIR = ROOT / "whisper.cpp" / "build-shared" / "bin"
PARAKEET_MODEL = ROOT / "whisper.cpp" / "models" / "ggml-parakeet-tdt-0.6b-v3-q8_0.bin"
JFK_WAV = ROOT / "whisper.cpp" / "samples" / "jfk.wav"
EMPTY_FIXTURE_DIR = ROOT / "benchmarks" / "results" / "phase6_replay" / "audio"

# The five Phase 5 missing-final cases, used only as English-speech
# regression fixtures (no native-language investigation).
EMPTY_CASES = ["assamese_03817", "assamese_06152", "kannada_00197",
               "kashmiri_03111", "bodo_03621"]

AVAILABLE = (
    JFK_WAV.exists()
    and PARAKEET_MODEL.exists()
    and find_library(SHARED_BUILD_DIR) is not None
    and all((EMPTY_FIXTURE_DIR / f"{c}_dropped_A.wav").exists() for c in EMPTY_CASES)
)

pytestmark = pytest.mark.skipif(
    not AVAILABLE,
    reason="shared library (parakeet.dll), model (~669MB), JFK sample, or Phase 6 "
           "empty-decode fixtures not available",
)


def _read_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as f:
        assert f.getframerate() == 16000, f"{path.name} must be 16 kHz"
        return f.readframes(f.getnframes())


class CountingEngine(ParakeetNativeEngine):
    """Production engine plus a call log, so session-level tests can count
    how many decodes actually happened (ParakeetNativeEngine has no hooks)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.final_calls: list[bytes] = []

    async def transcribe_final(self, pcm_bytes: bytes) -> str:
        self.final_calls.append(pcm_bytes)
        return await super().transcribe_final(pcm_bytes)


async def _stream_into_session(engine, pcm: bytes, session_id: str | None, buf_kw: dict,
                               diag_path, tail_silence_s: float = 1.0):
    """Drive one real session: feed `pcm` as 100 ms frames (faster than
    real time -- the partial cycle is wall-clock, so this just keeps the
    test short), then `tail_silence_s` of digital silence so the trailing
    utterance flushes via the silence hang WHILE THE CONNECTION IS STILL
    OPEN, exactly as it does for a real client that keeps streaming after
    the speaker stops. Then disconnect.

    Two things this has to get right, both learned the hard way:
    - The tail matters: a final flushed after the socket is closed can
      never be delivered (send() raises ConnectionClosed and the relay
      logs and drops it), so asserting finals without it would test the
      harness rather than the relay.
    - Waiting matters more: a decode of several seconds outlives any fixed
      sleep, so disconnect would land mid-decode and lose the final anyway.
      STT_FLUSH_DIAG_FILE (Phase 4, observational only) is the completion
      signal: a record is appended only AFTER decode and send have both
      finished, and `audio_received_s` tells us the record belongs to the
      flush that consumed all the audio (the tail flush), not an earlier
      mid-utterance one.

    Returns (wire payloads, this session's final-call list, diag records).
    """
    assert diag_path is not None, "session-level ASR tests run with diagnostics on"
    engine.final_calls.clear()
    ws = FakeWebSocket()
    buf = _buf(**buf_kw)
    task = asyncio.create_task(
        run_speaker_session(ws, session_id, engine, buf, SessionRegistry())
    )
    await asyncio.sleep(0.02)
    frame = 1600 * 2

    async def feed_frames(data: bytes, pause: float = 0.002):
        for i in range(0, len(data), frame):
            ws.feed(data[i:i + frame])
            await asyncio.sleep(pause)

    await feed_frames(pcm)
    pcm_s = len(pcm) / (16000 * 2)
    await feed_frames(b"\x00" * int(16000 * 2 * tail_silence_s))

    async def read_records():
        if not diag_path.exists():
            return []
        return [json.loads(line) for line in diag_path.read_text(encoding="utf-8").splitlines()]

    deadline = time.monotonic() + 15
    records = []
    while time.monotonic() < deadline:
        records = await read_records()
        if any(r.get("audio_received_s", -1) >= pcm_s for r in records):
            break
        await asyncio.sleep(0.05)
    else:
        raise AssertionError(
            f"no flush completed while connected (need a record with "
            f"audio_received_s >= {pcm_s}); records={records!r}"
        )

    ws.disconnect()
    await task
    assert task.exception() is None
    return [json.loads(m) for m in ws.sent], list(engine.final_calls), await read_records()


@pytest.fixture(scope="module")
def _shared_engine():
    e = CountingEngine(SHARED_BUILD_DIR, PARAKEET_MODEL)
    yield e
    asyncio.run(e.shutdown())


@pytest.fixture
def engine(_shared_engine):
    """Function-scoped handle to the one loaded model.

    ParakeetNativeEngine's asyncio.Lock binds itself to whichever event
    loop first *contends* on it (uncontended acquire never touches the
    loop). Every test here runs in its own loop via asyncio.run, so a lock
    carried over from a previous test raises "bound to a different event
    loop" -- seen as a sporadic dropped_exception, only under contention.
    Production never hits this: one relay process, one loop for its whole
    life. The fix is therefore test-side: fresh unbound lock per test.
    Model load -- the expensive part -- still happens once per module.
    """
    _shared_engine._call_lock = asyncio.Lock()
    _shared_engine.final_calls.clear()
    return _shared_engine


# ------------------------------------------------- empty decode (area A)
@pytest.mark.parametrize("case", EMPTY_CASES)
def test_empty_decode_without_context_is_still_empty(engine, case):
    """Phase 6 reproduction, pinned: with NO left context, each of the five
    missing-final buffers must still decode to empty text. If this ever
    fails the model/quantization changed underneath us -- investigate
    before touching relay code."""
    pcm = _read_pcm(EMPTY_FIXTURE_DIR / f"{case}_dropped_A.wav")
    text = asyncio.run(engine.transcribe_final(pcm))
    assert text.strip() == "", (
        f"{case}: expected empty decode without context (Phase 6 finding), got {text!r}"
    )


@pytest.mark.parametrize("case", EMPTY_CASES)
def test_empty_decode_with_pending_utterance_sends_no_final(engine, case, monkeypatch, tmp_path):
    """Area A end-to-end with the REAL model: stream the empty-decode slice
    into a real session. The buffer is pending, the model returns "", and
    the relay drops it -- no final reaches the client, the diagnostics say
    `dropped_empty_text` with no final ever constructed, and no exception
    escapes. This is the defect itself, pinned so that any change to
    empty-decode handling is visible here first.

    Deliberate test config, and the reason for it:
    - `min_utterance=0.05` so the softest fixture (bodo_03621, only ~0.2 s
      above the RMS threshold) still counts as a pending utterance.
    - `silence_hang=30` so no silence-triggered flush can split the slice.
      This matters: the slices contain internal pauses, and a sub-buffer
      cut at a pause decodes to NON-EMPTY text (measured), which would send
      a real final and hide the defect we are pinning.
    - `max_utterance=len(pcm)` so the forced cap fires on the LAST frame of
      the slice, decoding the exact bytes the direct test decodes, while
      the connection is still open.
    The silence tail then only serves to keep the socket alive until that
    flush has finished, so `finals == []` is the relay's decision rather
    than a send failing on a dead socket.
    """
    diag = tmp_path / "phase7_asr.jsonl"
    monkeypatch.setenv("STT_FLUSH_DIAG_FILE", str(diag))
    pcm = _read_pcm(EMPTY_FIXTURE_DIR / f"{case}_dropped_A.wav")
    pcm_s = len(pcm) / (16000 * 2)
    buf_kw = dict(min_utterance_seconds=0.05, silence_hang_seconds=30.0,
                  max_utterance_seconds=pcm_s)
    payloads, final_calls, records = asyncio.run(
        _stream_into_session(engine, pcm, None, buf_kw, diag)
    )
    finals = [p for p in payloads if p.get("partial") is False]
    assert len(final_calls) >= 1, "pending audio must reach the model"
    assert finals == [], (
        f"{case}: empty decode currently sends NO final (Phase 5 defect, still present)"
    )
    cap = [r for r in records if r["reason"] == "forced_cap" and r["decode_attempted"]]
    assert cap, f"expected a forced-cap flush of the whole slice, got {records!r}"
    assert cap[0]["buffer_s"] == pytest.approx(pcm_s, abs=0.01), (
        "the decode must see the whole slice, not a pause-split sub-buffer "
        f"(got {cap[0]['buffer_s']}s of {pcm_s}s)"
    )
    dropped = [r for r in records
               if r["outcome"] == "dropped_empty_text" and r["decode_attempted"]]
    assert dropped, f"expected a dropped_empty_text record, got {records!r}"
    assert all(r["final_constructed"] is False and r["final_send_called"] is False
               for r in dropped), "an empty decode must never build or send a final"


# ------------------------------------------- normal non-empty final
def test_normal_non_empty_final_direct(engine):
    text = asyncio.run(engine.transcribe_final(_read_pcm(JFK_WAV)))
    assert text.strip(), "JFK sample must decode to non-empty text"
    lowered = text.lower()
    assert "country" in lowered and "ask" in lowered, f"unexpected JFK decode: {text!r}"


def test_normal_non_empty_final_through_session(engine, monkeypatch, tmp_path):
    """Same clip through the real session loop: every final that reaches
    the wire is non-empty, every decode produces exactly one final (no
    silently dropped utterance on normal speech), the JFK content shows up,
    and the buffer is empty at disconnect so nothing is left behind."""
    diag = tmp_path / "phase7_asr_jfk.jsonl"
    monkeypatch.setenv("STT_FLUSH_DIAG_FILE", str(diag))
    payloads, final_calls, records = asyncio.run(
        _stream_into_session(engine, _read_pcm(JFK_WAV), "phase7asrjfk", {}, diag)
    )
    finals = [p for p in payloads if p.get("partial") is False]
    assert finals, "expected at least one final for the JFK clip"
    assert all(f["text"].strip() for f in finals), "no final may be empty on normal speech"
    joined = " ".join(f["text"] for f in finals).lower()
    assert "country" in joined, f"JFK content missing from finals: {finals!r}"

    final_sent = [r for r in records if r["outcome"] == "final_sent"]
    assert len(final_sent) == len(finals), (
        f"wire finals ({len(finals)}) must match finals the relay reports "
        f"sending ({len(final_sent)}); records={records!r}"
    )
    assert len(final_calls) == len(final_sent), (
        "every real-model decode of normal speech must produce a final "
        "(count mismatch = a silently dropped utterance)"
    )
    assert any(r["outcome"] == "dropped_not_pending" for r in records), \
        "buffer must be empty at disconnect (trailing silence only)"
