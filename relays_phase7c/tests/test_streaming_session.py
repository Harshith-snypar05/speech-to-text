import asyncio
import json

from core.session_manager import SessionRegistry
from core.streaming_session import run_streaming_session

from .conftest import FakeWebSocket, make_speech_chunk


class FakeStream:
    """Stands in for the ASR worker: yields scripted events, records what the session sent."""

    def __init__(self):
        self.audio, self.flushes, self.closed = [], 0, False
        self.q = asyncio.Queue()

    async def send_audio(self, pcm):
        self.audio.append(pcm)

    async def flush(self):
        self.flushes += 1

    async def events(self):
        while True:
            ev = await self.q.get()
            if ev is None:
                return
            yield ev

    async def close(self):
        self.closed = True
        await self.q.put(None)


class FakeStreamEngine:
    model_key = "fake"

    def __init__(self, has_eou):
        self.has_eou = has_eou
        self.stream = FakeStream()

    async def open_stream(self):
        return self.stream


def _payloads(ws):
    return [json.loads(m) for m in ws.sent]


async def test_partials_are_word_deltas_and_final_resets():
    ws, eng = FakeWebSocket(), FakeStreamEngine(has_eou=True)
    task = asyncio.create_task(run_streaming_session(ws, "streamtest1", eng, SessionRegistry()))
    await asyncio.sleep(0.02)
    ws.feed(make_speech_chunk(amplitude=0.5, seconds=0.1))
    for text in ("ask", "ask not", "ask not what"):
        await eng.stream.q.put({"type": "partial", "text": text})
    await eng.stream.q.put({"type": "final", "text": "ask not what"})
    await eng.stream.q.put({"type": "partial", "text": "your"})
    await asyncio.sleep(0.05)
    p = _payloads(ws)
    # the newest word is held back (may be a sub-word fragment); the final carries it
    assert [x["text"] for x in p if x.get("partial") is True] == ["ask", "not"]
    await asyncio.sleep(0.35)  # tail hold expires: "your" is released although nothing followed it
    p = _payloads(ws)
    assert [x["text"] for x in p if x.get("partial") is True] == ["ask", "not", "your"]
    assert [x["text"] for x in p if x.get("partial") is False] == ["ask not what"]
    ws.disconnect()
    await task
    assert eng.stream.closed and len(eng.stream.audio) == 1


async def test_non_eou_model_flushes_after_silence_once():
    ws, eng = FakeWebSocket(), FakeStreamEngine(has_eou=False)
    task = asyncio.create_task(run_streaming_session(ws, "streamtest2", eng, SessionRegistry()))
    await asyncio.sleep(0.02)
    for _ in range(3):
        ws.feed(make_speech_chunk(amplitude=0.5, seconds=0.1))
    for _ in range(8):  # 0.8 s silence > 0.5 s endpoint
        ws.feed(make_speech_chunk(amplitude=0.001, seconds=0.1))
    await asyncio.sleep(0.05)
    assert eng.stream.flushes == 1  # one endpoint flush, not one per silent chunk
    ws.disconnect()
    await task


async def test_fragment_is_never_sent_before_it_is_completed():
    ws, eng = FakeWebSocket(), FakeStreamEngine(has_eou=True)
    task = asyncio.create_task(run_streaming_session(ws, "streamtest4", eng, SessionRegistry()))
    await asyncio.sleep(0.02)
    for text in ("a sess", "a session"):
        await eng.stream.q.put({"type": "partial", "text": text})
        await asyncio.sleep(0.02)
    await eng.stream.q.put({"type": "partial", "text": "a session called"})
    await asyncio.sleep(0.05)
    sent = [x["text"] for x in _payloads(ws) if x.get("partial") is True]
    assert "sess" not in sent and sent == ["a", "session"]
    ws.disconnect()
    await task


