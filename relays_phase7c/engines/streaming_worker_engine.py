"""Client for the out-of-process NVIDIA streaming ASR worker (asr_worker/stream_worker.py, runs in its own venv).

The worker holds one loaded model and one decoder/cache state per connection, so audio is decoded in small chunks as it
arrives. Partial text therefore grows monotonically and its delay does not depend on utterance length (unlike the
re-decode-the-whole-buffer path of ParakeetNativeEngine).

Wire protocol (localhost websocket):
  relay -> worker: text {"type":"start","model":"<key>"}; binary PCM16 mono 16 kHz; text {"type":"flush"}
  worker -> relay: {"type":"ready"} | {"type":"partial","text":<utterance text so far>}
                   | {"type":"final","text":<utterance text>} | {"type":"error","detail":...}
"""
import json
import logging

import websockets

logger = logging.getLogger(__name__)

MODELS = {
    "eou120m": "nvidia/parakeet_realtime_eou_120m-v1",
    "nemotron": "nvidia/nemotron-speech-streaming-en-0.6b",
    "nemotron35": "nvidia/nemotron-3.5-asr-streaming-0.6b",
    "multitalker": "nvidia/multitalker-parakeet-streaming-0.6b-v1",
}


class StreamHandle:
    def __init__(self, ws):
        self._ws = ws

    async def send_audio(self, pcm: bytes):
        await self._ws.send(pcm)

    async def flush(self):
        await self._ws.send(json.dumps({"type": "flush"}))

    async def events(self):
        async for m in self._ws:
            if isinstance(m, str):
                yield json.loads(m)

    async def close(self):
        try:
            await self._ws.close()
        except Exception:
            pass


class StreamingWorkerEngine:
    is_streaming = True
    supports_partial = True
    supports_scheduling = False

    def __init__(self, model_key: str, url: str = "ws://127.0.0.1:8780"):
        if model_key not in MODELS:
            raise SystemExit(f"unknown streaming model '{model_key}'; choose one of {sorted(MODELS)}")
        self.model_key = model_key
        self.model_name = MODELS[model_key]
        self.url = url
        # EOU models mark the end of an utterance themselves; the others need the relay to endpoint on silence.
        self.has_eou = model_key == "eou120m"

    async def open_stream(self) -> StreamHandle:
        # loopback to our own worker: library keepalive pings only add a failure mode (a worker busy decoding answers late, the
        # ping times out and the stream dies mid-session), so they are off; a dead worker still closes the socket.
        ws = await websockets.connect(self.url, max_size=None, open_timeout=10, ping_interval=None)
        await ws.send(json.dumps({"type": "start", "model": self.model_key}))
        ready = json.loads(await ws.recv())
        if ready.get("type") != "ready":
            await ws.close()
            raise RuntimeError(f"ASR worker refused stream: {ready}")
        return StreamHandle(ws)

    async def shutdown(self) -> None:
        return None
