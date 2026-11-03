"""Low-latency live-transcription relay for whisper.cpp.

whisper.cpp ships no network streaming server (its `server` example is
batch/file-upload only, and `stream` reads the local mic directly via SDL2).
Earlier version of this relay faked streaming with a fixed timer, re-decoding
a sliding window every CYCLE_SECONDS -- that gave a fast first partial but
restated the whole sentence-so-far on every cycle (visible repetition).
Switched to the same VAD-pause-triggered single-shot approach as
openai_whisper_relay.py: transcribe once per utterance, the instant you
pause. Clean output, same wire protocol -- drop-in replacement either way.

Also acts as the same thin session broadcaster: a speaker connects with
?role=speaker&session=<token>, a viewer connects with
?role=viewer&session=<token> and receives the same transcript messages
read-only. The session dies the moment the speaker disconnects.
"""
import asyncio
import json
import logging
import re
import tempfile
import wave
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import numpy as np
import websockets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("whispercpp_relay")

ROOT = Path(__file__).resolve().parent.parent
WHISPER_CLI = ROOT / "whisper.cpp" / "build" / "bin" / "whisper-cli"
MODEL = ROOT / "whisper.cpp" / "models" / "ggml-base.en.bin"
SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2
LISTEN_PORT = 8765

SILENCE_RMS_THRESHOLD = 0.01
SILENCE_HANG_SECONDS = 0.6
MIN_UTTERANCE_SECONDS = 0.3
MAX_UTTERANCE_SECONDS = 8.0

# session_id -> set of viewer websockets currently watching that speaker
sessions: dict[str, set] = {}
# session_ids with a currently-connected speaker -- lets viewer cleanup tell
# "no speaker ever showed up for this id" (safe to drop) apart from
# "speaker is live with zero viewers right now" (must not drop).
active_speakers: set[str] = set()

# Same degenerate-repetition collapse as openai_whisper_relay.py -- whisper.cpp
# shares the same underlying Whisper decoder and can hallucinate the same way
# on long/ambiguous audio.
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


def write_wav(path: str, pcm_bytes: bytes):
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(BYTES_PER_SAMPLE)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(pcm_bytes)


async def transcribe_window(pcm_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        write_wav(tmp.name, pcm_bytes)
        tmp_path = tmp.name
    try:
        proc = await asyncio.create_subprocess_exec(
            str(WHISPER_CLI), "-m", str(MODEL), "-f", tmp_path, "--no-prints", "-nt",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        return collapse_repetition(stdout.decode("utf-8", errors="replace").strip())
    finally:
        Path(tmp_path).unlink(missing_ok=True)


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
    if not WHISPER_CLI.exists():
        raise SystemExit(f"whisper-cli not found at {WHISPER_CLI}")
    if not MODEL.exists():
        raise SystemExit(f"model not found at {MODEL}")
    async with websockets.serve(handle, "localhost", LISTEN_PORT, max_size=None):
        logger.info(f"whisper.cpp relay listening on ws://localhost:{LISTEN_PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
