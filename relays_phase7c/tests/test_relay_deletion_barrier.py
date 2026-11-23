"""Account-deletion barrier in the relay (Phase 3).

A tombstoned (`deleting`) account must not be able to create or change relay-owned records, whether the relay learns about
the tombstone at admission, on reconnect, through a usage report, or only when it tries to write. All tests are
deterministic and use mongomock; nothing talks to a live database or API.
"""
import asyncio
import importlib
import json
import sys
import time

import mongomock
import pytest
from bson import ObjectId

import core.billing as B
import core.mongo_mirror as M
import core.transcript_store as store
from core.audio_processor import UtteranceBuffer
from core.session_manager import SessionRegistry
from core.speaker_session import run_speaker_session

from .conftest import FakeEngine, FakeWebSocket, make_speech_chunk

SR = 16000
SID = "sess_barrier_01"


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    M._blocked.clear()
    store._blocked.clear()
    # these tests are about accounts, so run in "owned" mode (the relay is wired to the API)
    monkeypatch.setattr(M, "owned_mode", lambda: True)
    yield
    M._blocked.clear()
    store._blocked.clear()


@pytest.fixture
def db():
    return mongomock.MongoClient()["scriptliv"]


def _account(db, deleting=False, with_session=True, sid=SID):
    uid = ObjectId()
    user = {"_id": uid, "email": "a@example.com"}
    if deleting:
        user["deleting"] = True
    db.users.insert_one(user)
    if with_session:
        # what the API's /internal/v1/sessions/start does when it admits the speaker
        db.sessions.insert_one({"session_id": sid, "owner_id": str(uid), "started_at": 1.0, "ended_at": None})
    return uid


def _tombstone(db, uid):
    db.users.update_one({"_id": uid}, {"$set": {"deleting": True}})


def _events(db, sid=SID):
    return list(db.transcript_events.find({"session_id": sid}))


# --------------------------------------------------------------------------------------------------- mirror: guard

def test_active_account_events_are_written(db):
    _account(db)
    M._apply(db, ("event", SID, 0, "hello", 5.0))
    M._apply(db, ("event", SID, 1, "world", 6.0))
    assert [e["text"] for e in sorted(_events(db), key=lambda e: e["seq"])] == ["hello", "world"]


def test_active_account_start_end_refine_still_work(db):
    _account(db)
    M._apply(db, ("start", SID, "ACODE", 10.0, False))
    M._apply(db, ("event", SID, 0, "helo", 11.0))
    M._apply(db, ("refine", SID, 0, "helo", "hello"))
    M._apply(db, ("end", SID, 20.0))
    s = db.sessions.find_one({"session_id": SID})
    assert s["access_code"] == "ACODE" and s["ended_at"] == 20.0 and s["owner_id"]
    assert _events(db)[0]["text"] == "hello"


def test_tombstoned_account_cannot_create_events_or_session_rows(db):
    uid = _account(db)
    _tombstone(db, uid)
    M._apply(db, ("event", SID, 0, "late words", 5.0))
    M._apply(db, ("start", SID, "ACODE", 6.0, True))
    assert _events(db) == []
    assert "access_code" not in db.sessions.find_one({"session_id": SID})   # not even the session row is touched
    assert M.is_blocked(SID)


@pytest.mark.parametrize("op", [("start", SID, "ACODE", 6.0, True), ("end", SID, 9.0), ("refine", SID, 0, "a", "b"), ("event", SID, 0, "x", 1.0)])
def test_each_op_alone_is_refused_for_a_tombstoned_account(db, op):
    uid = _account(db)
    db.transcript_events.insert_one({"session_id": SID, "seq": 0, "text": "a", "created_at": 1.0})
    _tombstone(db, uid)
    before = (db.sessions.find_one({"session_id": SID}), list(db.transcript_events.find({"session_id": SID})))
    M._apply(db, op)
    after = (db.sessions.find_one({"session_id": SID}), list(db.transcript_events.find({"session_id": SID})))
    assert before == after                      # nothing created, changed or deleted by the relay


