"""Low-latency live-transcription relay for NVIDIA's Parakeet TDT model,
via whisper.cpp's native `parakeet-cli` (same vendored fork already used
for the whisper.cpp relay -- this is a separate binary/model, not a
variant of whisper-cli). Same VAD-pause-triggered single-shot approach as
the other CLI-based relay (whisper.cpp): transcribe once per utterance,
the instant you pause.

Measured against the other three engines on this hardware (same JFK
clip + noise-degraded variants, same WER/RTF methodology): best accuracy
at every noise level tested (100% at 0dB SNR vs 90-95% for the others,
90.91% at -5dB SNR vs 63-77%), and fastest raw inference (~131ms vs
232-326ms for an 11s clip). Requires the model downloaded separately --
see MODEL path below; not bundled in the repo (~669MB).

Also acts as the same thin session broadcaster: a speaker connects with
?role=speaker&session=<token>, a viewer connects with
?role=viewer&session=<token> and receives the same transcript messages
read-only. The session dies the moment the speaker disconnects.

Session/VAD/broadcast orchestration lives in core/ and is shared with the
other three relays; this file just wires the Parakeet engine into it.
"""
import asyncio
import logging
from pathlib import Path

import websockets

from core.audio_processor import UtteranceBuffer
from core.config import (
    ADAPTIVE_NOISE_FLOOR, BYTES_PER_SAMPLE, MAX_TOTAL_CONNECTIONS, MAX_UTTERANCE_SECONDS,
    MAX_VIEWERS_PER_SESSION, MIN_UTTERANCE_SECONDS, NOISE_FLOOR_MULTIPLIER, SAMPLE_RATE,
    SILENCE_HANG_SECONDS, SILENCE_RMS_THRESHOLD,
)
from core.protocol import is_valid_access_code, is_valid_session_id, parse_connection_params
from core.session_manager import SessionRegistry
from core.speaker_session import run_speaker_session
from engines.parakeet_engine import ParakeetEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("parakeet_relay")

ROOT = Path(__file__).resolve().parent.parent
PARAKEET_CLI = ROOT / "whisper.cpp" / "build" / "bin" / "parakeet-cli"
MODEL = ROOT / "whisper.cpp" / "models" / "ggml-parakeet-tdt-0.6b-v3-q8_0.bin"
LISTEN_PORT = 8768

engine = ParakeetEngine(PARAKEET_CLI, MODEL, SAMPLE_RATE, BYTES_PER_SAMPLE)
registry = SessionRegistry(max_viewers_per_session=MAX_VIEWERS_PER_SESSION, max_total_connections=MAX_TOTAL_CONNECTIONS)


def _new_buffer() -> UtteranceBuffer:
    return UtteranceBuffer(
        SAMPLE_RATE, BYTES_PER_SAMPLE, SILENCE_RMS_THRESHOLD,
        SILENCE_HANG_SECONDS, MIN_UTTERANCE_SECONDS, MAX_UTTERANCE_SECONDS,
        adaptive_noise_floor=ADAPTIVE_NOISE_FLOOR, noise_floor_multiplier=NOISE_FLOOR_MULTIPLIER,
    )


async def handle(websocket):
    params = parse_connection_params(websocket)
    if not is_valid_access_code(params.access_code):
        await websocket.close(code=4400, reason="malformed access code")
        return
    if params.role == "viewer":
        await registry.handle_viewer(websocket, params.session_id, params.access_code)
    else:
        if params.session_id and not is_valid_session_id(params.session_id):
            await websocket.close(code=4400, reason="malformed session id")
            return
        await run_speaker_session(websocket, params.session_id, engine, _new_buffer(), registry, params.access_code)


async def main():
    async with websockets.serve(handle, "localhost", LISTEN_PORT, max_size=None):
        logger.info(f"Parakeet relay listening on ws://localhost:{LISTEN_PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