async def test_eou_model_also_endpoints_on_silence_once():
    ws, eng = FakeWebSocket(), FakeStreamEngine(has_eou=True)
    task = asyncio.create_task(run_streaming_session(ws, "streamtest3", eng, SessionRegistry()))
    await asyncio.sleep(0.02)
    for _ in range(3):
        ws.feed(make_speech_chunk(amplitude=0.5, seconds=0.1))
    for _ in range(8):
        ws.feed(make_speech_chunk(amplitude=0.001, seconds=0.1))
    await asyncio.sleep(0.05)
    assert eng.stream.flushes == 1  # EOU token may not fire; silence still closes the utterance
    ws.disconnect()
    await task


async def test_audio_past_the_allowance_never_reaches_the_engine(monkeypatch):
    from core import billing as B
    monkeypatch.setattr(B, "_post", lambda path, body: {"allowed": True, "remaining_seconds": 0})
    monkeypatch.setattr(B, "FINAL_RETRY_DELAY", 0.0)
    ws, eng = FakeWebSocket(), FakeStreamEngine(has_eou=True)
    ctx = B.BillingContext("u1", "limit_test_1", 2, 0.0)   # 2 s allowance
    task = asyncio.create_task(run_streaming_session(ws, "limit_test_1", eng, SessionRegistry(), billing=ctx))
    await asyncio.sleep(0.02)
    for _ in range(4):   # 4 x 0.75 s offered
        ws.feed(make_speech_chunk(amplitude=0.5, seconds=0.75))
    await asyncio.wait_for(task, timeout=6)
    sent_bytes = sum(len(a) for a in eng.stream.audio)
    assert sent_bytes == 2 * 16000 * 2          # exactly 2.0 s reached the engine, not a sample more
    assert ctx.audio_seconds == 2.0
    assert ws.close_code == 4402 and ws.close_reason == "out_of_minutes"
    msgs = [json.loads(m) for m in ws.sent]
    assert any(m.get("type") == "error" and m.get("code") == "out_of_minutes" for m in msgs)


async def test_free_session_cap_closes_with_session_limit_reason(monkeypatch):
    from core import billing as B
    monkeypatch.setattr(B, "_post", lambda path, body: {"allowed": True, "remaining_seconds": 0})
    monkeypatch.setattr(B, "FINAL_RETRY_DELAY", 0.0)
    ws, eng = FakeWebSocket(), FakeStreamEngine(has_eou=True)
    ctx = B.BillingContext("u1", "limit_test_2", 2, 0.0, 2)   # allowance of 2 s that is the plan's per-session cap
    task = asyncio.create_task(run_streaming_session(ws, "limit_test_2", eng, SessionRegistry(), billing=ctx))
    await asyncio.sleep(0.02)
    for _ in range(4):
        ws.feed(make_speech_chunk(amplitude=0.5, seconds=0.75))
    await asyncio.wait_for(task, timeout=6)
    assert ws.close_code == 4402 and ws.close_reason == "session_limit"
    msgs = [json.loads(m) for m in ws.sent]
    assert any(m.get("type") == "error" and m.get("code") == "session_limit" and "30 minutes" in m.get("message", "") for m in msgs)


async def test_engine_socket_loss_is_reported_not_a_silent_normal_close():
    import websockets

    class DyingStream(FakeStream):
        async def send_audio(self, pcm):
            raise websockets.exceptions.ConnectionClosedError(None, None)

    class Eng(FakeStreamEngine):
        def __init__(self):
            super().__init__(True)
            self.stream = DyingStream()

    ws, eng = FakeWebSocket(), Eng()
    task = asyncio.create_task(run_streaming_session(ws, "asrlost_1", eng, SessionRegistry()))
    await asyncio.sleep(0.02)
    ws.feed(make_speech_chunk(amplitude=0.5, seconds=0.1))
    await asyncio.wait_for(task, timeout=5)
    assert ws.close_code == 1011 and ws.close_reason == "asr_connection_lost"
    assert any(json.loads(m).get("code") == "asr_connection_lost" for m in ws.sent)
