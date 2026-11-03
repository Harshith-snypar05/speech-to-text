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

Session/VAD/broadcast orchestration lives in core/ and is shared with the
other two relays; this file just wires the openai/whisper engine into it.
"""
import asyncio
import logging

import websockets

from core.audio_processor import UtteranceBuffer
from core.config import (
    ADAPTIVE_NOISE_FLOOR, BYTES_PER_SAMPLE, MAX_UTTERANCE_SECONDS, MIN_UTTERANCE_SECONDS,
    NOISE_FLOOR_MULTIPLIER, SAMPLE_RATE, SILENCE_HANG_SECONDS, SILENCE_RMS_THRESHOLD,
)
from core.protocol import parse_connection_params
from core.session_manager import SessionRegistry
from core.speaker_session import run_speaker_session
from engines.openai_whisper_engine import OpenAIWhisperEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("openai_whisper_relay")

LISTEN_PORT = 8766

logger.info("Loading openai/whisper base.en model...")
engine = OpenAIWhisperEngine()
logger.info("Model loaded.")

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
        logger.info(f"openai/whisper relay listening on ws://localhost:{LISTEN_PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
