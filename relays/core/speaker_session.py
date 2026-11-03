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
import time

import websockets

from .audio_processor import UtteranceBuffer
from .config import FINAL_FLUSH_TIMEOUT_SECONDS, PARTIAL_CYCLE_SECONDS, SESSION_MAX_DURATION_SECONDS
from .protocol import final_message, partial_message
from .session_manager import SessionRegistry
from engines.base_engine import TranscriptionEngine

logger = logging.getLogger(__name__)


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
                words = await engine.transcribe_partial(bytes(buffer.buffer))
            except Exception as e:
                logger.exception(f"partial transcription failed: {e}")
                continue
            if my_generation != generation:
                continue  # a flush happened while this was transcribing -- stale, drop it
            new_words = words[words_sent:]
            if new_words:
                words_sent = len(words)
                await send(partial_message(" ".join(new_words)))

    async def flush():
        # Awaited everywhere it's called (including from the disconnect
        # path) so the last utterance of a session is never dropped by a
        # fire-and-forget task that outlives the connection teardown.
        nonlocal words_sent, generation
        generation += 1
        words_sent = 0
        if not buffer.has_pending_utterance():
            buffer.take()
            return
        snapshot = buffer.take()
        try:
            text = await asyncio.wait_for(engine.transcribe_final(snapshot), timeout=FINAL_FLUSH_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.error("final transcription timed out; utterance dropped")
            return
        except Exception as e:
            logger.exception(f"final transcription failed: {e}")
            return
        if text:
            await send(final_message(text))

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
            if boundary:
                await flush()
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
            await flush()
        except Exception as e:
            logger.exception(f"final flush on disconnect failed: {e}")
        await registry.speaker_disconnected(session_id)
        logger.info(f"Speaker disconnected (session={session_id})")
