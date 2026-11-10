"""Same three probes as ../adaptive_probe.py (same RNG seed / inputs), run against the
experimental VADs next to the fixed and production-adaptive baselines. Writes
../results/vad_probe_experimental.json. Segmentation only; says nothing about WER."""
import json, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
from audio_utils import read_wav, to_pcm16  # noqa: E402
from run_experiment import make_vad  # noqa: E402
N = 3200
JFK = read_wav(HERE.parents[1] / "whisper.cpp/samples/jfk.wav")
VADS = ["fixed", "prod_adaptive", "exp_v1", "exp", "exp_lowlo"]


def run(x, name, tail_s=1.5):
    b = make_vad(name)
    pcm = to_pcm16(np.concatenate([x, np.zeros(int(tail_s * 16000), np.float32)]))
    fl, sp, forced = [], 0, 0
    for i in range(0, len(pcm) - N + 1, N):
        c = pcm[i:i + N]
        full = len(b.buffer) / 32000 + 0.1 >= 8.0
        pre = None
        if name in ("fixed", "prod_adaptive"):
            rms = float(np.sqrt(np.mean((np.frombuffer(c, np.int16) / 32768.0) ** 2)))
            pre = rms >= b._effective_threshold()
        if b.add_chunk(c):
            fl.append(round((i + N) / 32000, 1)); forced += int(full); b.take()
        sp += int(pre if pre is not None else b.last_is_speech)
    return {"flushes": fl, "forced": forced, "speech_chunk_frac": round(sp / (len(pcm) // N), 3)}


rng = np.random.default_rng(0)
out = {}
def show(key, x, tail=1.5):
    out[key] = {v: run(x, v, tail) for v in VADS}
    print(key)
    for v in VADS:
        print(f"   {v:14s}", out[key][v])

print("1) noise-only 20 s white (any speech_chunk_frac / flush = false activation)")
for r in (0.003, 0.008, 0.015, 0.03, 0.06):
    show(f"noise_only_{r}", (rng.standard_normal(20 * 16000) * r).astype(np.float32), 0)
print("2) quiet clean JFK")
for g in (1.0, 0.5, 0.25, 0.15, 0.1):
    show(f"quiet_{g}", JFK * g)
print("3) 3 s noise lead-in then JFK + white noise")
for r in (0.005, 0.012, 0.02, 0.03, 0.05):
    nz = lambda n: (rng.standard_normal(n) * r).astype(np.float32)
    show(f"lead_noise_{r}", np.concatenate([nz(3 * 16000), JFK + nz(len(JFK))]))
(HERE.parent / "results/vad_probe_experimental.json").write_text(json.dumps(out, indent=1))
