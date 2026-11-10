"""Phase 1/2 of the existing-audio evaluation: inventory + 16 kHz mono PCM16 working copies.

Reads the original files READ-ONLY (never writes next to them). Decodes with PyAV (bundled ffmpeg libs),
resamples to 16 kHz mono, writes one full-length working WAV per source into --out-audio, and a JSON of
measurements. All levels are on the 16 kHz mono decode (float, full scale = 1.0).

  python inventory_existing.py --src C:\\Users\\sriha\\snypar\\stt\\data --out-audio dataset_existing/audio_full \
      --out-json results/existing_audio_inventory.json
"""
import argparse
import hashlib
import json
import re
import wave
from pathlib import Path

import av
import numpy as np

SR = 16000
FRAME = 320  # 20 ms
FIXED_THR = 0.01  # production fixed VAD threshold (UtteranceBuffer default)
BINS = [(0.0, 0.1), (0.1, 0.3), (0.3, 0.6), (0.6, 1.2), (1.2, 3.0), (3.0, 1e9)]


def rid_for(i, name):
    return f"rec{i + 1:02d}"


def decode(path):
    """Return native stream info and 16 kHz mono float32 samples."""
    with av.open(str(path)) as c:
        s = c.streams.audio[0]
        info = dict(container=c.format.name, codec=s.codec_context.name, native_rate=s.rate,
                    native_channels=s.channels, layout=str(s.layout.name), bit_rate=c.bit_rate,
                    container_duration_s=(c.duration / 1e6 if c.duration else None),
                    sample_format=s.format.name if s.format else None,
                    tags={k: v for k, v in c.metadata.items()})
        rs = av.AudioResampler(format="s16", layout="mono", rate=SR)
        chunks = []
        for fr in c.decode(s):
            for o in rs.resample(fr):
                chunks.append(o.to_ndarray().reshape(-1))
        for o in rs.resample(None):
            chunks.append(o.to_ndarray().reshape(-1))
    x = np.concatenate(chunks).astype(np.float32) / 32768.0
    return info, x


def runs(mask):
    """Lengths (in frames) of consecutive True runs, plus start indices."""
    if not len(mask):
        return [], []
    d = np.diff(np.r_[0, mask.astype(np.int8), 0])
    st, en = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
    return (en - st).tolist(), st.tolist()


def pause_stats(rms, thr, edge_trim=True):
    sil = rms < thr
    lens, st = runs(sil)
    n = len(rms)
    inner = []
    for l, s in zip(lens, st):
        if s == 0 or s + l == n:
            continue  # leading / trailing silence is not a pause
        inner.append(l * 0.02)
    inner = np.array(inner) if inner else np.zeros(0)
    hist = {}
    for lo, hi in BINS:
        m = (inner >= lo) & (inner < hi)
        hist[f"{lo:g}-{hi:g}s" if hi < 1e8 else f">={lo:g}s"] = dict(n=int(m.sum()), total_s=round(float(inner[m].sum()), 1))
    return dict(thr=round(float(thr), 5), n_pauses=int(len(inner)), pause_total_h=round(float(inner.sum()) / 3600, 3),
                pause_fraction=round(float(inner.sum() / (n * 0.02)), 3),
                longest_pause_s=round(float(inner.max()), 2) if len(inner) else 0.0,
                median_pause_s=round(float(np.median(inner)), 2) if len(inner) else 0.0, hist=hist,
                n_ge_0p6=int((inner >= 0.6).sum()), n_ge_1p2=int((inner >= 1.2).sum()))


