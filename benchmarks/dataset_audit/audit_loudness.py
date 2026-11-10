import sys, io, re, json, collections, wave
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from svarah_adapter import rows
N = 0
names, fam = [], collections.Counter()
txt_feat = collections.Counter()
long_rows = []
lv = []
for r in rows(Path("C:/data/svarah/data")):
    p = r["audio_filepath"]["path"]; t = r["text"]; d = r["duration"]
    m = re.match(r"(\d+)_([a-z]\d+)_chunk_(\d+)", p)
    spk = (m.group(1), m.group(2)) if m else None
    fam[spk] += 1
    pass
    txt_feat["upper"] += any(c.isupper() for c in t)
    txt_feat["punct"] += bool(re.search(r"[.,?!;:]", t))
    txt_feat["digits"] += bool(re.search(r"\d", t))
    txt_feat["hyphen"] += "-" in t
    txt_feat["special"] += bool(re.search(r"[^A-Za-z0-9 .,?!'\-:;()\"]", t))
    txt_feat["rows"] += 1
    w = len(t.split()); txt_feat["words"] += w
    if d >= 10:
        long_rows.append((spk, r["primary_language"], d, w))
    x = np.frombuffer(wave.open(io.BytesIO(r["audio_filepath"]["bytes"])).readframes(10**9), np.int16).astype(np.float32) / 32768
    fr = x[: len(x) // 320 * 320].reshape(-1, 320)
    rms = np.sqrt((fr ** 2).mean(1))
    act = rms >= 0.01
    idx = np.nonzero(act)[0]
    lead = idx[0] * 0.02 if len(idx) else d
    trail = (len(rms) - 1 - idx[-1]) * 0.02 if len(idx) else d
    lv.append((d, float(np.percentile(rms, 95)), float(np.percentile(rms, 10)), float(np.abs(x).max()), float((np.abs(x) >= 0.999).mean()), lead, trail, float(act.mean()), spk, r["primary_language"], float(np.sqrt((x**2).mean()))))
print("speaker-key groups", len(fam), "min/med/max rows", min(fam.values()), int(np.median(list(fam.values()))), max(fam.values()))
print({k: v for k, v in txt_feat.items()}, "words/row", txt_feat["words"] / txt_feat["rows"])
L = np.array([(x[2], x[3]) for x in long_rows]); L = np.c_[np.zeros(len(L)), L]
print("long rows", len(long_rows), "speakers", len({a[0] for a in long_rows}), "L1s", len({a[1] for a in long_rows}),
      "words/s median", float(np.median(L[:, 2] / L[:, 0])) if len(L) else None)
print("long per-L1", collections.Counter(a[1] for a in long_rows).most_common())
a = np.array([(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[10]) for x in lv])
def q(i, name, mask=None):
    v = a[:, i] if mask is None else a[mask, i]
    print(f"{name}: p5 {np.percentile(v,5):.4f} p25 {np.percentile(v,25):.4f} med {np.median(v):.4f} p75 {np.percentile(v,75):.4f} p95 {np.percentile(v,95):.4f}")
for name, mask in (("ALL", np.ones(len(a), bool)), ("10-60s", a[:, 0] >= 10)):
    print("==", name, int(mask.sum()))
    q(1, "rms_p95", mask); q(2, "rms_p10 (noise floor est)", mask); q(3, "peak", mask); q(5, "lead_s", mask); q(6, "trail_s", mask); q(7, "frac>=0.01", mask); q(8, "overall rms", mask)
    print("clipping>0.1%:", int((a[mask, 4] > 0.001).sum()), " rms_p95<0.05:", int((a[mask, 1] < 0.05).sum()), " p10>=0.01:", int((a[mask, 2] >= 0.01).sum()), " p10>=0.003:", int((a[mask, 2] >= 0.003).sum()))
    snr = 20 * np.log10(np.maximum(a[mask, 1], 1e-6) / np.maximum(a[mask, 2], 1e-5))
    print("est SNR dB p5/med/p95", np.percentile(snr, [5, 50, 95]).round(1))
