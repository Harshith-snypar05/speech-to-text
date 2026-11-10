"""Generic VAD-buffered speaker loop shared by all three relays. Only the
engine's transcribe_final/transcribe_partial differ between them -- this
owns the session orchestration: feeding audio into the VAD buffer,
triggering flushes, running the partial-preview cycle for engines that
support it, and guaranteeing the final utterance is never lost on
disconnect (awaited, not fire-and-forget).
"""
import asyncio
import json
import logging
import itertools
import time

import websockets

from . import flush_diagnostics as diag
from . import transcript_store
from .audio_processor import UtteranceBuffer
from .config import FINAL_FLUSH_TIMEOUT_SECONDS, PARTIAL_CYCLE_SECONDS, SESSION_MAX_DURATION_SECONDS
from .scheduler import FinalExpired, JobTicket
from .protocol import final_message, partial_message
from .session_manager import SessionRegistry
from engines.base_engine import TranscriptionEngine

logger = logging.getLogger(__name__)
_CONN_IDS = itertools.count(1)


def _ticket_fields(ticket) -> dict:
    """Scheduler timing for the flush diagnostic record (empty for engines without a scheduler)."""
    if ticket is None:
        return {}
    return {"sched_state": ticket.state, "queue_wait_s": _r(ticket.queue_wait_s), "infer_s": _r(ticket.infer_s),
            "sched_abandoned": ticket.abandoned}


def _r(x):
    return None if x is None else round(x, 4)


def _timeout_outcome(ticket) -> str:
    """Which kind of final timeout this was. Plain 'dropped_timeout' when there is no scheduler ticket."""
    if ticket is None:
        return "dropped_timeout"
    if ticket.state in ("expired_in_queue", "queued"):
        return "dropped_expired_in_queue"
    if ticket.state == "cancelled_before_dispatch":
        return "dropped_cancelled_before_dispatch"
    return "dropped_timeout_running"


