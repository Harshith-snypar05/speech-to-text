"""Build / extend a benchmark corpus manifest.

  # register a real recording (16-bit WAV, any rate; resampled to 16 kHz mono)
  python make_corpus.py add --out corpus --id ind_eng_01 --wav raw/ind_eng_01.wav \
      --ref "the quick brown fox ..." --tag accent=indian_english --tag domain=technical

  # derive degraded / speed-changed variants from a registered clip
  python make_corpus.py variants --out corpus --id ind_eng_01 \
      --snr 20 10 5 0 -5 --speed 0.8 1.25 --noise-file raw/cafe_babble.wav

Variants keep `timing_wav` pointing at the CLEAN source so speech start/end
ground truth isn't corrupted by the added noise. Speed change is a plain
resample (pitch shifts with tempo) -- a crude rate stressor; prefer real
fast/slow speakers when you have them.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audio_utils import SAMPLE_RATE, read_wav, resample, write_wav  # noqa: E402


def load(out: Path) -> dict:
    p = out / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"clips": []}


def save(out: Path, m: dict):
    (out / "manifest.json").write_text(json.dumps(m, indent=2), encoding="utf-8")


def mix_at_snr(speech: np.ndarray, noise: np.ndarray, snr_db: float, rng) -> np.ndarray:
    if len(noise) < len(speech):
        noise = np.tile(noise, int(np.ceil(len(speech) / len(noise))))
    start = rng.integers(0, len(noise) - len(speech) + 1)
    noise = noise[start:start + len(speech)]
    # SNR measured over the speech-active region (frames above a loose floor),
    # otherwise long pauses make a "0 dB" clip far cleaner than it sounds.
    active = np.abs(speech) > 0.02 * max(np.abs(speech).max(), 1e-9)
    p_sig = float(np.mean(speech[active] ** 2)) if active.any() else float(np.mean(speech ** 2))
    p_noise = float(np.mean(noise ** 2)) or 1e-12
    gain = np.sqrt(p_sig / (p_noise * 10 ** (snr_db / 10)))
    mixed = speech + gain * noise
    peak = np.abs(mixed).max()
    return mixed / peak * 0.95 if peak > 0.95 else mixed


def cmd_add(a):
    out = Path(a.out)
    (out / "wav").mkdir(parents=True, exist_ok=True)
    x = read_wav(a.wav)
    dest = out / "wav" / f"{a.id}.wav"
    write_wav(dest, x)
    tags = dict(t.split("=", 1) for t in a.tag)
    m = load(out)
    m["clips"] = [c for c in m["clips"] if c["id"] != a.id]
    m["clips"].append({"id": a.id, "wav": f"wav/{a.id}.wav", "reference": a.ref,
                       "tags": {"noise": "clean", "speed": "1.0", **tags}})
    save(out, m)
    print(f"added {a.id}: {len(x) / SAMPLE_RATE:.1f}s")


def cmd_variants(a):
    out = Path(a.out)
    m = load(out)
    base = next((c for c in m["clips"] if c["id"] == a.id), None)
    if not base:
        sys.exit(f"clip {a.id} not in manifest; run `add` first")
    x = read_wav(out / base["wav"])
    rng = np.random.default_rng(a.seed)
    noise = read_wav(a.noise_file) if a.noise_file else None
    new = []
    for snr in a.snr or []:
        n = noise if noise is not None else rng.standard_normal(len(x)).astype(np.float32)
        y = mix_at_snr(x, n, snr, rng)
        vid = f"{a.id}__snr{snr:g}"
        write_wav(out / "wav" / f"{vid}.wav", y)
        new.append({**base, "id": vid, "wav": f"wav/{vid}.wav", "timing_wav": base["wav"],
                    "tags": {**base["tags"], "noise": f"snr{snr:g}dB_{'file' if a.noise_file else 'white'}"}})
    for sp in a.speed or []:
        y = resample(x, SAMPLE_RATE, int(round(SAMPLE_RATE / sp)))  # sp>1 => shorter => faster
        vid = f"{a.id}__x{sp:g}"
        write_wav(out / "wav" / f"{vid}.wav", y)
        # speed variants change timing, so let the bench re-detect from the variant itself
        new.append({**base, "id": vid, "wav": f"wav/{vid}.wav", "timing_wav": f"wav/{vid}.wav",
                    "tags": {**base["tags"], "speed": f"{sp:g}"}})
    ids = {c["id"] for c in new}
    m["clips"] = [c for c in m["clips"] if c["id"] not in ids] + new
    save(out, m)
    print(f"wrote {len(new)} variants of {a.id}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--out", default="benchmarks/corpus")
    a.add_argument("--id", required=True)
    a.add_argument("--wav", required=True)
    a.add_argument("--ref", required=True, help="reference transcript (the words actually spoken)")
    a.add_argument("--tag", action="append", default=[], help="key=value, e.g. accent=indian_english (repeatable)")
    a.set_defaults(fn=cmd_add)
    v = sub.add_parser("variants")
    v.add_argument("--out", default="benchmarks/corpus")
    v.add_argument("--id", required=True)
    v.add_argument("--snr", type=float, nargs="*")
    v.add_argument("--speed", type=float, nargs="*")
    v.add_argument("--noise-file", help="real noise (babble/cafe/street); default is white noise")
    v.add_argument("--seed", type=int, default=0)
    v.set_defaults(fn=cmd_variants)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
