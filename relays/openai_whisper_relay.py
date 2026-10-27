"""Low-latency live-transcription relay for the plain openai/whisper package.

openai/whisper has no streaming API at all (batch-only, transcribe() runs on
a full array). Rather than re-decoding a fixed window on a fixed timer (which
wastes time on silence and makes every result wait for the next tick), this
relay watches incoming audio energy and transcribes the instant you pause --
same mechanism as WhisperLiveKit's VAD-triggered segmentation, so results
fire as soon as a sentence ends instead of up to CYCLE_SECONDS later.
"""
import asyncio
import json
import logging

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
MAX_UTTERANCE_SECONDS = 15.0   # force-flush long continuous speech even without a pause

logger.info("Loading openai/whisper base.en model...")
model = whisper.load_model("base.en")
logger.info("Model loaded.")


def pcm_bytes_to_float32(pcm_bytes: bytes) -> np.ndarray:
    return np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0


async def transcribe_window(pcm_bytes: bytes) -> str:
    audio = pcm_bytes_to_float32(pcm_bytes)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: model.transcribe(audio, language="en", fp16=False, temperature=0.0)
    )
    return result.get("text", "").strip()


async def handle(websocket):
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
            try:
                await websocket.send(json.dumps({"text": text}))
            except websockets.exceptions.ConnectionClosed:
                pass

    def flush():
        nonlocal buffer, silence_s, speech_s
        if buffer and speech_s >= MIN_UTTERANCE_SECONDS:
            asyncio.create_task(transcribe_and_send(bytes(buffer)))
        buffer = bytearray()
        silence_s = 0.0
        speech_s = 0.0

    logger.info("Client connected")
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
                flush()
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        flush()
        logger.info("Client disconnected")


async def main():
    async with websockets.serve(handle, "localhost", LISTEN_PORT, max_size=None):
        logger.info(f"openai/whisper relay listening on ws://localhost:{LISTEN_PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
