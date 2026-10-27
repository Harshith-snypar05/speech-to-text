"""Chunked live-transcription relay for whisper.cpp.

whisper.cpp ships no network streaming server (its `server` example is
batch/file-upload only, and `stream` reads the local mic directly via SDL2).
This relay fakes streaming: it buffers incoming PCM, and every CYCLE_SECONDS
re-transcribes the trailing WINDOW_SECONDS window by shelling out to the
`whisper-cli` binary against a temp WAV file.
"""
import asyncio
import json
import logging
import tempfile
import wave
from pathlib import Path

import websockets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("whispercpp_relay")

ROOT = Path(__file__).resolve().parent.parent
WHISPER_CLI = ROOT / "whisper.cpp" / "build" / "bin" / "whisper-cli"
MODEL = ROOT / "whisper.cpp" / "models" / "ggml-base.en.bin"
SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2
LISTEN_PORT = 8765
CYCLE_SECONDS = 1.2
WINDOW_SECONDS = 10.0


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
        return stdout.decode("utf-8", errors="replace").strip()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def handle(websocket):
    buffer = bytearray()
    lock = asyncio.Lock()
    stop = asyncio.Event()

    async def receiver():
        nonlocal buffer
        try:
            async for message in websocket:
                if isinstance(message, (bytes, bytearray)):
                    async with lock:
                        buffer.extend(message)
        finally:
            stop.set()

    async def cycle():
        nonlocal buffer
        while not stop.is_set():
            await asyncio.sleep(CYCLE_SECONDS)
            async with lock:
                window_bytes = int(WINDOW_SECONDS * SAMPLE_RATE * BYTES_PER_SAMPLE)
                snapshot = bytes(buffer[-window_bytes:])
                if len(buffer) > window_bytes:
                    buffer = buffer[-window_bytes:]
            if len(snapshot) < SAMPLE_RATE * BYTES_PER_SAMPLE:  # less than 1s
                continue
            try:
                text = await transcribe_window(snapshot)
            except Exception as e:
                logger.exception(f"transcription failed: {e}")
                continue
            if text:
                try:
                    await websocket.send(json.dumps({"text": text}))
                except websockets.exceptions.ConnectionClosed:
                    return

    recv_task = asyncio.create_task(receiver())
    cycle_task = asyncio.create_task(cycle())
    logger.info("Client connected")
    await asyncio.wait([recv_task, cycle_task], return_when=asyncio.FIRST_COMPLETED)
    stop.set()
    cycle_task.cancel()
    recv_task.cancel()
    logger.info("Client disconnected")


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
