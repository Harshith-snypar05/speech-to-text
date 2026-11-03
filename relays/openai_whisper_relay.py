"""Low-latency live-transcription relay for the plain openai/whisper package.

openai/whisper has no streaming API at all (batch-only, transcribe() runs on
a full array). Rather than re-decoding a fixed window on a fixed timer (which
wastes time on silence and makes every result wait for the next tick), this
relay watches incoming audio energy and transcribes the instant you pause --
same mechanism as WhisperLiveKit's VAD-triggered segmentation, so results
fire as soon as a sentence ends instead of up to CYCLE_SECONDS later.

Also acts as a thin session broadcaster: a speaker connects with
?role=speaker&session=<token>, a viewer connects with
?role=viewer&session=<token> and receives the same transcript messages
read-only, with no mic/audio of its own. The session dies the moment the
speaker disconnects.
"""
import asyncio
import json
import logging
import re
from urllib.parse import parse_qs, urlsplit

import numpy as np
import websockets
import whisper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("openai_whisper_relay")

SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2
LISTEN_PORT = 8766

SILENCE_RMS_THRESHOLD = 0.01   # below this = "silence" (matches compare.html's mic-level indicator)
SILENCE_HANG_SECONDS = 0.6     # pause length that triggers a flush
MIN_UTTERANCE_SECONDS = 0.3    # ignore blips shorter than this
MAX_UTTERANCE_SECONDS = 8.0    # force-flush long continuous speech/noise even without a pause --
                                # kept short because a long ambiguous chunk is exactly what sends
                                # Whisper into a repetition loop ("no, no, no, no...")

logger.info("Loading openai/whisper base.en model...")
model = whisper.load_model("base.en")
logger.info("Model loaded.")

# session_id -> set of viewer websockets currently watching that speaker
sessions: dict[str, set] = {}
# session_ids with a currently-connected speaker -- lets viewer cleanup tell
# "no speaker ever showed up for this id" (safe to drop) apart from
# "speaker is live with zero viewers right now" (must not drop).
active_speakers: set[str] = set()


def pcm_bytes_to_float32(pcm_bytes: bytes) -> np.ndarray:
    return np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0


# Collapses degenerate repetition Whisper sometimes produces on long/ambiguous
# audio (e.g. "no, no, no, no..." or "a little bit of a little bit of...").
# Catches runs of an n-word phrase repeated 3+ times in a row. Smallest unit
# size first and to a fixpoint, so "no, no, no" (1-word unit) fully collapses
# before a larger unit like "no, no" gets a chance to lock in and only
# partially collapse it.
_REPEAT_RES = [
    re.compile(r'\b(' + r'\w+' + (r'[\s,]+\w+' * (n - 1)) + r')\b(?:[\s,]+\1\b){2,}', re.IGNORECASE)
    for n in (1, 2, 3, 4)
]


def collapse_repetition(text: str) -> str:
    for pattern in _REPEAT_RES:
        prev = None
        while prev != text:
            prev = text
            text = pattern.sub(r'\1', text)
    return text


async def transcribe_window(pcm_bytes: bytes) -> str:
    audio = pcm_bytes_to_float32(pcm_bytes)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        # No fixed temperature: let Whisper fall back to higher temperatures
        # when the greedy decode looks degenerate (high compression ratio /
        # low confidence) -- that fallback IS the anti-repetition-loop
        # mechanism built into the library. Pinning temperature=0.0 disables
        # it entirely, which is what caused the repetition spam.
        lambda: model.transcribe(audio, language="en", fp16=False),
    )
    return collapse_repetition(result.get("text", "").strip())


def parse_connection_params(websocket) -> tuple[str, str | None]:
    query = urlsplit(websocket.request.path).query
    params = parse_qs(query)
    role = (params.get("role", ["speaker"])[0]).strip().lower()
    session_id = (params.get("session", [None])[0])
    return role, session_id


