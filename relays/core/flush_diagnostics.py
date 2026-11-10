"""Diagnostic-only flush logging (Phase 4). OFF unless STT_FLUSH_DIAG_FILE is set.

Writes one JSON object per line describing what the finalization path did
for each flush, so a missing final can be traced to a specific cause. It
never changes control flow: every function swallows its own errors and
returns None / does nothing when disabled. Transcript text is NOT logged,
only its length and word count.

Correlation: every record carries conn_id (one per speaker connection),
seq (flush number within that connection) and audio_received_s (audio
position at the moment of the flush, i.e. the same clock as the benchmark's
expected_detail / final_times_s). session_id is None for benchmark runs.
"""
import json
import os
import time

ENV_VAR = "STT_FLUSH_DIAG_FILE"

OUTCOMES = (
    "final_sent",            # text non-empty, final message constructed and send() awaited
    "dropped_not_pending",   # has_pending_utterance() False -> audio discarded by buffer.take(), no decode
    "dropped_timeout",       # transcribe_final exceeded FINAL_FLUSH_TIMEOUT_SECONDS
    "dropped_exception",     # transcribe_final raised
    "dropped_empty_text",    # decode returned empty text -> no final constructed
    "dropped_send_exception",  # final constructed, send() raised (re-raised unchanged)
)


def _path():
    return os.environ.get(ENV_VAR) or None


def enabled() -> bool:
    return _path() is not None


def emit(record: dict) -> None:
    p = _path()
    if not p:
        return
    try:
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # diagnostics must never affect the relay


def event(conn_id, session_id, kind: str, **fields) -> None:
    if not enabled():
        return
    emit({"kind": kind, "ts_wall": time.time(), "ts_mono": time.monotonic(),
          "conn_id": conn_id, "session_id": session_id, **fields})


def flush_start(conn_id, session_id, seq, reason, audio_received_bytes, buffer,
                sample_rate, bytes_per_sample, has_pending):
    """Returns a record dict (to pass to flush_finish) or None when disabled."""
    if not enabled():
        return None
    try:
        nbytes = len(buffer.buffer)
        samples = nbytes // bytes_per_sample
        return {
            "kind": "flush", "ts_wall": time.time(), "ts_mono": time.monotonic(),
            "conn_id": conn_id, "session_id": session_id, "seq": seq, "reason": reason,
            "audio_received_s": round(audio_received_bytes / (sample_rate * bytes_per_sample), 3),
            "buffer_bytes": nbytes, "buffer_samples": samples,
            "buffer_s": round(samples / sample_rate, 3),
            "speech_s": round(float(buffer.speech_s), 3), "silence_s": round(float(buffer.silence_s), 3),
            "min_utterance_s": buffer.min_utterance_seconds, "max_utterance_s": buffer.max_utterance_seconds,
            "hang_s": buffer.silence_hang_seconds,
            "has_pending": bool(has_pending),
            "decode_attempted": False, "decode_s": None, "exception": None,
            "text_empty": None, "text_len": None, "text_words": None,
            "final_constructed": False, "final_send_called": False, "send_s": None,
            "outcome": None,
        }
    except Exception:
        return None


def flush_finish(rec, outcome: str, **fields) -> None:
    if rec is None:
        return
    try:
        rec.update(fields)
        rec["outcome"] = outcome
        rec["total_s"] = round(time.monotonic() - rec["ts_mono"], 4)
        emit(rec)
    except Exception:
        pass
