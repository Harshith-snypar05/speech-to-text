"""Phase 4: flush diagnostics are observational only. Same scenario run with
diagnostics off and on must give identical outgoing messages and engine calls."""
import asyncio
import json

import pytest

from core.session_manager import SessionRegistry
from core.speaker_session import run_speaker_session

from .conftest import FakeEngine, FakeWebSocket, make_speech_chunk
from .test_speaker_session import _buf

SPEECH = dict(amplitude=0.5, seconds=0.1)
QUIET = dict(amplitude=0.001, seconds=0.1)


async def _scenario(chunks, engine, buf_kw=None, disconnect=True):
    ws = FakeWebSocket()
    buf = _buf(**(buf_kw or {}))
    task = asyncio.create_task(run_speaker_session(ws, None, engine, buf, SessionRegistry()))
    await asyncio.sleep(0.02)
    for kw in chunks:
        ws.feed(make_speech_chunk(**kw))
        await asyncio.sleep(0.005)
    await asyncio.sleep(0.05)
    if disconnect:
        ws.disconnect()
        await task
        return [json.loads(m) for m in ws.sent], list(engine.final_calls)
    # Snapshot before teardown so the disconnect flush is not included.
    result = [json.loads(m) for m in ws.sent], list(engine.final_calls)
    ws.disconnect()
    await task
    return result


def _read(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]


SCENARIOS = {
    "silence_hang": ([SPEECH] * 3 + [QUIET] * 4, {}, dict(final_text="hello there")),
    "forced_cap": ([SPEECH] * 12, dict(max_utterance_seconds=0.5), dict(final_text="capped words")),
    "short_remainder": ([SPEECH] * 5 + [SPEECH] + [QUIET] * 2, dict(max_utterance_seconds=0.5, min_utterance_seconds=0.3), dict(final_text="x")),
    "empty_text": ([SPEECH] * 3 + [QUIET] * 4, {}, dict(final_text="")),
    "engine_raises": ([SPEECH] * 3 + [QUIET] * 4, {}, dict(raise_on_final=True)),
    "disconnect_flush": ([SPEECH] * 3, {}, dict(final_text="tail")),
}


@pytest.mark.parametrize("name", list(SCENARIOS))
async def test_behaviour_identical_with_diagnostics_on_and_off(name, tmp_path, monkeypatch):
    chunks, buf_kw, eng_kw = SCENARIOS[name]
    monkeypatch.delenv("STT_FLUSH_DIAG_FILE", raising=False)
    off = await _scenario(chunks, FakeEngine(**eng_kw), buf_kw)
    log = tmp_path / "diag.jsonl"
    monkeypatch.setenv("STT_FLUSH_DIAG_FILE", str(log))
    on = await _scenario(chunks, FakeEngine(**eng_kw), buf_kw)
    assert on == off
    assert log.exists() and _read(log)


async def test_disabled_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("STT_FLUSH_DIAG_FILE", raising=False)
    monkeypatch.chdir(tmp_path)
    await _scenario(*SCENARIOS["silence_hang"][:1], FakeEngine(final_text="a"))
    assert list(tmp_path.iterdir()) == []


async def test_records_final_sent_silence_hang(tmp_path, monkeypatch):
    log = tmp_path / "d.jsonl"
    monkeypatch.setenv("STT_FLUSH_DIAG_FILE", str(log))
    await _scenario(SCENARIOS["silence_hang"][0], FakeEngine(final_text="hello there"), disconnect=False)
    r = _read(log)[0]
    assert r["reason"] == "silence_hang" and r["outcome"] == "final_sent"
    assert r["decode_attempted"] and r["final_constructed"] and r["final_send_called"]
    assert r["text_empty"] is False and r["text_words"] == 2
    assert r["buffer_samples"] == r["buffer_bytes"] // 2 and r["seq"] == 1 and r["conn_id"]
    assert r["audio_received_s"] == pytest.approx(0.6, abs=0.01)
    assert "hello" not in json.dumps(r)  # no transcript text logged


async def test_records_forced_cap(tmp_path, monkeypatch):
    log = tmp_path / "d.jsonl"
    monkeypatch.setenv("STT_FLUSH_DIAG_FILE", str(log))
    await _scenario(SCENARIOS["forced_cap"][0], FakeEngine(final_text="capped words"),
                    SCENARIOS["forced_cap"][1])
    recs = _read(log)
    assert recs[0]["reason"] == "forced_cap"
    assert [r["seq"] for r in recs] == list(range(1, len(recs) + 1))
    assert len({r["conn_id"] for r in recs}) == 1


async def test_records_not_pending_drop(tmp_path, monkeypatch):
    log = tmp_path / "d.jsonl"
    monkeypatch.setenv("STT_FLUSH_DIAG_FILE", str(log))
    eng = FakeEngine(final_text="x")
    await _scenario(*SCENARIOS["short_remainder"][:1], eng, SCENARIOS["short_remainder"][1])
    drops = [r for r in _read(log) if r["outcome"] == "dropped_not_pending"]
    assert drops, "short remainder after forced cap must be logged as not-pending drop"
    d = drops[0]
    assert d["decode_attempted"] is False and d["final_constructed"] is False and d["has_pending"] is False
    assert d["early_return"] == "not_pending" and d["buffer_samples"] > 0


async def test_records_empty_text_drop(tmp_path, monkeypatch):
    log = tmp_path / "d.jsonl"
    monkeypatch.setenv("STT_FLUSH_DIAG_FILE", str(log))
    msgs, _ = await _scenario(SCENARIOS["empty_text"][0], FakeEngine(final_text=""), disconnect=False)
    assert [m for m in msgs if m.get("partial") is False] == []
    r = _read(log)[0]
    assert r["outcome"] == "dropped_empty_text" and r["decode_attempted"] and r["text_empty"] is True
    assert r["final_constructed"] is False and r["final_send_called"] is False


async def test_records_exception_drop(tmp_path, monkeypatch):
    log = tmp_path / "d.jsonl"
    monkeypatch.setenv("STT_FLUSH_DIAG_FILE", str(log))
    await _scenario(SCENARIOS["engine_raises"][0], FakeEngine(raise_on_final=True), disconnect=False)
    r = _read(log)[0]
    assert r["outcome"] == "dropped_exception" and r["decode_attempted"] and r["exception"]


async def test_unwritable_log_path_does_not_break_session(tmp_path, monkeypatch):
    monkeypatch.setenv("STT_FLUSH_DIAG_FILE", str(tmp_path / "no" / "such" / "dir" / "x.jsonl"))
    msgs, calls = await _scenario(SCENARIOS["silence_hang"][0], FakeEngine(final_text="ok"), disconnect=False)
    assert len([m for m in msgs if m.get("partial") is False]) == 1 and len(calls) == 1
