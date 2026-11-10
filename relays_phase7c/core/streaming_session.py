"""Speaker loop for true streaming engines (engines/streaming_worker_engine.py).

Audio goes to the worker the moment it arrives; there is no utterance buffer and no periodic re-decode. The worker's
partial text for the current utterance only grows, so each partial message carries just the new words (same wire format
as the buffered path: partial = words to append, final = the whole utterance). A final is produced when the model emits
its own end-of-utterance token (EOU model) or, for models without one, when the speaker has been silent for
STT_STREAM_ENDPOINT_SECONDS after speech. Session/broadcast behaviour matches core/speaker_session.py.

With billing enabled the account's allowance is a hard ceiling: each chunk is checked BEFORE it reaches the engine, the chunk
that crosses the ceiling is cut at the exact sample, and the connection is closed with code 4402 (out_of_minutes).
"""
import asyncio
import json
import logging
import os
import time

import numpy as np
import websockets

from . import transcript_store
from .config import SESSION_MAX_DURATION_SECONDS, SILENCE_RMS_THRESHOLD, SAMPLE_RATE
from .protocol import final_message, partial_message, refine_message
from .session_manager import SessionRegistry

logger = logging.getLogger(__name__)

ENDPOINT_SECONDS = float(os.environ.get("STT_STREAM_ENDPOINT_SECONDS", "0.5"))
# The last word of a partial may still be a sub-word fragment ("sess" -> "session"). It is held until it is followed by
# another word or has been stable this long; deltas are append-only so a sent fragment could never be corrected.
TAIL_HOLD_SECONDS = float(os.environ.get("STT_STREAM_TAIL_HOLD_SECONDS", "0.25"))
MAX_UTTERANCE_SECONDS = float(os.environ.get("STT_STREAM_MAX_UTTERANCE_SECONDS", "25"))
FLUSH_WAIT_SECONDS = 3.0
# audio kept for the optional second-pass refinement (core/refiner.py); older audio is dropped so silence cannot grow it
UTT_BUFFER_MAX_BYTES = int((MAX_UTTERANCE_SECONDS + 5) * SAMPLE_RATE * 2)


OUT_OF_MINUTES = "out_of_minutes"
ASR_LOST = "asr_connection_lost"
ASR_LOST_MESSAGE = "The transcription engine connection was interrupted. Your audio was not lost beyond this point; reconnect to continue."
OUT_OF_MINUTES_MESSAGE = "You have used all your available transcription minutes. Add minutes or upgrade your plan to continue."


