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
import os
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
from core import billing as billing_mod
from core.speaker_session import run_speaker_session
from core.streaming_session import run_streaming_session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("parakeet_relay")

ROOT = Path(__file__).resolve().parent.parent
WHISPER_CPP = ROOT / "whisper.cpp"
MODEL = WHISPER_CPP / "models" / "ggml-parakeet-tdt-0.6b-v3-q8_0.bin"
SHARED_BUILD_DIR = WHISPER_CPP / "build-shared" / "bin"
PARAKEET_CLI = WHISPER_CPP / "build" / "bin" / ("parakeet-cli.exe" if sys.platform == "win32" else "parakeet-cli")
LISTEN_PORT = int(os.environ.get("STT_LISTEN_PORT", "8768"))

from engines.parakeet_native_engine import find_library, library_filename  # noqa: E402

# STT_ENGINE selects the ASR backend (staging experiments). Unset/"parakeet" = the original whisper.cpp Parakeet path.
# eou120m | nemotron | nemotron35 | multitalker = true streaming NVIDIA models served by asr_worker/stream_worker.py.
STT_ENGINE = os.environ.get("STT_ENGINE", "parakeet").strip().lower()
STREAMING = STT_ENGINE != "parakeet"

if STREAMING:
    from engines.streaming_worker_engine import StreamingWorkerEngine
    engine = StreamingWorkerEngine(STT_ENGINE, os.environ.get("STT_ASR_WORKER_URL", "ws://127.0.0.1:8780"))
    logger.info("using StreamingWorkerEngine model=%s (%s)", STT_ENGINE, engine.model_name)
elif find_library(SHARED_BUILD_DIR) is not None:
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


# API denial reasons that close with 4402 (out of minutes / allowance held); everything else is 4401 (not allowed)
BILLING_DENY_4402 = ("quota_exhausted", "personal_limit", "allowance_reserved", "payment_required")
# the account may not transcribe until its email is verified (close 4403, reason "email_not_verified")
BILLING_DENY_4403 = ("email_not_verified",)


# One live speaker connection per session id. A reconnect (e.g. a phone that changed network while the old socket is
# still half-open) supersedes the old one: the old socket is closed with 4409 and its closing billing report is awaited
# BEFORE the new connection is authorized, so two sockets can never bill the same session at once.
SUPERSEDE_WAIT_SECONDS = 8.0
_speakers: dict[str, tuple] = {}     # session_id -> (websocket, done_event)

# Capacity gate. One ASR worker process serves every live stream; measured on the staging box (1 GPU), 1 stream is real-time,
# 4 already lag by seconds and 5 for two minutes ended in keepalive timeouts. Past the cap a new speaker is refused (1013,
# "server_busy") BEFORE it is authorized, so no allowance is reserved and nothing is billed. 0 = unlimited.
MAX_ACTIVE_STREAMS = int(os.environ.get("STT_MAX_ACTIVE_STREAMS", "3"))
_active_streams = 0


async def handle(websocket):
    params = parse_connection_params(websocket)
    if not is_valid_access_code(params.access_code):
        await websocket.close(code=4400, reason="malformed access code")
        return
    if params.role == "viewer":
        await registry.handle_viewer(websocket, params.session_id, params.access_code)
        return
    sid = params.session_id
    done = asyncio.Event()
    if sid and billing_mod.enabled():
        old = _speakers.get(sid)
        if old is not None:
            try:
                await old[0].close(code=4409, reason="superseded")
            except Exception:
                pass
            try:
                await asyncio.wait_for(old[1].wait(), SUPERSEDE_WAIT_SECONDS)
            except asyncio.TimeoutError:
                logger.warning("old speaker for session %s did not finish its closing report in time", sid)
        _speakers[sid] = (websocket, done)
    try:
        await _handle_speaker(websocket, params)
    finally:
        done.set()
        if sid and _speakers.get(sid, (None,))[0] is websocket:
            _speakers.pop(sid, None)


async def _handle_speaker(websocket, params):
    global _active_streams
    if params.session_id and not is_valid_session_id(params.session_id):
        await websocket.close(code=4400, reason="malformed session id")
        return
    if STREAMING and MAX_ACTIVE_STREAMS and _active_streams >= MAX_ACTIVE_STREAMS:
        logger.warning("refusing speaker %s: %d active streams (cap %d)", params.session_id, _active_streams, MAX_ACTIVE_STREAMS)
        await websocket.close(code=1013, reason="server_busy")
        return
    _active_streams += 1
    try:
        await _speaker_admitted(websocket, params)
    finally:
        _active_streams -= 1


async def _speaker_admitted(websocket, params):
    billing_ctx = None
    if billing_mod.enabled():
        # customer account: the ScriptLiv API validates the token and the remaining minutes; fail closed
        if not STREAMING or not params.session_id:
            await websocket.close(code=1013 if not STREAMING else 4400, reason="not available")
            return
        verdict = await billing_mod.authorize_start(params.token, params.session_id)
        if not verdict.get("allowed"):
            reason = verdict.get("reason")
            code = 4402 if reason in BILLING_DENY_4402 else 4403 if reason in BILLING_DENY_4403 else 4401
            await websocket.close(code=code, reason=reason or "denied")
            return
        billing_ctx = billing_mod.BillingContext(verdict["user_id"], params.session_id, verdict.get("remaining_seconds", 0), verdict.get("base_seconds", 0.0))
    if STREAMING:
        await run_streaming_session(websocket, params.session_id, engine, registry, params.access_code, billing=billing_ctx, refiner=refiner)
    else:
        await run_speaker_session(websocket, params.session_id, engine, _new_buffer(), registry, params.access_code)


# Optional second pass (off unless STT_REFINE_ENGINE is set): re-listens to each finalized utterance with a Nemotron
# worker in its own process and swaps the line in place. Never on the live path; see core/refiner.py.
refiner = None
if STREAMING and os.environ.get("STT_REFINE_ENGINE"):
    from core.refiner import Refiner
    _refine_engine = StreamingWorkerEngine(os.environ["STT_REFINE_ENGINE"].strip().lower(),
                                           os.environ.get("STT_REFINE_WORKER_URL", "ws://127.0.0.1:8781"))
    refiner = Refiner(_refine_engine, log_path=os.environ.get("STT_REFINE_LOG_FILE") or None)
    logger.info("text refinement enabled: %s via %s", _refine_engine.model_name, _refine_engine.url)


async def main():
    async with websockets.serve(handle, "localhost", LISTEN_PORT, max_size=None):
        logger.info(f"Parakeet relay listening on ws://localhost:{LISTEN_PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