def test_relay_never_creates_a_session_row_in_owned_mode(db):
    uid = _account(db, with_session=False)
    M._apply(db, ("start", SID, "ACODE", 6.0, False))
    M._apply(db, ("event", SID, 0, "orphan", 7.0))
    assert db.sessions.count_documents({}) == 0 and _events(db) == []
    assert uid  # account itself is fine; there is just no API-created session to attach to


def test_deleted_account_gets_nothing_recreated(db):
    """User document gone entirely (cascade finished): cleanup ops must not bring any record back."""
    uid = _account(db)
    db.users.delete_one({"_id": uid})
    db.sessions.delete_many({})
    db.transcript_events.delete_many({})
    for op in (("start", SID, "A", 1.0, True), ("event", SID, 0, "x", 2.0), ("end", SID, 3.0), ("refine", SID, 0, "x", "y")):
        M._apply(db, op)
    assert db.sessions.count_documents({}) == 0 and db.transcript_events.count_documents({}) == 0


def test_end_and_refine_never_upsert(db):
    _account(db)
    M._apply(db, ("end", "sess_other_999", 1.0))                      # unknown session: refused, nothing created
    M._apply(db, ("refine", SID, 7, "a", "b"))                        # no such event: nothing created
    assert db.sessions.count_documents({"session_id": "sess_other_999"}) == 0
    assert _events(db) == []


def test_owner_missing_or_malformed_is_refused(db):
    db.sessions.insert_one({"session_id": SID, "owner_id": "not-an-object-id"})
    M._apply(db, ("event", SID, 0, "x", 1.0))
    db.sessions.insert_one({"session_id": "sess_noowner_1"})
    M._apply(db, ("event", "sess_noowner_1", 0, "x", 1.0))
    assert db.transcript_events.count_documents({}) == 0


# ------------------------------------------------------------------------ mirror: race with the tombstone (re-check)

class _TombstoneAfterWrite:
    """Wraps a collection: after the first upsert it applies `hook`, i.e. the tombstone lands while the write is in flight."""

    def __init__(self, coll, hook):
        self._c, self._hook, self._fired = coll, hook, False

    def __getattr__(self, name):
        return getattr(self._c, name)

    def update_one(self, *a, **k):
        r = self._c.update_one(*a, **k)
        if not self._fired:
            self._fired = True
            self._hook()
        return r


class _DB:
    def __init__(self, db, events):
        self._db, self.transcript_events = db, events
        self.sessions, self.users = db.sessions, db.users


def test_tombstone_between_check_and_write_is_undone(db):
    uid = _account(db)
    racing = _DB(db, _TombstoneAfterWrite(db.transcript_events, lambda: _tombstone(db, uid)))
    M._apply(racing, ("event", SID, 0, "in flight", 5.0))
    assert _events(db) == []                       # the write was undone by the re-check
    assert M.is_blocked(SID)


def test_race_then_cascade_leaves_nothing(db):
    """Whichever side wins the race, no event survives once the cascade's events stage has run after the tombstone."""
    uid = _account(db)
    racing = _DB(db, _TombstoneAfterWrite(db.transcript_events, lambda: _tombstone(db, uid)))
    M._apply(racing, ("event", SID, 0, "in flight", 5.0))
    db.transcript_events.delete_many({"session_id": SID})   # cascade stage
    assert _events(db) == []


def test_failed_undo_surfaces_and_the_cascade_still_cleans_up(db):
    uid = _account(db)

    class BadEvents(_TombstoneAfterWrite):
        def delete_one(self, *a, **k):
            raise RuntimeError("db down")

    racing = _DB(db, BadEvents(db.transcript_events, lambda: _tombstone(db, uid)))
    with pytest.raises(RuntimeError):
        M._apply(racing, ("event", SID, 0, "in flight", 5.0))   # surfaces to the worker, which logs and drops (see below)
    # the cascade (which runs after the tombstone) is what removes the leftover row in this case
    db.transcript_events.delete_many({"session_id": SID})
    assert _events(db) == []


