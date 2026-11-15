"""Standalone profiling run against the real production ParakeetNativeEngine (same class parakeet_relay.py
constructs), no relay/websocket involved. Measures: cold load time, per-call inference latency (warm),
real-time factor (RTF = processing_seconds / audio_seconds), CPU%, and RSS memory, sampled on this process
with psutil since the engine runs in-process via ctypes (not a subprocess).

Run from repo root: /tmp/bench-venv/bin/python3 benchmarks/profile_parakeet_v2.py
"""
import asyncio
import json
import sys
import time
import wave
from pathlib import Path

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "relays_phase7c"))
from engines.parakeet_native_engine import ParakeetNativeEngine  # noqa: E402

WAV = ROOT / "whisper.cpp" / "samples" / "jfk.wav"
BUILD_DIR = ROOT / "whisper.cpp" / "build-shared" / "bin"
MODEL = ROOT / "whisper.cpp" / "models" / "ggml-parakeet-tdt-0.6b-v2-q8_0.bin"
REPEATS = 10


def load_pcm16(path: Path) -> bytes:
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2
        return w.readframes(w.getnframes())


async def main():
    proc = psutil.Process()
    pcm = load_pcm16(WAV)
    audio_seconds = len(pcm) / 2 / 16000

    proc.cpu_percent()  # first call always returns 0.0; primes the interval
    rss_before = proc.memory_info().rss

    t0 = time.perf_counter()
    engine = ParakeetNativeEngine(BUILD_DIR, MODEL, use_gpu=True)
    load_seconds = time.perf_counter() - t0
    rss_after_load = proc.memory_info().rss

    # one untimed warm-up call: first real inference after load pays one-time lazy-init costs
    # (Metal pipeline compile, buffer allocation) that production would also pay once per process.
    await engine.transcribe_final(pcm, deadline=None)

    cpu_samples = []
    latencies = []
    for _ in range(REPEATS):
        t0 = time.perf_counter()
        text = await engine.transcribe_final(pcm, deadline=None)
        latencies.append(time.perf_counter() - t0)
        cpu_samples.append(proc.cpu_percent())  # % of one core since the previous call

    rss_peak = proc.memory_info().rss
    await engine.shutdown()

    latencies.sort()
    result = {
        "model": MODEL.name,
        "audio_seconds": audio_seconds,
        "cold_load_seconds": load_seconds,
        "transcript": text,
        "repeats": REPEATS,
        "latency_seconds": {
            "min": latencies[0], "median": latencies[len(latencies) // 2], "max": latencies[-1],
            "mean": sum(latencies) / len(latencies),
        },
        "rtf": {
            "mean": (sum(latencies) / len(latencies)) / audio_seconds,
            "best": latencies[0] / audio_seconds,
        },
        "cpu_percent_per_call": cpu_samples,
        "cpu_percent_mean": sum(cpu_samples) / len(cpu_samples),
        "memory_rss_mb": {
            "before_load": rss_before / 1e6,
            "after_load": rss_after_load / 1e6,
            "peak_during_inference": rss_peak / 1e6,
            "model_footprint": (rss_after_load - rss_before) / 1e6,
        },
    }
    print(json.dumps(result, indent=2))
    out = ROOT / "benchmarks" / "results" / "parakeet_v2_profile.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"\nwritten to {out}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
