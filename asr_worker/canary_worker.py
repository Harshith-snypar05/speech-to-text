"""Canary-Qwen-2.5B second-pass worker (runs in asr_venv, torch cu128 + NeMo). Staging.

It is NOT a live engine: Canary is an offline speech-augmented LLM. The relay keeps Parakeet TDT as the live engine and
replays each finalized utterance here (core/refiner.py); an accepted result replaces the line in place.

Same wire protocol as stream_worker.py, so StreamingWorkerEngine("canary") and the Refiner work unchanged:
  in : text {"type":"start","model":"canary"} | binary PCM16 mono 16 kHz | text {"type":"flush"}
  out: {"type":"ready"} | {"type":"final","text":...} | {"type":"error","detail":...}
Audio is collected until `flush`, transcribed once, and answered with one `final`.

Run:  asr_venv\\Scripts\\python.exe asr_worker\\canary_worker.py --port 8781
"""
import argparse
import asyncio
import json
import logging
import os
import re
import tempfile
import threading
import time

import numpy as np
import soundfile as sf
import torch
import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("canary_worker")

MODEL_NAME = "nvidia/canary-qwen-2.5b"
KEY = "canary"
SR = 16000
MAX_CLIP_S = 35.0          # the model was trained on clips up to 40 s; longer audio is cut into pieces
MAX_NEW_TOKENS = 256
GPU_LOCK = threading.Lock()
# Canary writes disfluencies the live engine leaves out; they only add noise to a transcript.
_FILLER = re.compile(r"\b(?:uh+|um+|uhm+|erm+|hmm+|mm+)\b[,.]?\s*", re.IGNORECASE)

_model = None

# CUDA by default; Apple Silicon (no NVIDIA GPU) uses Metal via MPS instead. bf16 is what the CUDA path already
# used; MPS's bf16 op coverage is still incomplete in places NeMo's SALM touches, so MPS gets float16 instead
# (CPU gets float32 since it has no fp16 speed benefit and worse numerical behavior for this model).
if torch.cuda.is_available():
    DEVICE, DTYPE = "cuda", torch.bfloat16
elif torch.backends.mps.is_available():
    DEVICE, DTYPE = "mps", torch.float16
else:
    DEVICE, DTYPE = "cpu", torch.float32


def _memory_gb() -> float:
    if DEVICE == "cuda":
        return torch.cuda.memory_allocated() / 1e9
    if DEVICE == "mps":
        return torch.mps.current_allocated_memory() / 1e9
    return 0.0


def load():
    global _model
    if _model is None:
        from nemo.collections.speechlm2.models import SALM
        t = time.time()
        _model = SALM.from_pretrained(MODEL_NAME).eval().to(DTYPE).to(DEVICE)
        log.info("loaded %s in %.0fs on %s, mem %.1f GB", MODEL_NAME, time.time() - t, DEVICE, _memory_gb())
        _transcribe_array(np.zeros(SR, dtype=np.float32))  # warm-up
    return _model


def clean(text: str) -> str:
    text = _FILLER.sub("", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _transcribe_array(audio: np.ndarray) -> str:
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        sf.write(path, audio, SR, subtype="PCM_16")
        m = _model
        with GPU_LOCK, torch.inference_mode():
            ids = m.generate(
                prompts=[[{"role": "user", "content": f"Transcribe the following: {m.audio_locator_tag}", "audio": [path]}]],
                max_new_tokens=MAX_NEW_TOKENS)
        return m.tokenizer.ids_to_text(ids[0].cpu())
    finally:
        os.remove(path)


def transcribe(pcm: bytes) -> str:
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if len(audio) < SR * 0.3:
        return ""
    step = int(MAX_CLIP_S * SR)
    parts = [clean(_transcribe_array(audio[i:i + step])) for i in range(0, len(audio), step)]
    return " ".join(p for p in parts if p)


async def handle(ws):
    loop = asyncio.get_running_loop()
    buf = bytearray()
    started = False
    try:
        async for msg in ws:
            if isinstance(msg, str):
                m = json.loads(msg)
                if m.get("type") == "start":
                    if m.get("model") != KEY:
                        await ws.send(json.dumps({"type": "error", "detail": f"this worker serves only '{KEY}'"}))
                        await ws.close()
                        return
                    await loop.run_in_executor(None, load)
                    started = True
                    await ws.send(json.dumps({"type": "ready"}))
                elif m.get("type") == "flush" and started:
                    pcm, buf = bytes(buf), bytearray()
                    t = time.time()
                    text = await loop.run_in_executor(None, transcribe, pcm)
                    log.info("%.1fs audio -> %.2fs: %s", len(pcm) / (SR * 2), time.time() - t, text)
                    await ws.send(json.dumps({"type": "final", "text": text}))
            elif started:
                buf.extend(msg)
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        log.exception("canary stream error")
        try:
            await ws.send(json.dumps({"type": "error", "detail": str(e)}))
        except Exception:
            pass


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8781)
    ap.add_argument("--no-preload", action="store_true", help="load the model on the first stream instead of at start")
    a = ap.parse_args()
    if not a.no_preload:
        load()
    # loopback only, no keepalive pings (a decode can keep this loop busy past the ping timeout)
    async with websockets.serve(handle, "127.0.0.1", a.port, max_size=None, ping_interval=None):
        log.info("Canary worker listening on ws://127.0.0.1:%d", a.port)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