# ------------------------------------------------------------------------------------------- mirror: fail closed

class _BrokenUsers:
    def find_one(self, *a, **k):
        raise ConnectionError("mongo unreachable")


def test_status_unverifiable_writes_nothing(db):
    _account(db)
    broken = _DB(db, db.transcript_events)
    broken.users = _BrokenUsers()
    with pytest.raises(ConnectionError):
        M._apply(broken, ("event", SID, 0, "x", 1.0))
    assert _events(db) == []                        # raised before any write; the worker drops the op


def test_worker_step_drops_the_op_and_survives_a_database_error(monkeypatch, db):
    """An error while applying an op must not raise into the thread, must not write, and must force a reconnect."""
    monkeypatch.setattr(M.time, "sleep", lambda s: None)
    _account(db)
    state = {"client": {"scriptliv": _DBWithBrokenUsers(db)}}
    M._step(state, ("event", SID, 0, "x", 1.0))
    assert state["client"] is None and _events(db) == []


class _DBWithBrokenUsers:
    def __init__(self, db):
        self.sessions, self.transcript_events, self.users = db.sessions, db.transcript_events, _BrokenUsers()


def test_worker_step_cannot_connect_writes_nothing(monkeypatch):
    monkeypatch.setenv("MONGODB_URI", "mongodb://unreachable.invalid")
    monkeypatch.setattr(M.time, "sleep", lambda s: None)

    import pymongo

    class Refuse:
        def __init__(self, *a, **k):
            raise pymongo.errors.ServerSelectionTimeoutError("no server")

    monkeypatch.setattr(pymongo, "MongoClient", Refuse)
    state = {}
    M._step(state, ("event", SID, 0, "x", 1.0))     # does not raise
    assert state["client"] is None


def test_legacy_mode_without_api_keeps_old_behaviour(db, monkeypatch):
    monkeypatch.setattr(M, "owned_mode", lambda: False)
    M._apply(db, ("start", "sess_legacy_1", "A", 1.0, False))
    M._apply(db, ("event", "sess_legacy_1", 0, "x", 2.0))
    assert db.sessions.find_one({"session_id": "sess_legacy_1"})["access_code"] == "A"
    assert len(_events(db, "sess_legacy_1")) == 1


# --------------------------------------------------------------------- transcript_store: local purge and no-ops

def test_block_session_purges_and_stops_local_writes():
    store.start_session(SID, "A")
    seq = store.record_event(SID, "kept until the account is found deleting")
    assert seq == 0 and store.get_history(SID)
    store.block_session(SID)
    assert store.get_history(SID) == [] and store.get_session(SID) is None
    assert store.record_event(SID, "late") is None
    assert store.update_event(SID, 0, "a", "b") is False
    store.start_session(SID, "A")      # reconnect-style start: also a no-op
    store.end_session(SID)
    assert store.get_session(SID) is None and store.get_history(SID) == []
    assert store.is_blocked(SID) and M.is_blocked(SID)


def test_other_sessions_unaffected_by_block():
    store.start_session("sess_other_01", "A")
    store.block_session(SID)
    assert store.record_event("sess_other_01", "still fine") == 0
    assert store.get_history("sess_other_01") == ["still fine"]


def test_blocked_set_is_bounded(monkeypatch):
    monkeypatch.setattr(store, "_BLOCKED_MAX", 3)
    monkeypatch.setattr(M, "_BLOCKED_MAX", 3)
    for i in range(10):
        store.block_session(f"sess_{i:08d}")
    assert len(store._blocked) == 3 and len(M._blocked) == 3


# --------------------------------------------------------------- BillingContext: detection while a session runs

def _feed(c, seconds):
    return c.take(int(round(seconds * SR)), SR) / SR


