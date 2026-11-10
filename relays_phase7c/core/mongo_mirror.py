"""Optional MongoDB mirror of session transcripts (staging). Enabled only when MONGODB_URI is set.

SQLite (core/transcript_store.py) stays the source for live viewer replay. Every session start/end and final utterance is
also queued here and written by one background thread, so a slow or unreachable cluster can never delay audio or text.
The URI (it holds the password) is read from the environment only and is never logged. Only what transcript_store already
keeps is mirrored: session id, access code, timestamps, final utterance text. No audio.
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


def enabled() -> bool:
    return bool(os.environ.get("MONGODB_URI"))


def _worker():
    client = None
    while True:
        op = _q.get()
        try:
            if client is None:
                from pymongo import MongoClient

                client = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=8000, appName="scriptliv-staging")
                db = client[DB_NAME]
                db.sessions.create_index("session_id", unique=True)
                db.transcript_events.create_index([("session_id", 1), ("seq", 1)], unique=True)
                logger.info("MongoDB mirror connected (db=%s)", DB_NAME)
            db = client[DB_NAME]
            kind = op[0]
            if kind == "start":
                _, sid, code, ts, reset = op
                if reset:
                    db.transcript_events.delete_many({"session_id": sid})
                db.sessions.update_one(
                    {"session_id": sid}, {"$set": {"access_code": code, "started_at": ts, "ended_at": None}}, upsert=True
                )
            elif kind == "end":
                _, sid, ts = op
                db.sessions.update_one({"session_id": sid}, {"$set": {"ended_at": ts}})
            elif kind == "refine":
                _, sid, seq, original, refined = op
                db.transcript_events.update_one({"session_id": sid, "seq": seq, "text": original}, {"$set": {"text": refined}})
            elif kind == "event":
                _, sid, seq, text, ts = op
                db.transcript_events.update_one(
                    {"session_id": sid, "seq": seq}, {"$set": {"text": text, "created_at": ts}}, upsert=True
                )
        except Exception as e:  # never raise into the relay; drop this write and retry connecting next time
            logger.warning("MongoDB mirror write failed: %s", type(e).__name__)
            client = None
            time.sleep(2)


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
