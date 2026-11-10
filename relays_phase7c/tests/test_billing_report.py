"""Relay-side usage reporting: cumulative reports, reconnect carry-on, the closing report survives a transient failure."""
import asyncio

from core import billing as B

SR = 16000


def feed(c, seconds):
    """Offer `seconds` of audio; returns the seconds the allowance accepted."""
    return c.take(int(round(seconds * SR)), SR) / SR


def _ctx(monkeypatch, posts, fail_first=0, base=0.0, remaining=300):
    calls = {"n": 0}

    def fake_post(path, body):
        calls["n"] += 1
        if calls["n"] <= fail_first:
            raise ConnectionError("api down")
        posts.append(body)
        return {"allowed": True, "remaining_seconds": 100}

    monkeypatch.setattr(B, "_post", fake_post)
    monkeypatch.setattr(B, "FINAL_RETRY_DELAY", 0.0)
    return B.BillingContext("u1", "sess_1234567", remaining, base)


def test_periodic_and_final_reports_are_cumulative(monkeypatch):
    posts = []

    async def go():
        c = _ctx(monkeypatch, posts)
        for _ in range(25):  # 25 x 2 s = 50 s
            feed(c, 2.0)
            await asyncio.sleep(0)
            await asyncio.sleep(0.01)
        await c.finish()
    asyncio.run(go())
    assert posts[-1]["final"] is True and posts[-1]["cumulative_seconds"] == 50.0
    seconds = [p["cumulative_seconds"] for p in posts]
    assert seconds == sorted(seconds)


def test_final_report_retried_after_transient_failure(monkeypatch):
    posts = []

    async def go():
        c = _ctx(monkeypatch, posts, fail_first=2)
        feed(c, 7.0)
        await c.finish()
    asyncio.run(go())
    assert len(posts) == 1 and posts[0]["final"] is True and posts[0]["cumulative_seconds"] == 7.0


def test_final_report_gives_up_after_attempts(monkeypatch):
    posts = []

    async def go():
        c = _ctx(monkeypatch, posts, fail_first=99)
        feed(c, 7.0)
        await c.finish()
    asyncio.run(go())
    assert posts == []


def test_reconnect_continues_from_base(monkeypatch):
    posts = []

    async def go():
        c = _ctx(monkeypatch, posts, base=10.0)
        feed(c, 10.0)
        await c.finish()
    asyncio.run(go())
    assert posts[-1]["cumulative_seconds"] == 20.0


def test_chunk_is_cut_at_the_exact_limit(monkeypatch):
    async def go():
        c = _ctx(monkeypatch, [], remaining=60)
        for _ in range(59):
            assert feed(c, 1.0) == 1.0 and not c.exhausted
        assert feed(c, 1.0) == 1.0   # ends exactly on the limit
        assert c.exhausted and c.audio_seconds == 60.0 and c.room() == 0.0
        assert feed(c, 1.0) == 0.0   # nothing past the limit is accepted
        assert c.audio_seconds == 60.0 and c.dropped_seconds == 1.0
    asyncio.run(go())


def test_crossing_chunk_is_truncated_not_extended(monkeypatch):
    c = _ctx(monkeypatch, [], remaining=10)
    assert feed(c, 9.6) == 9.6
    assert abs(feed(c, 1.0) - 0.4) < 1 / SR   # only the 0.4 s that fit
    assert c.exhausted and c.audio_seconds == 10.0


def test_limit_counts_from_the_billed_base_on_reconnect(monkeypatch):
    async def go():
        c = _ctx(monkeypatch, [], base=40.0, remaining=20)   # 60 s ceiling, 40 s already billed
        assert feed(c, 25.0) == 20.0
        assert c.exhausted and c.audio_seconds == 60.0
    asyncio.run(go())


def test_server_denial_stops_without_extending(monkeypatch):
    def deny(path, body):
        return {"allowed": False, "remaining_seconds": 0}
    monkeypatch.setattr(B, "_post", deny)

    async def go():
        c = B.BillingContext("u1", "sess_1234567", 300, 0.0)
        feed(c, 12.0)   # triggers a periodic report
        await asyncio.sleep(0.05)
        assert c.exhausted and feed(c, 1.0) == 0.0
    asyncio.run(go())


def test_report_never_grows_the_ceiling_beyond_server_base(monkeypatch):
    monkeypatch.setattr(B, "_post", lambda path, body: {"allowed": True, "base_seconds": 10.0, "remaining_seconds": 300})

    async def go():
        c = B.BillingContext("u1", "sess_1234567", 300, 0.0)
        feed(c, 10.6)
        await asyncio.sleep(0.05)
        assert c._remaining == 310.0   # anchored to the server's billed seconds, not to our 10.6
    asyncio.run(go())