def test_non_final_report_denial_for_deleting_account_stops_session_and_writes():
    store.start_session(SID, None)
    store.record_event(SID, "before")

    async def go():
        c = B.BillingContext("u1", SID, 600, 0.0)
        B._post = lambda path, body: {"allowed": False, "reason": "account_unavailable"}
        _feed(c, 10.0)
        await asyncio.sleep(0.05)
        return c

    orig = B._post
    try:
        c = asyncio.run(go())
    finally:
        B._post = orig
    assert c.exhausted and c.deny_reason == "account_unavailable"
    assert B.close_params(c) == (4401, "account_unavailable")
    assert store.record_event(SID, "after") is None and store.get_history(SID) == []


def test_final_report_denial_also_blocks(monkeypatch):
    monkeypatch.setattr(B, "_post", lambda p, b: {"allowed": False, "reason": "account_unavailable"} if b["final"] else {"allowed": True, "remaining_seconds": 99})
    store.start_session(SID, None)

    async def go():
        c = B.BillingContext("u1", SID, 600, 0.0)
        _feed(c, 3.0)
        await c.finish()
        return c
    c = asyncio.run(go())
    assert store.is_blocked(SID) and c.deny_reason == "account_unavailable"


def test_mirror_detection_stops_the_audio_path_without_any_request(monkeypatch):
    """The mirror found the account gone on its own write: the next chunk is refused, no API call involved."""
    monkeypatch.setattr(B, "_post", lambda p, b: pytest.fail("no request expected"))
    c = B.BillingContext("u1", SID, 600, 0.0)
    assert _feed(c, 1.0) == 1.0 and not c.exhausted
    M.block_session(SID)
    assert _feed(c, 1.0) == 0.0
    assert c.exhausted and c.deny_reason == "account_unavailable"


def test_no_per_chunk_requests_when_healthy(monkeypatch):
    calls = []
    monkeypatch.setattr(B, "_post", lambda p, b: calls.append(b) or {"allowed": True, "remaining_seconds": 999})

    async def go():
        c = B.BillingContext("u1", SID, 9999, 0.0)
        for _ in range(100):           # 100 chunks of 0.1 s = 10 s of audio
            _feed(c, 0.1)
            await asyncio.sleep(0)
        await asyncio.sleep(0.05)
        return c
    c = asyncio.run(go())
    assert not c.exhausted
    assert len(calls) <= 2             # one report per 10 s of audio, never one per chunk


def test_unverifiable_midsession_fails_closed_after_grace(monkeypatch):
    monkeypatch.setattr(B, "_post", lambda p, b: (_ for _ in ()).throw(ConnectionError("api down")))
    monkeypatch.setattr(B, "UNVERIFIED_GRACE_SECONDS", 0.2)
    clock = {"t": 1000.0}
    monkeypatch.setattr(B, "_now", lambda: clock["t"])

    async def go():
        c = B.BillingContext("u1", SID, 9999, 0.0)
        _feed(c, 10.0)                  # first report is attempted and fails
        await asyncio.sleep(0.05)
        assert c._failing_since is not None and not c.exhausted
        clock["t"] += 0.1
        _feed(c, 1.0)
        assert not c.exhausted          # still inside the grace period: keep serving
        clock["t"] += 1.0
        _feed(c, 1.0)
        return c
    c = asyncio.run(go())
    assert c.exhausted and c.deny_reason == "billing_unavailable"
    assert B.close_params(c) == (4401, "billing_unavailable")


