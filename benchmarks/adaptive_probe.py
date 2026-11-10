"""Offline probes of UtteranceBuffer adaptive-noise-floor behaviour using the REAL class
(relays/core/audio_processor.py, unmodified). No relay/model needed. Supplementary to the A/B run:
isolates segmentation only; says nothing about transcription."""
import importlib.util, sys, json
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from audio_utils import read_wav, to_pcm16  # noqa: E402
spec = importlib.util.spec_from_file_location("ap", HERE.parent / "relays/core/audio_processor.py")
ap = importlib.util.module_from_spec(spec); spec.loader.exec_module(ap)
N = 3200  # 100 ms chunks, as the bench/app send
JFK = read_wav(HERE.parent / "whisper.cpp/samples/jfk.wav")


def run(x, adaptive, tail_s=1.5):
    b = ap.UtteranceBuffer(16000, 2, 0.01, 0.6, 0.3, 8.0, adaptive_noise_floor=adaptive, noise_floor_multiplier=2.5)
    pcm = to_pcm16(np.concatenate([x, np.zeros(int(tail_s * 16000), np.float32)]))
    flushes, speech_chunks, forced, thr_last = [], 0, 0, None
    for i in range(0, len(pcm) - N + 1, N):
        c = pcm[i:i + N]
        rms = float(np.sqrt(np.mean((np.frombuffer(c, np.int16) / 32768.0) ** 2)))
        if rms >= b._effective_threshold():
            speech_chunks += 1
        full = len(b.buffer) / 32000 + 0.1 >= 8.0
        if b.add_chunk(c):
            flushes.append(round((i + N) / 32000, 1)); forced += int(full); b.take()
    return {"flushes": flushes, "forced": forced, "speech_chunk_frac": round(speech_chunks / (len(pcm) // N), 3),
            "final_threshold": round(b._effective_threshold(), 4)}


rng = np.random.default_rng(0)
out = {}
print("1) noise-only 20 s (white), should produce NO speech:")
for r in (0.003, 0.008, 0.015, 0.03, 0.06):
    x = (rng.standard_normal(20 * 16000) * r).astype(np.float32)
    out[f"noise_only_{r}"] = {m: run(x, a, 0) for m, a in (("off", False), ("on", True))}
    print(f"  rms={r}: OFF {out[f'noise_only_{r}']['off']}  ON {out[f'noise_only_{r}']['on']}")
print("2) quiet clean speech (JFK scaled):")
for g in (1.0, 0.5, 0.25, 0.15, 0.1):
    x = JFK * g
    out[f"quiet_{g}"] = {m: run(x, a) for m, a in (("off", False), ("on", True))}
    print(f"  gain={g}: OFF {out[f'quiet_{g}']['off']}  ON {out[f'quiet_{g}']['on']}")
print("3) moderate stationary noise: 3 s noise-only lead-in then JFK + noise:")
for r in (0.005, 0.012, 0.02, 0.03, 0.05):
    noise = lambda n: (rng.standard_normal(n) * r).astype(np.float32)
    x = np.concatenate([noise(3 * 16000), JFK + noise(len(JFK))])
    out[f"lead_noise_{r}"] = {m: run(x, a) for m, a in (("off", False), ("on", True))}
    print(f"  noise rms={r}: OFF {out[f'lead_noise_{r}']['off']}  ON {out[f'lead_noise_{r}']['on']}")
(HERE / "results/adaptive_probe.json").write_text(json.dumps(out, indent=1))
