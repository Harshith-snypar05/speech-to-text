"""Second-pass refinement: acceptance guard, bounded queue, failure isolation, store update, wire format."""
import asyncio

from core import refiner as R
from core.protocol import refine_message


def test_accept_punctuation_and_case_fix():
    assert R.accept("hello can you hear me", "Hello, can you hear me?")


def test_reject_identical_empty_hallucinated_and_truncated():
    assert not R.accept("hello can you hear me", "hello can you hear me")
    assert not R.accept("hello can you hear me", "")
    assert not R.accept("hello can you hear me", "thank you for watching see you next time")
    assert not R.accept("one two three four five six", "one")
    assert not R.accept("one two three", "one two three four five six seven eight")


def test_refine_message_has_no_text_key():
    m = refine_message(3, "a b", "A, b.")
    assert "text" not in m and m["type"] == "refine" and m["seq"] == 3


class FakeStream:
    def __init__(self, text, fail=False, delay=0.0):
        self.text, self.fail, self.delay = text, fail, delay

    async def send_audio(self, pcm):
        pass

    async def flush(self):
        pass

    async def events(self):
        await asyncio.sleep(self.delay)
        if self.fail:
            raise ConnectionError("worker down")
        yield {"type": "partial", "text": "x"}
        yield {"type": "final", "text": self.text}

    async def close(self):
        pass


class FakeEngine:
    def __init__(self, **kw):
        self.kw = kw

    async def open_stream(self):
        return FakeStream(**self.kw)


PCM = b"\x01\x00" * R.SAMPLE_RATE  # 1 s


def _collect():
    got = []

    async def on(x):
        got.append(x)

    return got, on


def test_applies_accepted_refinement():
    async def go():
        r = R.Refiner(FakeEngine(text="Hello, can you hear me?"))
        got, on = _collect()
        assert r.submit(PCM, "hello can you hear me", on)
        await asyncio.gather(*r._tasks)
        return got, r.stats
    got, stats = asyncio.run(go())
    assert got == ["Hello, can you hear me?"] and stats["applied"] == 1


def test_failure_keeps_live_text_and_counts():
    async def go():
        r = R.Refiner(FakeEngine(text="", fail=True))
        got, on = _collect()
        r.submit(PCM, "hello there", on)
        await asyncio.gather(*r._tasks)
        return got, r.stats, r._pending
    got, stats, pending = asyncio.run(go())
    assert got == [] and stats["failed"] == 1 and pending == 0


def test_timeout_keeps_live_text():
    async def go():
        r = R.Refiner(FakeEngine(text="Hello there.", delay=2), timeout=0.1)
        got, on = _collect()
        r.submit(PCM, "hello there", on)
        await asyncio.gather(*r._tasks)
        return got, r.stats
    got, stats = asyncio.run(go())
    assert got == [] and stats["failed"] == 1


def test_queue_is_bounded_and_short_audio_skipped():
    async def go():
        r = R.Refiner(FakeEngine(text="Hello there.", delay=0.2), max_pending=2)
        _, on = _collect()
        ok = [r.submit(PCM, "hello there", on) for _ in range(4)]
        short = r.submit(b"\x00\x00" * 100, "hello there", on)
        await asyncio.gather(*r._tasks)
        return ok, short, r.stats
    ok, short, stats = asyncio.run(go())
    assert ok == [True, True, False, False] and short is False and stats["dropped"] == 2


def test_store_update_only_when_line_unchanged(monkeypatch):
    from core import transcript_store as ts

    class NoMirror:
        record_event = staticmethod(lambda *a: None)
        refine_event = staticmethod(lambda *a: None)

    monkeypatch.setattr(ts, "mongo_mirror", NoMirror)
    sid = "refine_test_session_unit"
    ts._conn.execute("DELETE FROM transcript_events WHERE session_id = ?", (sid,))
    s0 = ts.record_event(sid, "hello there")
    s1 = ts.record_event(sid, "how are you")
    assert (s0, s1) == (0, 1)
    assert ts.update_event(sid, 0, "hello there", "Hello there.")
    assert not ts.update_event(sid, 0, "hello there", "Other")  # line already replaced
    assert ts.get_history(sid) == ["Hello there.", "how are you"]
    ts._conn.execute("DELETE FROM transcript_events WHERE session_id = ?", (sid,))
    ts._conn.commit()