async def broadcast(session_id: str, payload: dict):
    viewers = sessions.get(session_id)
    if not viewers:
        return
    dead = []
    message = json.dumps(payload)
    for viewer in viewers:
        try:
            await viewer.send(message)
        except Exception:
            dead.append(viewer)
    for viewer in dead:
        viewers.discard(viewer)


async def handle_viewer(websocket, session_id: str):
    if not session_id:
        await websocket.close(code=4400, reason="missing session id")
        return
    viewers = sessions.setdefault(session_id, set())
    viewers.add(websocket)
    logger.info(f"Viewer joined session {session_id}")
    try:
        async for _ in websocket:
            pass  # viewers don't send anything; just hold the connection open
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        viewers.discard(websocket)
        if not viewers and session_id not in active_speakers:
            sessions.pop(session_id, None)
        logger.info(f"Viewer left session {session_id}")


async def handle_speaker(websocket, session_id: str | None):
    buffer = bytearray()
    silence_s = 0.0
    speech_s = 0.0

    async def transcribe_and_send(pcm_bytes):
        try:
            text = await transcribe_window(pcm_bytes)
        except Exception as e:
            logger.exception(f"transcription failed: {e}")
            return
        if text:
            payload = {"text": text}
            try:
                await websocket.send(json.dumps(payload))
            except websockets.exceptions.ConnectionClosed:
                pass
            if session_id:
                await broadcast(session_id, payload)

    async def flush():
        # Awaited everywhere it's called (including from the disconnect
        # path) so the last utterance of a session is never dropped by a
        # fire-and-forget task that outlives the connection teardown.
        nonlocal buffer, silence_s, speech_s
        if buffer and speech_s >= MIN_UTTERANCE_SECONDS:
            snapshot = bytes(buffer)
            buffer = bytearray()
            silence_s = 0.0
            speech_s = 0.0
            try:
                await asyncio.wait_for(transcribe_and_send(snapshot), timeout=10.0)
            except asyncio.TimeoutError:
                logger.error("final transcription timed out; utterance dropped")
            except Exception as e:
                logger.exception(f"flush failed: {e}")
        else:
            buffer = bytearray()
            silence_s = 0.0
            speech_s = 0.0

    if session_id:
        active_speakers.add(session_id)
    logger.info(f"Speaker connected (session={session_id})")
    try:
        async for message in websocket:
            if not isinstance(message, (bytes, bytearray)):
                continue
            samples = pcm_bytes_to_float32(message)
            if len(samples) == 0:
                continue
            chunk_s = len(samples) / SAMPLE_RATE
            rms = float(np.sqrt(np.mean(samples ** 2)))
            buffer.extend(message)
            if rms < SILENCE_RMS_THRESHOLD:
                silence_s += chunk_s
            else:
                silence_s = 0.0
                speech_s += chunk_s
            total_s = len(buffer) / (SAMPLE_RATE * BYTES_PER_SAMPLE)
            if (silence_s >= SILENCE_HANG_SECONDS and speech_s >= MIN_UTTERANCE_SECONDS) or total_s >= MAX_UTTERANCE_SECONDS:
                await flush()
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        try:
            await flush()
        except Exception as e:
            logger.exception(f"final flush on disconnect failed: {e}")
        if session_id:
            active_speakers.discard(session_id)
            await broadcast(session_id, {"type": "ended"})
            # list(...) snapshots the set -- closing each viewer triggers
            # their own handler's finally block, which discards them from
            # this same set concurrently; iterating the live set directly
            # raises "Set changed size during iteration".
            for viewer in list(sessions.pop(session_id, ())):
                try:
                    await viewer.close(code=1000, reason="session ended")
                except Exception:
                    pass
        logger.info(f"Speaker disconnected (session={session_id})")


async def handle(websocket):
    role, session_id = parse_connection_params(websocket)
    if role == "viewer":
        await handle_viewer(websocket, session_id)
    else:
        await handle_speaker(websocket, session_id)


async def main():
    async with websockets.serve(handle, "localhost", LISTEN_PORT, max_size=None):
        logger.info(f"openai/whisper relay listening on ws://localhost:{LISTEN_PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
