"""Word-by-word live-transcription relay using faster-whisper (CTranslate2).

Same VAD-pause-triggered final commit as the other two relays (clean
sentence, no duplication), but also runs a fast partial-preview cycle every
PARTIAL_CYCLE_SECONDS: re-transcribes the in-progress utterance with
word-level timestamps and sends only the *new* words since the last cycle
(diffed by word count), so the client can append word-by-word rather than
re-rendering a restated sentence.

Benchmarked against plain openai/whisper on this machine before building
this: float32 compute_type ties on raw speed (int8 was slower here, likely
under-optimized on Apple Silicon's CPU path) -- the real win is
word_timestamps, not raw throughput.
"""
import asyncio
import json
import logging
import re
from urllib.parse import parse_qs, urlsplit

import numpy as np
import websockets
from faster_whisper import WhisperModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fasterwhisper_relay")

SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2
LISTEN_PORT = 8767

SILENCE_RMS_THRESHOLD = 0.01
SILENCE_HANG_SECONDS = 0.6
MIN_UTTERANCE_SECONDS = 0.3
MAX_UTTERANCE_SECONDS = 8.0
PARTIAL_CYCLE_SECONDS = 0.5

logger.info("Loading faster-whisper base.en model (float32)...")
model = WhisperModel("base.en", device="cpu", compute_type="float32")
logger.info("Model loaded.")

sessions: dict[str, set] = {}
# session_ids with a currently-connected speaker -- lets viewer cleanup tell
# "no speaker ever showed up for this id" (safe to drop) apart from
# "speaker is live with zero viewers right now" (must not drop).
active_speakers: set[str] = set()

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


def pcm_bytes_to_float32(pcm_bytes: bytes) -> np.ndarray:
    return np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe_final(audio: np.ndarray) -> str:
    segments, _ = model.transcribe(audio, language="en", beam_size=1)
    return collapse_repetition(" ".join(s.text.strip() for s in segments).strip())


def transcribe_words(audio: np.ndarray) -> list[str]:
    segments, _ = model.transcribe(audio, language="en", beam_size=1, word_timestamps=True)
    words = []
    for s in segments:
        for w in s.words:
            words.append(w.word.strip())
    return words


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
            pass
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
    words_sent = 0  # how many words of the CURRENT utterance have already been streamed
    generation = 0  # bumped on every flush; lets a slow partial notice it's stale

    async def send(payload):
        try:
            await websocket.send(json.dumps(payload))
        except websockets.exceptions.ConnectionClosed:
            pass
        if session_id:
            await broadcast(session_id, payload)

    async def partial_cycle():
        nonlocal words_sent
        while True:
            await asyncio.sleep(PARTIAL_CYCLE_SECONDS)
            if speech_s < MIN_UTTERANCE_SECONDS or not buffer:
                continue
            my_generation = generation
            try:
                audio = pcm_bytes_to_float32(bytes(buffer))
                words = await loop.run_in_executor(None, transcribe_words, audio)
            except Exception as e:
                logger.exception(f"partial transcription failed: {e}")
                continue
            if my_generation != generation:
                continue  # a flush happened while this was transcribing -- stale, drop it
            new_words = words[words_sent:]
            if new_words:
                words_sent = len(words)
                await send({"text": " ".join(new_words), "partial": True})

    async def finalize(pcm_bytes):
        try:
            audio = pcm_bytes_to_float32(pcm_bytes)
            text = await loop.run_in_executor(None, transcribe_final, audio)
        except Exception as e:
            logger.exception(f"final transcription failed: {e}")
            return
        if text:
            await send({"text": text, "partial": False})

    async def flush():
        # Awaited everywhere it's called (including from the disconnect
        # path) so the last utterance of a session is never dropped. The
        # generation bump still guards partial_cycle against racing a
        # flush that happened while it was mid-transcription.
        nonlocal buffer, silence_s, speech_s, words_sent, generation
        generation += 1
        if buffer and speech_s >= MIN_UTTERANCE_SECONDS:
            snapshot = bytes(buffer)
            buffer = bytearray()
            silence_s = 0.0
            speech_s = 0.0
            words_sent = 0
            try:
                await asyncio.wait_for(finalize(snapshot), timeout=10.0)
            except asyncio.TimeoutError:
                logger.error("final transcription timed out; utterance dropped")
            except Exception as e:
                logger.exception(f"flush failed: {e}")
        else:
            buffer = bytearray()
            silence_s = 0.0
            speech_s = 0.0
            words_sent = 0

    loop = asyncio.get_running_loop()
    partial_task = asyncio.create_task(partial_cycle())
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
        partial_task.cancel()
        try:
            await partial_task
        except (asyncio.CancelledError, Exception):
            pass
        try:
            await flush()
        except Exception as e:
            logger.exception(f"final flush on disconnect failed: {e}")
        if session_id:
            active_speakers.discard(session_id)
            await broadcast(session_id, {"type": "ended"})
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
        logger.info(f"faster-whisper relay listening on ws://localhost:{LISTEN_PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
