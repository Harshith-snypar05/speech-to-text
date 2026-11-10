"""Ingest real recordings into a benchmark corpus (manifest.json + wav/*.wav) that
ws_bench.py, the VAD experiment and selftest tooling read unchanged.

Input folder layout (one recording = files sharing a stem):

    raw/
      priya_kubernetes_01.wav        audio (16/24/32-bit PCM WAV natively;
                                     mp3/m4a/flac/ogg need ffmpeg on PATH)
      priya_kubernetes_01.txt        EXACT reference transcript (required)
      priya_kubernetes_01.json       optional: {"tags": {"accent": "indian_english", ...}, "notes": "..."}
      defaults.json                  optional: {"tags": {...}} applied to every clip (sidecar wins)

Usage:
    python ingest_corpus.py raw --out corpus_real [--tag device=laptop_mic] [--dry-run]
                            [--replace] [--min-s 3] [--max-s 120]

Recommended tags (free-form, ws_bench reports WER/latency per tag value):
    accent=indian_english|us|uk|..., domain=technical|casual|numbers, speaker=<id>,
    level=normal|quiet|loud, noise=quiet_room|fan|cafe|street|keyboard, device=<mic>

Each clip gets meta{} (source file, sha256, original format, duration, peak, clipping %,
estimated speech/noise level and rough SNR) so later analysis can slice by recording
condition. Nothing is modified in the source folder. Output wavs are 16 kHz mono int16
(the relay wire format); NO gain normalisation is applied, because quiet speech is exactly
what the VAD experiments need to see.

Exit code 0 = all clips ingested (warnings allowed), 1 = at least one clip rejected.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audio_utils import SAMPLE_RATE, resample, rms_frames, write_wav  # noqa: E402

AUDIO_EXT = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".wma", ".webm", ".mp4"}


def read_pcm_wav(path: Path):
    """Any-PCM-width WAV -> (float32 mono at native rate, rate, channels, bits)."""
    with wave.open(str(path), "rb") as f:
        rate, ch, width, n = f.getframerate(), f.getnchannels(), f.getsampwidth(), f.getnframes()
        raw = f.readframes(n)
    if width == 1:
        x = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
    elif width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        v = np.where(v & 0x800000, v - 0x1000000, v)
        x = v.astype(np.float32) / 8388608.0
    elif width == 4:
        x = np.frombuffer(raw, np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"unsupported sample width {width * 8} bit")
    if ch > 1:
        x = x[: len(x) // ch * ch].reshape(-1, ch).mean(axis=1)
    return x, rate, ch, width * 8


def load_audio(path: Path):
    if path.suffix.lower() == ".wav":
        try:
            return read_pcm_wav(path)
        except wave.Error as e:  # e.g. float WAV / WAVE_FORMAT_EXTENSIBLE
            if shutil.which("ffmpeg") is None:
                raise ValueError(f"{path.name}: stdlib cannot read this WAV ({e}); install ffmpeg or re-export as PCM 16-bit")
    if shutil.which("ffmpeg") is None:
        raise ValueError(f"{path.name}: {path.suffix} needs ffmpeg on PATH (not found). "
                         f"Convert to PCM WAV first, e.g. `ffmpeg -i in{path.suffix} -ac 1 -ar 16000 out.wav`")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "x.wav"
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-ac", "1", "-ar", str(SAMPLE_RATE),
                            "-c:a", "pcm_s16le", str(tmp)], capture_output=True, text=True)
        if r.returncode != 0:
            raise ValueError(f"{path.name}: ffmpeg failed: {r.stderr.strip()[:200]}")
        x, rate, _, _ = read_pcm_wav(tmp)
    return x, rate, -1, -1


def quality(x: np.ndarray) -> dict:
    fr = rms_frames(x, 0.02)
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    speech = float(np.percentile(fr, 95)) if len(fr) else 0.0
    noise = float(np.percentile(fr, 10)) if len(fr) else 0.0
    return dict(
        duration_s=round(len(x) / SAMPLE_RATE, 2),
        peak=round(peak, 4),
        clipping_pct=round(float(np.mean(np.abs(x) >= 0.999)) * 100, 4),
        dc_offset=round(float(np.mean(x)), 5),
        speech_rms_p95=round(speech, 4),
        noise_rms_p10=round(noise, 5),
        est_snr_db=round(20 * np.log10(max(speech, 1e-9) / max(noise, 1e-5)), 1),
        frac_above_0p01=round(float(np.mean(fr >= 0.01)), 3),
    )


def normalise_ref(s: str) -> str:
    return " ".join(s.replace("﻿", "").split())


def check(q: dict, ref: str, a) -> tuple[list, list]:
    warn, err = [], []
    if q["duration_s"] < a.min_s:
        warn.append(f"short ({q['duration_s']}s < {a.min_s}s)")
    if q["duration_s"] > a.max_s:
        warn.append(f"long ({q['duration_s']}s > {a.max_s}s)")
    if q["peak"] < 0.005:
        err.append("essentially silent (peak < 0.005)")
    elif q["peak"] < 0.05:
        warn.append(f"very quiet (peak {q['peak']}): fine for quiet-speech tests, tag level=quiet")
    if q["clipping_pct"] > 0.1:
        warn.append(f"clipping {q['clipping_pct']}% of samples")
    if abs(q["dc_offset"]) > 0.02:
        warn.append(f"DC offset {q['dc_offset']}")
    if q["frac_above_0p01"] < 0.15:
        warn.append(f"little energy above the VAD threshold ({q['frac_above_0p01']:.0%} of frames)")
    words = len(ref.split())
    wps = words / max(q["duration_s"], 1e-3)
    if not ref:
        err.append("empty reference")
    elif wps > 6.0 or (q["duration_s"] > 5 and wps < 0.4):
        warn.append(f"reference/audio length mismatch? {words} words in {q['duration_s']}s ({wps:.1f} w/s)")
    return warn, err


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="folder of recordings + same-stem .txt references")
    ap.add_argument("--out", required=True, help="corpus dir (created / extended): wav/ + manifest.json")
    ap.add_argument("--tag", action="append", default=[], metavar="K=V", help="tag applied to every clip (repeatable)")
    ap.add_argument("--min-s", type=float, default=3.0)
    ap.add_argument("--max-s", type=float, default=120.0)
    ap.add_argument("--replace", action="store_true", help="overwrite clips whose id already exists")
    ap.add_argument("--dry-run", action="store_true", help="validate and report only; write nothing")
    ap.add_argument("--strict", action="store_true", help="treat warnings as rejections")
    a = ap.parse_args()

    src, out = Path(a.src), Path(a.out)
    if not src.is_dir():
        sys.exit(f"source folder not found: {src}")
    cli_tags = {}
    for t in a.tag:
        if "=" not in t:
            sys.exit(f"bad --tag {t!r}, want K=V")
        k, v = t.split("=", 1)
        cli_tags[k] = v
    defaults = {}
    if (src / "defaults.json").exists():
        defaults = json.loads((src / "defaults.json").read_text(encoding="utf-8")).get("tags", {})

    man_path = out / "manifest.json"
    manifest = json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else {"clips": []}
    existing = {c["id"]: i for i, c in enumerate(manifest["clips"])}

    files = sorted(p for p in src.iterdir() if p.suffix.lower() in AUDIO_EXT)
    if not files:
        sys.exit(f"no audio files ({', '.join(sorted(AUDIO_EXT))}) in {src}")
    seen, rejected, added = set(), 0, 0
    print(f"{'clip':32s} {'dur':>6s} {'peak':>6s} {'snr~':>6s}  status")
    for p in files:
        cid = p.stem
        status, notes = "OK", []
        try:
            if cid in seen:
                raise ValueError("duplicate stem (two audio files with the same name)")
            seen.add(cid)
            ref_path = p.with_suffix(".txt")
            if not ref_path.exists():
                raise ValueError(f"missing reference {ref_path.name}")
            ref = normalise_ref(ref_path.read_text(encoding="utf-8-sig"))
            x, rate, ch, bits = load_audio(p)
            if len(x) == 0:
                raise ValueError("empty audio")
            x16 = resample(x, rate, SAMPLE_RATE).astype(np.float32)
            q = quality(x16)
            warn, err = check(q, ref, a)
            if a.strict and warn:
                err += [f"(strict) {w}" for w in warn]
            if err:
                raise ValueError("; ".join(err))
            if cid in existing and not a.replace:
                raise ValueError("id already in manifest (use --replace)")
            side = {}
            if p.with_suffix(".json").exists():
                side = json.loads(p.with_suffix(".json").read_text(encoding="utf-8"))
            tags = {**defaults, **cli_tags, **side.get("tags", {})}
            clip = {"id": cid, "wav": f"wav/{cid}.wav", "reference": ref, "tags": tags,
                    "meta": {"source": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                             "orig_rate": rate, "orig_channels": ch, "orig_bits": bits, **q,
                             **({"notes": side["notes"]} if "notes" in side else {})}}
            if not a.dry_run:
                (out / "wav").mkdir(parents=True, exist_ok=True)
                write_wav(out / "wav" / f"{cid}.wav", x16)
                if cid in existing:
                    manifest["clips"][existing[cid]] = clip
                else:
                    manifest["clips"].append(clip)
                    existing[cid] = len(manifest["clips"]) - 1
            added += 1
            if warn:
                status, notes = "WARN", warn
            print(f"{cid:32s} {q['duration_s']:6.1f} {q['peak']:6.3f} {q['est_snr_db']:6.1f}  {status}")
            for w in notes:
                print(f"    - {w}")
        except Exception as e:  # noqa: BLE001 - report per-clip, keep going
            rejected += 1
            print(f"{cid:32s} {'':>6s} {'':>6s} {'':>6s}  REJECT: {e}")
    if not a.dry_run and added:
        out.mkdir(parents=True, exist_ok=True)
        man_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    tag_counts = {}
    for c in manifest["clips"]:
        for k, v in c.get("tags", {}).items():
            tag_counts.setdefault(k, {}).setdefault(v, 0)
            tag_counts[k][v] += 1
    total = sum(c["meta"]["duration_s"] for c in manifest["clips"] if "meta" in c)
    print(f"\n{'(dry run) ' if a.dry_run else ''}ingested {added}, rejected {rejected}; "
          f"manifest has {len(manifest['clips'])} clips, {total / 60:.1f} min of audio")
    for k, d in sorted(tag_counts.items()):
        print(f"  {k}: " + ", ".join(f"{v}={n}" for v, n in sorted(d.items())))
    if not a.dry_run:
        print(f"next: python ws_bench.py --manifest {man_path} --out results/real.json")
    sys.exit(1 if rejected else 0)


if __name__ == "__main__":
    main()
