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

Session/VAD/broadcast orchestration lives in core/ and is shared with the
other two relays; this file just wires the faster-whisper engine into it.
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
from engines.fasterwhisper_engine import FasterWhisperEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fasterwhisper_relay")

LISTEN_PORT = 8767

logger.info("Loading faster-whisper base.en model (float32)...")
engine = FasterWhisperEngine()
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
        logger.info(f"faster-whisper relay listening on ws://localhost:{LISTEN_PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