def test_recovery_inside_grace_resets_the_clock(monkeypatch):
    state = {"fail": True}

    def post(p, b):
        if state["fail"]:
            raise ConnectionError("blip")
        return {"allowed": True, "remaining_seconds": 999}

    monkeypatch.setattr(B, "_post", post)
    monkeypatch.setattr(B, "UNVERIFIED_GRACE_SECONDS", 5.0)
    clock = {"t": 0.0}
    monkeypatch.setattr(B, "_now", lambda: clock["t"])

    async def go():
        c = B.BillingContext("u1", SID, 9999, 0.0)
        _feed(c, 10.0)
        await asyncio.sleep(0.05)
        assert c._failing_since is not None
        state["fail"] = False
        clock["t"] += 3.0
        _feed(c, 1.0)
        await asyncio.sleep(0.05)       # the retry succeeds
        assert c._failing_since is None
        clock["t"] += 100.0             # long after: no failure outstanding, so nothing trips
        _feed(c, 1.0)
        return c
    c = asyncio.run(go())
    assert not c.exhausted


def test_close_params_mapping():
    c = B.BillingContext("u1", SID, 10, 0.0)
    assert B.close_params(c) == (4402, "out_of_minutes")
    c.deny_reason = "quota_exhausted"
    assert B.close_params(c) == (4402, "out_of_minutes")
    c.deny_reason = "invalid_token"
    assert B.close_params(c) == (4401, "invalid_token")


# ------------------------------------------------------- admission: new session and reconnect (parakeet_relay)

@pytest.fixture
def relay(monkeypatch):
    monkeypatch.setenv("STT_ENGINE", "eou120m")
    sys.path.insert(0, ".")
    try:
        return importlib.import_module("parakeet_relay")
    except Exception as e:
        pytest.skip(f"relay module not importable here: {e}")


class _P:
    session_id = SID
    access_code = None
    token = "tok"
    role = "speaker"


class _WS:
    def __init__(self):
        self.closed = None

    async def close(self, code=1000, reason=""):
        self.closed = (code, reason)


def _admit(relay, monkeypatch, verdict, ran):
    monkeypatch.setattr(relay.billing_mod, "enabled", lambda: True)

    async def auth(token, session_id):
        return verdict() if callable(verdict) else verdict

    async def fake_run(*a, **k):
        ran.append(k.get("billing"))

    monkeypatch.setattr(relay.billing_mod, "authorize_start", auth)
    monkeypatch.setattr(relay, "run_streaming_session", fake_run)
    monkeypatch.setattr(relay, "run_speaker_session", fake_run)
    ws = _WS()
    asyncio.run(relay._speaker_admitted(ws, _P))
    return ws


def test_tombstoned_account_rejected_before_session_creation(relay, monkeypatch):
    ran = []
    ws = _admit(relay, monkeypatch, {"allowed": False, "reason": "invalid_token"}, ran)
    assert ws.closed == (4401, "invalid_token") and ran == []
    assert store.get_session(SID) is None          # nothing was created


def test_tombstoned_account_rejected_on_reconnect(relay, monkeypatch):
    ran = []
    first = _admit(relay, monkeypatch, {"allowed": True, "user_id": "u1", "remaining_seconds": 60}, ran)
    assert first.closed is None and len(ran) == 1
    second = _admit(relay, monkeypatch, {"allowed": False, "reason": "invalid_token"}, ran)   # tombstone landed meanwhile
    assert second.closed == (4401, "invalid_token") and len(ran) == 1


def test_authorization_service_failure_fails_closed(relay, monkeypatch):
    ran = []

    def down(*a, **k):
        raise ConnectionError("api down")

    monkeypatch.setattr(B, "_post", down)
    monkeypatch.setattr(relay.billing_mod, "enabled", lambda: True)
    monkeypatch.setattr(relay, "run_streaming_session", lambda *a, **k: ran.append(1))
    monkeypatch.setattr(relay, "run_speaker_session", lambda *a, **k: ran.append(1))
    ws = _WS()
    asyncio.run(relay._speaker_admitted(ws, _P))
    assert ws.closed == (4401, "billing_unavailable") and ran == []


def test_allowed_verdict_without_user_id_fails_closed(relay, monkeypatch):
    ran = []
    ws = _admit(relay, monkeypatch, {"allowed": True, "remaining_seconds": 60}, ran)
    assert ws.closed == (4401, "billing_unavailable") and ran == []


