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

Session/VAD/broadcast orchestration lives in core/ and is shared with the
other two relays; this file just wires the whisper.cpp engine into it.
"""
import asyncio
import logging
from pathlib import Path

import websockets

from core.audio_processor import UtteranceBuffer
from core.config import (
    ADAPTIVE_NOISE_FLOOR, BYTES_PER_SAMPLE, MAX_UTTERANCE_SECONDS, MIN_UTTERANCE_SECONDS,
    NOISE_FLOOR_MULTIPLIER, SAMPLE_RATE, SILENCE_HANG_SECONDS, SILENCE_RMS_THRESHOLD,
)
from core.protocol import parse_connection_params
from core.session_manager import SessionRegistry
from core.speaker_session import run_speaker_session
from engines.whispercpp_engine import WhisperCppEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("whispercpp_relay")

ROOT = Path(__file__).resolve().parent.parent
WHISPER_CLI = ROOT / "whisper.cpp" / "build" / "bin" / "whisper-cli"
MODEL = ROOT / "whisper.cpp" / "models" / "ggml-base.en.bin"
LISTEN_PORT = 8765

engine = WhisperCppEngine(WHISPER_CLI, MODEL, SAMPLE_RATE, BYTES_PER_SAMPLE)
registry = SessionRegistry()


def _new_buffer() -> UtteranceBuffer:
    return UtteranceBuffer(
        SAMPLE_RATE, BYTES_PER_SAMPLE, SILENCE_RMS_THRESHOLD,
        SILENCE_HANG_SECONDS, MIN_UTTERANCE_SECONDS, MAX_UTTERANCE_SECONDS,
        adaptive_noise_floor=ADAPTIVE_NOISE_FLOOR, noise_floor_multiplier=NOISE_FLOOR_MULTIPLIER,
    )


async def handle(websocket):
    role, session_id = parse_connection_params(websocket)
    if role == "viewer":
        await registry.handle_viewer(websocket, session_id)
    else:
        await run_speaker_session(websocket, session_id, engine, _new_buffer(), registry)


async def main():
    async with websockets.serve(handle, "localhost", LISTEN_PORT, max_size=None):
        logger.info(f"whisper.cpp relay listening on ws://localhost:{LISTEN_PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
