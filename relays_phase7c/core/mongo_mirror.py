"""Optional MongoDB mirror of session transcripts (staging). Enabled only when MONGODB_URI is set.

SQLite (core/transcript_store.py) stays the source for live viewer replay. Every session start/end and final utterance is
also queued here and written by one background thread, so a slow or unreachable cluster can never delay audio or text.
The URI (it holds the password) is read from the environment only and is never logged. Only what transcript_store already
keeps is mirrored: session id, access code, timestamps, final utterance text. No audio.

Deletion barrier (when the relay runs against the ScriptLiv API, i.e. `billing.enabled()`): the API creates every
`sessions` row (with `owner_id`) when it authorizes the speaker, so the relay never creates one. Before each write it
reads that row and the owner's user document and refuses the write unless the owner exists and is not being deleted
(`deleting`). Event writes are check -> write -> re-check: if the account was tombstoned or the session removed while the
write was in flight, the write is undone. Together with the API cascade (which runs only after the tombstone) this leaves no
window in which an account's relay record can outlive its deletion, apart from a database failure between write and
re-check (logged at ERROR). The check runs on this background thread, per final utterance, never per audio chunk, and any
database error drops the write (fail closed). Without the API (staging without accounts) the old behaviour is kept.
"""
import logging
import os
import queue
import threading
import time

logger = logging.getLogger(__name__)

DB_NAME = os.environ.get("MONGODB_DB", "scriptliv")
_q: "queue.Queue[tuple]" = queue.Queue(maxsize=10000)
_started = False
_lock = threading.Lock()
_blocked: "dict[str, float]" = {}      # session_id -> when it was refused; bounded, see block_session
_BLOCKED_MAX = 5000


def enabled() -> bool:
    return bool(os.environ.get("MONGODB_URI"))


def owned_mode() -> bool:
    """True when sessions belong to ScriptLiv accounts (the relay is wired to the API)."""
    from . import billing
    return billing.enabled()


def block_session(session_id: str) -> None:
    """Refuse every further mirror write for this session. Called when the account is found to be deleting/deleted; the set
    only ever holds sessions of such accounts, is bounded, and drops its oldest entries first."""
    if not session_id:
        return
    _blocked[session_id] = time.time()
    while len(_blocked) > _BLOCKED_MAX:
        _blocked.pop(next(iter(_blocked)), None)


def is_blocked(session_id) -> bool:
    return session_id in _blocked


def _owner_available(db, sid) -> bool:
    """The session row exists, has an owner, and that owner exists and is not being deleted. Raises on database errors:
    the caller treats an error as a refusal (fail closed)."""
    row = db.sessions.find_one({"session_id": sid}, {"owner_id": 1})
    owner = row.get("owner_id") if row else None
    if not owner:
        return False
    from bson import ObjectId
    try:
        oid = ObjectId(owner)
    except Exception:
        return False
    user = db.users.find_one({"_id": oid}, {"deleting": 1})
    return user is not None and not user.get("deleting")


def _apply(db, op) -> None:
    """Perform one queued write against `db`. Separate from the thread so it can be tested without a cluster."""
    kind, sid = op[0], op[1]
    owned = owned_mode()
    if owned:
        if sid in _blocked:
            return
        if not _owner_available(db, sid):
            block_session(sid)
            logger.warning("MongoDB mirror: refused %s for %s (account unavailable)", kind, sid)
            return
    if kind == "start":
        _, sid, code, ts, reset = op
        if reset:
            db.transcript_events.delete_many({"session_id": sid})
        if owned:   # the API created the row; never create one here
            db.sessions.update_one({"session_id": sid}, {"$set": {"access_code": code, "started_at": ts, "ended_at": None}})
        else:
            db.sessions.update_one({"session_id": sid}, {"$set": {"access_code": code, "started_at": ts, "ended_at": None}}, upsert=True)
    elif kind == "end":
        _, sid, ts = op
        db.sessions.update_one({"session_id": sid}, {"$set": {"ended_at": ts}})
    elif kind == "refine":
        _, sid, seq, original, refined = op
        db.transcript_events.update_one({"session_id": sid, "seq": seq, "text": original}, {"$set": {"text": refined}})
    elif kind == "event":
        _, sid, seq, text, ts = op
        db.transcript_events.update_one({"session_id": sid, "seq": seq}, {"$set": {"text": text, "created_at": ts}}, upsert=True)
        if owned and not _owner_available(db, sid):
            # the account was tombstoned (or the session removed) while this write was in flight: undo it. The cascade
            # either already ran past this stage (so it will not see the row) or has not started (it will).
            db.transcript_events.delete_one({"session_id": sid, "seq": seq})
            block_session(sid)
            logger.warning("MongoDB mirror: undid event %s/%s written during account deletion", sid, seq)


def _step(state: dict, op) -> None:
    """Handle one queued op. Never raises: on any error the op is dropped (fail closed) and the connection is rebuilt."""
    try:
        if state.get("client") is None:
            from pymongo import MongoClient

            client = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=8000, appName="scriptliv-staging")
            db = client[DB_NAME]
            db.sessions.create_index("session_id", unique=True)
            db.transcript_events.create_index([("session_id", 1), ("seq", 1)], unique=True)
            state["client"] = client
            logger.info("MongoDB mirror connected (db=%s)", DB_NAME)
        _apply(state["client"][DB_NAME], op)
    except Exception as e:
        logger.warning("MongoDB mirror write failed (dropped): %s", type(e).__name__)
        state["client"] = None
        time.sleep(2)


def _worker():
    state: dict = {}
    while True:
        _step(state, _q.get())


def _put(op):
    global _started
    if not enabled():
        return
    with _lock:
        if not _started:
            threading.Thread(target=_worker, name="mongo-mirror", daemon=True).start()
            _started = True
    try:
        _q.put_nowait(op)
    except queue.Full:
        logger.warning("MongoDB mirror queue full; dropping write")


def start_session(session_id, access_code, reset):
    _put(("start", session_id, access_code, time.time(), reset))


def end_session(session_id):
    _put(("end", session_id, time.time()))


def record_event(session_id, seq, text):
    _put(("event", session_id, seq, text, time.time()))


def refine_event(session_id, seq, original, refined):
    _put(("refine", session_id, seq, original, refined))