def test_active_account_is_admitted_and_reconnects(relay, monkeypatch):
    ran = []
    ok = {"allowed": True, "user_id": "u1", "remaining_seconds": 60, "base_seconds": 0.0}
    assert _admit(relay, monkeypatch, ok, ran).closed is None
    assert _admit(relay, monkeypatch, dict(ok, base_seconds=12.0), ran).closed is None
    assert len(ran) == 2 and ran[1].audio_seconds == 12.0   # reconnect carries on from what was billed


# ---------------------------------- end to end: a connected session whose account is tombstoned stops writing

def _buf():
    return UtteranceBuffer(sample_rate=SR, bytes_per_sample=2, silence_rms_threshold=0.01, silence_hang_seconds=0.3,
                           min_utterance_seconds=0.2, max_utterance_seconds=8.0)


async def _speak(ws, words_pause=True):
    for _ in range(3):
        ws.feed(make_speech_chunk(amplitude=0.5, seconds=0.1))
        await asyncio.sleep(0.01)
    if words_pause:
        for _ in range(4):
            ws.feed(make_speech_chunk(amplitude=0.001, seconds=0.1))
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)


async def test_connected_session_tombstoned_midway_stops_further_writes(monkeypatch):
    mirrored = []
    monkeypatch.setattr(M, "_put", lambda op: mirrored.append(op))
    monkeypatch.setattr(B, "_post", lambda p, b: {"allowed": True, "remaining_seconds": 600})
    ws = FakeWebSocket()
    engine = FakeEngine(final_text="first utterance")
    ctx = B.BillingContext("u1", SID, 600, 0.0)
    task = asyncio.create_task(run_speaker_session(ws, SID, engine, _buf(), SessionRegistry(), billing=ctx))
    await asyncio.sleep(0.02)

    await _speak(ws)
    assert store.get_history(SID) == ["first utterance"]
    assert [op[0] for op in mirrored].count("event") == 1

    M.block_session(SID)            # what the mirror guard / a denied usage report does on seeing the tombstone
    engine._final_text = "after the tombstone"
    await _speak(ws)
    await asyncio.sleep(0.05)
    assert task.done() or ws.close_code is not None or ctx.exhausted
    assert store.get_history(SID) == []                      # nothing new stored locally ...
    assert [op[0] for op in mirrored].count("event") == 1    # ... and nothing new queued for Mongo
    if not task.done():
        ws.disconnect()
    await task
    assert ws.close_code == 4401 and ws.close_reason == "account_unavailable"
    assert [op[0] for op in mirrored].count("event") == 1


async def test_active_account_still_records_and_reconnects(monkeypatch):
    mirrored = []
    monkeypatch.setattr(M, "_put", lambda op: mirrored.append(op))
    registry = SessionRegistry()
    for i, text in enumerate(("one", "two")):         # second pass is a reconnect of the same session
        ws = FakeWebSocket()
        engine = FakeEngine(final_text=text)
        ctx = B.BillingContext("u1", SID, 600, 0.0)
        task = asyncio.create_task(run_speaker_session(ws, SID, engine, _buf(), registry, billing=ctx))
        await asyncio.sleep(0.02)
        await _speak(ws)
        ws.disconnect()
        await task
        assert ws.close_code is None
    assert store.get_history(SID) == ["one", "two"]
    assert [op[0] for op in mirrored].count("event") == 2


async def test_cleanup_after_tombstone_does_not_recreate_records(monkeypatch):
    """Disconnect/cleanup (end_session) after the account is blocked writes nothing local or remote."""
    mirrored = []
    monkeypatch.setattr(M, "_put", lambda op: mirrored.append(op))
    store.start_session(SID, None)
    store.block_session(SID)
    n = len(mirrored)
    store.end_session(SID)
    store.start_session(SID, None)
    assert store.get_session(SID) is None and len(mirrored) == n