def analyse(x):
    n = len(x) // FRAME * FRAME
    fr = x[:n].reshape(-1, FRAME)
    rms = np.sqrt((fr ** 2).mean(1))
    p = np.percentile
    peak = float(np.abs(x).max())
    p95, p50, p10, p5 = (float(p(rms, q)) for q in (95, 50, 10, 5))
    voiced = rms >= FIXED_THR
    # spectral character of the quietest 5% of frames (noise-floor colour; hum vs broadband)
    q = np.argsort(rms)[: max(50, len(rms) // 20)]
    q = q[rms[q] > 1e-5]
    noise = {}
    if len(q):
        sp = np.abs(np.fft.rfft(fr[q] * np.hanning(FRAME), axis=1)) ** 2
        f = np.fft.rfftfreq(FRAME, 1 / SR)
        e = sp.sum()
        noise = dict(frac_energy_below_300hz=round(float(sp[:, f < 300].sum() / e), 3),
                     frac_energy_above_4khz=round(float(sp[:, f > 4000].sum() / e), 3),
                     spectral_centroid_hz=round(float((sp * f).sum() / e), 0),
                     hum_50_60hz_frac=round(float(sp[:, (f >= 45) & (f <= 65)].sum() / e), 3))
    rel_thr = max(p95 * 10 ** (-35 / 20), 1e-4)  # 35 dB below speech level
    return dict(
        peak=round(peak, 4), peak_dbfs=round(20 * np.log10(max(peak, 1e-9)), 1),
        rms_overall=round(float(np.sqrt((x ** 2).mean())), 4),
        rms_p95=round(p95, 4), rms_median=round(p50, 4), rms_p10_floor=round(p10, 5), rms_p5=round(p5, 5),
        est_snr_db=round(20 * np.log10(max(p95, 1e-6) / max(p10, 1e-6)), 1),
        clipped_samples_ge_0p999=int((np.abs(x) >= 0.999).sum()), clipped_pct=round(float((np.abs(x) >= 0.999).mean() * 100), 5),
        near_clip_ge_0p99_pct=round(float((np.abs(x) >= 0.99).mean() * 100), 5),
        dc_offset=round(float(x.mean()), 6),
        voiced_frac_fixed_thr=round(float(voiced.mean()), 3),
        quiet_voiced_frac=round(float(((rms >= FIXED_THR) & (rms < 0.03)).sum() / max(voiced.sum(), 1)), 3),
        below_thr_frac_with_p95_lt_0p05=bool(p95 < 0.05),
        noise_floor_character=noise,
        pauses_fixed_0p01=pause_stats(rms, FIXED_THR),
        pauses_rel_minus35db=pause_stats(rms, rel_thr),
    ), rms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out-audio", required=True)
    ap.add_argument("--out-json", required=True)
    a = ap.parse_args()
    src, oa = Path(a.src), Path(a.out_audio)
    oa.mkdir(parents=True, exist_ok=True)
    files = sorted([p for p in src.iterdir() if p.is_file() and p.suffix.lower() in (".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".mp4", ".webm")],
                   key=lambda p: p.name.lower())
    out = []
    for i, p in enumerate(files):
        rid = rid_for(i, p.name)
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for b in iter(lambda: fh.read(1 << 20), b""):
                h.update(b)
        info, x = decode(p)
        wavp = oa / f"{rid}.wav"
        with wave.open(str(wavp), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
        m, rms = analyse(x)
        m.update(recording_id=rid, source_filename=p.name, source_path=str(p), source_sha256=h.hexdigest(),
                 file_bytes=p.stat().st_size, decoded_duration_s=round(len(x) / SR, 2), working_wav=str(wavp),
                 **info)
        out.append(m)
        print(f"{rid} {p.name[:50]:50s} {len(x)/SR/60:6.1f} min  peak {m['peak']:.3f}  snr~{m['est_snr_db']} dB  "
              f"pauses>=0.6s {m['pauses_fixed_0p01']['n_ge_0p6']}")
    tot = sum(o["decoded_duration_s"] for o in out)
    Path(a.out_json).write_text(json.dumps(dict(files=out, total_duration_s=round(tot, 1), total_min=round(tot / 60, 1)),
                                           indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"total {tot/60:.1f} min over {len(out)} files")


if __name__ == "__main__":
    main()
