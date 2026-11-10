"""Live-transcription relay for NVIDIA's Parakeet TDT model, via
whisper.cpp's native Parakeet support (this vendored whisper.cpp fork is
still a dependency -- it's where libparakeet/parakeet-cli live -- even
though the whisper.cpp *relay* itself was removed). VAD-pause-triggered:
transcribe once per utterance, the instant you pause.

The only engine in this app. whisper.cpp, openai/whisper, and
faster-whisper relays existed earlier in this project and were removed
after head-to-head testing on this hardware (same JFK clip +
noise-degraded variants, same WER methodology) showed Parakeet ahead on
accuracy at every noise level tested: 100% at 0dB SNR vs 90-95% for the
others, 90.91% at -5dB SNR vs 63-77%.

Two engine implementations, picked automatically:
- ParakeetNativeEngine (engines/parakeet_native_engine.py): ctypes binding
  against a shared-library build of libparakeet, model loaded ONCE at
  relay startup and reused for every utterance -- matches faster-whisper/
  openai-whisper's in-process architecture. ~130ms per utterance after
  the one-time startup cost, and (also unlike the subprocess engine)
  supports word-by-word partial streaming the same way faster-whisper
  does, since re-running inference every PARTIAL_CYCLE_SECONDS is only
  cheap once there's no per-call subprocess/reload cost. Used
  automatically if the shared library has been built (see that file's
  docstring for the build command -- it's an extra step, not part of the
  default whisper.cpp build).
- ParakeetEngine (engines/parakeet_engine.py): shells out to a fresh
  `parakeet-cli` subprocess per utterance, reloading the full 668MB model
  from disk every single time (~350-520ms measured, not the ~130ms pure
  inference figure), final-only (no partials -- would mean re-spawning a
  subprocess every 500ms). Used as a fallback when the shared library
  isn't built, so this relay still works without the extra build step,
  just slower and without partials.

Requires the model downloaded separately -- see MODEL path below; not
bundled in the repo (~669MB).

Also acts as the same thin session broadcaster: a speaker connects with
?role=speaker&session=<token>, a viewer connects with
?role=viewer&session=<token> and receives the same transcript messages
read-only -- including everything said before they joined (replayed from
core/transcript_store on connect) and, if the speaker has already
disconnected, the full saved transcript followed by an immediate close.

Session/VAD/broadcast orchestration lives in core/ -- built shared across
what used to be four relays, kept that way (rather than inlined here)
in case another engine is added later; this file just wires the
Parakeet engine into it.
"""
import asyncio
import logging
import sys
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("parakeet_relay")

ROOT = Path(__file__).resolve().parent.parent
WHISPER_CPP = ROOT / "whisper.cpp"
MODEL = WHISPER_CPP / "models" / "ggml-parakeet-tdt-0.6b-v3-q8_0.bin"
SHARED_BUILD_DIR = WHISPER_CPP / "build-shared" / "bin"
PARAKEET_CLI = WHISPER_CPP / "build" / "bin" / ("parakeet-cli.exe" if sys.platform == "win32" else "parakeet-cli")
LISTEN_PORT = 8768

from engines.parakeet_native_engine import find_library, library_filename  # noqa: E402

if find_library(SHARED_BUILD_DIR) is not None:
    from engines.parakeet_native_engine import ParakeetNativeEngine
    logger.info("using ParakeetNativeEngine (model loaded once, shared library found)")
    engine = ParakeetNativeEngine(SHARED_BUILD_DIR, MODEL)
else:
    from engines.parakeet_engine import ParakeetEngine
    logger.warning(
        "%s not found in %s -- falling back to per-utterance subprocess "
        "(slower, ~350-520ms vs ~130ms per utterance; see this file's docstring to build the shared library)",
        library_filename(), SHARED_BUILD_DIR,
    )
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
