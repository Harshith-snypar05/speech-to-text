"""Tiny persistence layer for session transcripts -- SQLite, stdlib only.
Lets a viewer who joins mid-session see everything said so far (replayed
before live messages start arriving), and a viewer who opens the share
link after the session has ended still see the full transcript instead
of a dead connection.

Writes are one row per final utterance plus one row per session
start/end -- low enough volume that plain synchronous sqlite3 calls from
the async relay code are fine; not worth a thread pool for this.
"""
import os
import sqlite3
import time
from pathlib import Path

from . import mongo_mirror

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "transcripts.db"

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS sessions ("
    "session_id TEXT PRIMARY KEY, access_code TEXT, started_at REAL, ended_at REAL)",
    "CREATE TABLE IF NOT EXISTS transcript_events ("
    "session_id TEXT, seq INTEGER, text TEXT, created_at REAL)",
)


def _new_connection(path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    for statement in _SCHEMA:
        conn.execute(statement)
    conn.commit()
    return conn


def _default_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return _new_connection(DB_PATH)


_conn = _default_connection()


RESUME_WINDOW_S = float(os.environ.get("STT_RESUME_WINDOW_SECONDS", "300"))


def start_session(session_id: str, access_code: str | None) -> None:
    prev = _conn.execute("SELECT ended_at FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    # Same id seen again: a reconnect of the same speaker if the previous run is still open or ended
    # within RESUME_WINDOW_S -- keep its history (Phase 7E fix; before this every reconnect wiped it).
    resuming = prev is not None and (prev[0] is None or time.time() - prev[0] <= RESUME_WINDOW_S)
    _conn.execute(
        "INSERT INTO sessions (session_id, access_code, started_at, ended_at) VALUES (?, ?, ?, NULL) "
        "ON CONFLICT(session_id) DO UPDATE SET access_code = excluded.access_code, "
        "started_at = excluded.started_at, ended_at = NULL",
        (session_id, access_code, time.time()),
    )
    # An id reused after the resume window is a different run: start its history over.
    if not resuming:
        _conn.execute("DELETE FROM transcript_events WHERE session_id = ?", (session_id,))
    _conn.commit()
    mongo_mirror.start_session(session_id, access_code, reset=not resuming)


def end_session(session_id: str) -> None:
    _conn.execute("UPDATE sessions SET ended_at = ? WHERE session_id = ?", (time.time(), session_id))
    _conn.commit()
    mongo_mirror.end_session(session_id)


def record_event(session_id: str, text: str) -> int:
    row = _conn.execute(
        "SELECT COALESCE(MAX(seq), -1) FROM transcript_events WHERE session_id = ?", (session_id,)
    ).fetchone()
    next_seq = row[0] + 1
    _conn.execute(
        "INSERT INTO transcript_events (session_id, seq, text, created_at) VALUES (?, ?, ?, ?)",
        (session_id, next_seq, text, time.time()),
    )
    _conn.commit()
    mongo_mirror.record_event(session_id, next_seq, text)
    return next_seq


def update_event(session_id: str, seq: int, original: str, refined: str) -> bool:
    """Replace line `seq` with its refined text, only if it still holds `original` (a restarted session reuses seq numbers)."""
    cur = _conn.execute(
        "UPDATE transcript_events SET text = ? WHERE session_id = ? AND seq = ? AND text = ?", (refined, session_id, seq, original)
    )
    _conn.commit()
    if cur.rowcount != 1:
        return False
    mongo_mirror.refine_event(session_id, seq, original, refined)
    return True


def get_session(session_id: str) -> dict | None:
    row = _conn.execute(
        "SELECT access_code, started_at, ended_at FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is None:
        return None
    return {"access_code": row[0], "started_at": row[1], "ended_at": row[2]}


def get_history(session_id: str) -> list[str]:
    rows = _conn.execute(
        "SELECT text FROM transcript_events WHERE session_id = ? ORDER BY seq", (session_id,)
    ).fetchall()
    return [r[0] for r in rows]