async def run_speaker_session(
    websocket,
    session_id: str | None,
    engine: TranscriptionEngine,
    buffer: UtteranceBuffer,
    registry: SessionRegistry,
    access_code: str | None = None,
):
    words_sent = 0
    generation = 0  # bumped on every flush; lets a slow partial notice it's stale
    started_at = time.monotonic()
    # Diagnostic-only state (Phase 4). Never read by control flow.
    conn_id = next(_CONN_IDS)
    flush_seq = 0
    audio_bytes_received = 0
    scheduled = bool(getattr(engine, "supports_scheduling", False))

    async def send(payload: dict):
        try:
            await websocket.send(json.dumps(payload))
        except websockets.exceptions.ConnectionClosed:
            pass
        if session_id:
            await registry.broadcast(session_id, payload)

    async def partial_cycle():
        nonlocal words_sent
        if not engine.supports_partial:
            return
        while True:
            await asyncio.sleep(PARTIAL_CYCLE_SECONDS)
            if not buffer.has_pending_utterance():
                continue
            my_generation = generation
            try:
                if scheduled:
                    words = await engine.transcribe_partial(bytes(buffer.buffer), speaker_id=conn_id)
                else:
                    words = await engine.transcribe_partial(bytes(buffer.buffer))
            except Exception as e:
                logger.exception(f"partial transcription failed: {e}")
                continue
            if words is None:
                continue  # skipped by scheduler backpressure; the next cycle tries again
            if my_generation != generation:
                continue  # a flush happened while this was transcribing -- stale, drop it
            new_words = words[words_sent:]
            if new_words:
                words_sent = len(words)
                await send(partial_message(" ".join(new_words)))

    def _flush_reason() -> str:
        # Diagnostic classification only; mirrors UtteranceBuffer.add_chunk.
        if buffer.silence_s >= buffer.silence_hang_seconds and buffer.speech_s >= buffer.min_utterance_seconds:
            return "silence_hang"
        return "forced_cap"

    def _finish(rec, outcome, **kw):
        diag.flush_finish(rec, outcome, **kw)

    async def flush(reason: str = "disconnect"):
        # Awaited everywhere it's called (including from the disconnect
        # path) so the last utterance of a session is never dropped by a
        # fire-and-forget task that outlives the connection teardown.
        nonlocal words_sent, generation, flush_seq
        generation += 1
        words_sent = 0
        flush_seq += 1
        pending = buffer.has_pending_utterance()
        rec = diag.flush_start(conn_id, session_id, flush_seq, reason, audio_bytes_received,
                               buffer, buffer.sample_rate, buffer.bytes_per_sample, pending)
        if not pending:
            buffer.take()
            _finish(rec, "dropped_not_pending", early_return="not_pending")
            return
        snapshot = buffer.take()
        t_decode = time.monotonic()
        if rec is not None:
            rec["decode_attempted"] = True
        ticket = None
        if scheduled:
            # Deadline is anchored at the original flush request: queue wait counts against it.
            ticket = JobTicket("final", conn_id)
            call = engine.transcribe_final(snapshot, speaker_id=conn_id,
                                           deadline=t_decode + FINAL_FLUSH_TIMEOUT_SECONDS, ticket=ticket)
        else:
            call = engine.transcribe_final(snapshot)
        try:
            text = await asyncio.wait_for(call, timeout=FINAL_FLUSH_TIMEOUT_SECONDS)
        except FinalExpired:
            logger.error("final expired in queue before dispatch; utterance dropped (never decoded)")
            _finish(rec, "dropped_expired_in_queue", early_return="expired_in_queue",
                              decode_s=round(time.monotonic() - t_decode, 4), **_ticket_fields(ticket))
            return
        except asyncio.TimeoutError:
            outcome = _timeout_outcome(ticket)
            logger.error(f"final transcription timed out ({outcome}); utterance dropped")
            _finish(rec, outcome, early_return="timeout",
                              decode_s=round(time.monotonic() - t_decode, 4), exception="TimeoutError",
                              **_ticket_fields(ticket))
            return
        except asyncio.CancelledError:
            _finish(rec, "dropped_cancelled_before_dispatch" if ticket is not None
                              and ticket.state in ("cancelled_before_dispatch", "expired_in_queue", "queued")
                              else "dropped_cancelled",
                              early_return="cancelled", decode_s=round(time.monotonic() - t_decode, 4),
                              **_ticket_fields(ticket))
            raise
        except Exception as e:
            logger.exception(f"final transcription failed: {e}")
            _finish(rec, "dropped_exception", early_return="exception",
                              decode_s=round(time.monotonic() - t_decode, 4), exception=repr(e),
                              **_ticket_fields(ticket))
            return
        decode_s = round(time.monotonic() - t_decode, 4)
        if rec is not None:
            rec.update(_ticket_fields(ticket))
        if text:
            if session_id:
                transcript_store.record_event(session_id, text)
            msg = final_message(text)
            if rec is not None:
                rec.update(decode_s=decode_s, text_empty=False, text_len=len(text),
                           text_words=len(text.split()), final_constructed=True, final_send_called=True)
            t_send = time.monotonic()
            try:
                await send(msg)
            except BaseException as e:
                _finish(rec, "dropped_send_exception", early_return="send_exception",
                                  send_s=round(time.monotonic() - t_send, 4), exception=repr(e))
                raise
            _finish(rec, "final_sent", send_s=round(time.monotonic() - t_send, 4))
        else:
            _finish(rec, "dropped_empty_text", early_return="empty_text", decode_s=decode_s,
                              text_empty=True, text_len=len(text) if text is not None else None,
                              text_words=0)

    partial_task = asyncio.create_task(partial_cycle())
    registry.speaker_connected(session_id, access_code)
    logger.info(f"Speaker connected (session={session_id})")
    try:
        async for message in websocket:
            if not isinstance(message, (bytes, bytearray)):
                continue
            if time.monotonic() - started_at > SESSION_MAX_DURATION_SECONDS:
                logger.info(f"Session {session_id} hit the max duration cap; ending it")
                await websocket.close(code=1000, reason="session time limit reached")
                break
            try:
                boundary = buffer.add_chunk(message)
            except Exception as e:
                # A malformed/corrupt audio frame (e.g. odd byte length
                # that doesn't divide evenly into 16-bit samples) must not
                # take the whole connection down -- drop the frame and
                # keep the session alive.
                logger.warning(f"dropped malformed audio frame: {e}")
                continue
            audio_bytes_received += len(message)
            if boundary:
                await flush(_flush_reason())
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        partial_task.cancel()
        try:
            await partial_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(f"partial task cleanup failed: {e}")
        try:
            await flush("disconnect")
        except Exception as e:
            logger.exception(f"final flush on disconnect failed: {e}")
        await registry.speaker_disconnected(session_id)
        logger.info(f"Speaker disconnected (session={session_id})")
