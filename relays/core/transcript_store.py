"""Tiny persistence layer for session transcripts -- SQLite, stdlib only.
Lets a viewer who joins mid-session see everything said so far (replayed
before live messages start arriving), and a viewer who opens the share
link after the session has ended still see the full transcript instead
of a dead connection.

Writes are one row per final utterance plus one row per session
start/end -- low enough volume that plain synchronous sqlite3 calls from
the async relay code are fine; not worth a thread pool for this.
"""
import sqlite3
import time
from pathlib import Path

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


def start_session(session_id: str, access_code: str | None) -> None:
    _conn.execute(
        "INSERT INTO sessions (session_id, access_code, started_at, ended_at) VALUES (?, ?, ?, NULL) "
        "ON CONFLICT(session_id) DO UPDATE SET access_code = excluded.access_code, "
        "started_at = excluded.started_at, ended_at = NULL",
        (session_id, access_code, time.time()),
    )
    # A reused session_id (same speaker resuming) starts its history over
    # rather than appending to whatever the previous run of this id said.
    _conn.execute("DELETE FROM transcript_events WHERE session_id = ?", (session_id,))
    _conn.commit()


def end_session(session_id: str) -> None:
    _conn.execute("UPDATE sessions SET ended_at = ? WHERE session_id = ?", (time.time(), session_id))
    _conn.commit()


def record_event(session_id: str, text: str) -> None:
    row = _conn.execute(
        "SELECT COALESCE(MAX(seq), -1) FROM transcript_events WHERE session_id = ?", (session_id,)
    ).fetchone()
    next_seq = row[0] + 1
    _conn.execute(
        "INSERT INTO transcript_events (session_id, seq, text, created_at) VALUES (?, ?, ?, ?)",
        (session_id, next_seq, text, time.time()),
    )
    _conn.commit()


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