async def run_streaming_session(websocket, session_id, engine, registry: SessionRegistry, access_code=None, billing=None, refiner=None):
    started = time.monotonic()
    words_sent = 0
    seq = 0
    silence_s = 0.0
    speech_s = 0.0
    utt_s = 0.0
    flush_sent = False
    stream = None
    tail_task = None
    latest_words = []
    utt_pcm = bytearray()
    limit_hit = False
    asr_lost = False

    async def send(payload: dict):
        try:
            await websocket.send(json.dumps(payload))
        except websockets.exceptions.ConnectionClosed:
            pass
        if session_id:
            await registry.broadcast(session_id, payload)

    async def send_out_of_minutes():
        try:
            await websocket.send(json.dumps({"type": "error", "code": OUT_OF_MINUTES, "message": OUT_OF_MINUTES_MESSAGE}))
        except websockets.exceptions.ConnectionClosed:
            pass

    async def emit(upto):
        nonlocal words_sent
        new = latest_words[words_sent:upto]
        if new:
            words_sent = upto
            await send(partial_message(" ".join(new)))

    async def release_tail(expected):
        await asyncio.sleep(TAIL_HOLD_SECONDS)
        if latest_words == expected:
            await emit(len(latest_words))

    def make_refined_handler(store_seq, original):
        async def apply(refined):
            if transcript_store.update_event(session_id, store_seq, original, refined):
                await send(refine_message(store_seq, original, refined))
        return apply

    async def reader():
        nonlocal words_sent, seq, flush_sent, silence_s, speech_s, utt_s, tail_task, latest_words, utt_pcm
        async for ev in stream.events():
            kind = ev.get("type")
            if kind == "partial":
                latest_words = (ev.get("text") or "").split()
                if tail_task:
                    tail_task.cancel()
                await emit(len(latest_words) - 1)
                if len(latest_words) > words_sent:
                    tail_task = asyncio.create_task(release_tail(list(latest_words)))
            elif kind == "final":
                if tail_task:
                    tail_task.cancel()
                latest_words = []
                text = (ev.get("text") or "").strip()
                words_sent = 0
                flush_sent = False
                silence_s = speech_s = utt_s = 0.0
                pcm, utt_pcm = bytes(utt_pcm), bytearray()
                if text:
                    seq += 1
                    store_seq = None
                    if session_id:
                        store_seq = transcript_store.record_event(session_id, text)
                    await send(final_message(text))
                    if refiner is not None and store_seq is not None:
                        refiner.submit(pcm, text, make_refined_handler(store_seq, text))
            elif kind == "error":
                logger.error("ASR worker error: %s", ev.get("detail"))

    try:
        stream = await engine.open_stream()
    except Exception as e:
        logger.exception("could not open ASR worker stream: %s", e)
        await websocket.close(code=1013, reason="asr worker unavailable")
        return

    read_task = asyncio.create_task(reader())
    registry.speaker_connected(session_id, access_code)
    logger.info("Streaming speaker connected (session=%s, model=%s)", session_id, engine.model_key)
    try:
        async for message in websocket:
            if not isinstance(message, (bytes, bytearray)):
                continue
            if time.monotonic() - started > SESSION_MAX_DURATION_SECONDS:
                await websocket.close(code=1000, reason="session time limit reached")
                break
            if len(message) % 2:
                logger.warning("dropped malformed audio frame (odd length)")
                continue
            chunk = bytes(message)
            if billing is not None:
                n = len(chunk) // 2
                fit = billing.take(n, SAMPLE_RATE)   # strict ceiling: decided before the engine sees any audio
                chunk = chunk[: fit * 2]
            if read_task.done() and not limit_hit:
                asr_lost = True   # the worker side of the stream ended on its own: do not keep accepting (and billing) audio
                break
            if chunk:
                try:
                    await stream.send_audio(chunk)
                except websockets.exceptions.ConnectionClosed:
                    asr_lost = True   # the ENGINE socket closed, not the speaker's: never let this look like a normal end
                    break
                if refiner is not None:
                    utt_pcm.extend(chunk)
                    if len(utt_pcm) > UTT_BUFFER_MAX_BYTES:
                        del utt_pcm[: len(utt_pcm) - UTT_BUFFER_MAX_BYTES]
            # endpoint on silence for every engine: the EOU model does not always emit <EOU> (long pauses, noisy mics);
            # when it does, its own final arrives first and resets these counters.
            samples = np.frombuffer(chunk, dtype=np.int16)
            if len(samples):
                chunk_s = len(samples) / SAMPLE_RATE
                rms = float(np.sqrt(np.mean((samples.astype(np.float32) / 32768.0) ** 2)))
                utt_s += chunk_s
                if rms < SILENCE_RMS_THRESHOLD:
                    silence_s += chunk_s
                else:
                    silence_s = 0.0
                    speech_s += chunk_s
                if not flush_sent and ((silence_s >= ENDPOINT_SECONDS and speech_s >= 0.2) or utt_s >= MAX_UTTERANCE_SECONDS):
                    flush_sent = True
                    await stream.flush()
            if billing is not None and billing.exhausted:
                limit_hit = True   # tell the user NOW; the close follows once the already-allowed audio has been finalized
                await send_out_of_minutes()
                break
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        try:
            await stream.flush()
            await asyncio.wait_for(asyncio.shield(read_task), timeout=FLUSH_WAIT_SECONDS)
        except Exception:
            pass
        await stream.close()
        read_task.cancel()
        try:
            await read_task
        except BaseException:
            pass
        if limit_hit:
            try:
                await websocket.close(code=4402, reason=OUT_OF_MINUTES)
            except Exception:
                pass
        elif asr_lost:
            logger.error("ASR worker connection lost (session=%s)", session_id)
            try:
                await websocket.send(json.dumps({"type": "error", "code": ASR_LOST, "message": ASR_LOST_MESSAGE}))
                await websocket.close(code=1011, reason=ASR_LOST)
            except Exception:
                pass
        if billing is not None:
            await billing.finish()
        await registry.speaker_disconnected(session_id)
        logger.info("Streaming speaker disconnected (session=%s)", session_id)
