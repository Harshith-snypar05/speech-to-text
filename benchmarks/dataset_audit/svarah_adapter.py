"""Isolated adapter: AI4Bharat Svarah (HF parquet) -> folder that benchmarks/ingest_corpus.py reads.

Svarah is GATED on Hugging Face (accept the terms while logged in, then `huggingface-cli login`
or set HF_TOKEN). This script never downloads anything itself and never writes into the dataset
folder. It reads local parquet files only.

  inspect : measure what the paper/card do not state: real container format, sample rate,
            channels, bit depth, duration histogram, transcript-marker census, how many rows
            fall in a duration window. Writes JSON. Run this FIRST.
  export  : write <out>/<id>.wav (original bytes untouched) + <id>.txt (reference) + <id>.json
            (tags from metadata) for ingest_corpus.py. Nothing is invented: a row without
            text is skipped and counted.

Reference handling: Svarah follows Switchboard-style transcription conventions, so references may
contain markers such as [laughter] or {word}. wer.py would turn those into spurious words.
With --strip-markers behaviour (default) bracketed [..] / {..} / <..> spans are removed and the
ORIGINAL text is kept in the sidecar "notes" so the change is auditable. Use --keep-markers to
export text verbatim. Run `inspect` first and decide from the marker census.

Usage:
  python svarah_adapter.py inspect <parquet_dir> --out audit_measured.json
  python svarah_adapter.py export  <parquet_dir> --out <raw_dir> --min-dur 10 --max-dur 60 --limit 40
  python ../ingest_corpus.py <raw_dir> --out ../corpus_svarah --tag corpus=svarah
"""
import argparse
import collections
import io
import json
import re
import sys
import wave
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

MARKER = re.compile(r"\[[^\]]*\]|\{[^}]*\}|<[^>]*>")
TAG_COLS = {  # parquet column -> manifest tag
    "gender": "gender", "age-group": "age_group", "primary_language": "l1",
    "native_place_state": "state", "native_place_district": "district",
    "highest_qualification": "qualification", "job_category": "job", "occupation_domain": "domain",
}


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_") or "na"


def rows(pdir: Path, batch=64):
    files = sorted(pdir.glob("**/*.parquet"))
    if not files:
        sys.exit(f"no .parquet under {pdir}")
    n = 0
    for f in files:
        for b in pq.ParquetFile(f).iter_batches(batch_size=batch):
            for r in b.to_pylist():
                r["_file"], r["_row"] = f.name, n
                n += 1
                yield r


def wav_info(raw: bytes):
    if raw[:4] != b"RIFF":
        return None
    try:
        with wave.open(io.BytesIO(raw)) as w:
            return dict(rate=w.getframerate(), ch=w.getnchannels(), bits=w.getsampwidth() * 8,
                        dur=w.getnframes() / w.getframerate())
    except wave.Error:
        return dict(rate=None, ch=None, bits=None, dur=None, nonpcm=True)


def clean(text, strip):
    t = MARKER.sub(" ", text) if strip else text
    return " ".join(t.split())


def cmd_inspect(a):
    fmt, rate, ch, bits = (collections.Counter() for _ in range(4))
    durs, mism, empty, markers = [], 0, 0, collections.Counter()
    meta = {k: collections.Counter() for k in TAG_COLS}
    proxy = collections.Counter()
    pathpat = collections.Counter()
    n = 0
    for r in rows(Path(a.src)):
        n += 1
        au = r.get("audio_filepath") or {}
        raw, path = au.get("bytes"), au.get("path") or ""
        info = wav_info(raw) if raw else None
        fmt["wav" if info else ("other" if raw else "no_bytes")] += 1
        if info and info.get("rate"):
            rate[info["rate"]] += 1
            ch[info["ch"]] += 1
            bits[info["bits"]] += 1
            if abs(info["dur"] - float(r.get("duration") or 0)) > 0.1:
                mism += 1
        durs.append(float(r.get("duration") or 0))
        if not (r.get("text") or "").strip():
            empty += 1
        for m in MARKER.findall(r.get("text") or ""):
            markers[m.lower()] += 1
        for k in TAG_COLS:
            meta[k][r.get(k)] += 1
        proxy[tuple(r.get(k) for k in TAG_COLS)] += 1
        pathpat[re.sub(r"\d+", "#", Path(path).name)] += 1
    d = np.array(durs)
    out = dict(rows=n, formats=dict(fmt), sample_rates=dict(rate), channels=dict(ch), bit_depths=dict(bits),
               duration=dict(total_h=round(float(d.sum()) / 3600, 3), mean=round(float(d.mean()), 2),
                             median=round(float(np.median(d)), 2),
                             pct={p: round(float(np.percentile(d, p)), 2) for p in (5, 25, 75, 90, 95, 99)},
                             max=round(float(d.max()), 2),
                             n_ge_10=int((d >= 10).sum()), n_10_60=int(((d >= 10) & (d <= 60)).sum()),
                             n_ge_5=int((d >= 5).sum()), n_lt_3=int((d < 3).sum())),
               header_vs_metadata_duration_mismatch=mism, empty_text=empty,
               marker_census_top30=markers.most_common(30),
               audio_filename_patterns_top10=pathpat.most_common(10),
               metadata_distinct={k: len(v) for k, v in meta.items()},
               metadata_counts={k: dict(v.most_common(40)) for k, v in meta.items()},
               proxy_speaker_groups=len(proxy),
               note="No speaker-id column exists in the HF schema; proxy_speaker_groups is the number of distinct "
                    "metadata tuples, NOT a verified speaker count.")
    Path(a.out).write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("rows", "formats", "sample_rates", "channels", "bit_depths", "duration")}, indent=1))


def cmd_export(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cand = []
    skipped = collections.Counter()
    for r in rows(Path(a.src)):
        au = r.get("audio_filepath") or {}
        raw = au.get("bytes")
        dur = float(r.get("duration") or 0)
        if not raw or raw[:4] != b"RIFF":
            skipped["not_wav_or_missing"] += 1
            continue
        if not (r.get("text") or "").strip():
            skipped["no_reference"] += 1
            continue
        if not (a.min_dur <= dur <= a.max_dur):
            skipped["outside_duration_window"] += 1
            continue
        cand.append((r, raw))
    # deterministic round-robin over L1 so one language cannot dominate the sample
    rng = np.random.default_rng(a.seed)
    by = collections.defaultdict(list)
    for c in cand:
        by[c[0].get("primary_language")].append(c)
    for v in by.values():
        rng.shuffle(v)
    picked = []
    while any(by.values()) and (not a.limit or len(picked) < a.limit):
        for k in sorted(by, key=str):
            if by[k] and (not a.limit or len(picked) < a.limit):
                picked.append(by[k].pop())
    for r, raw in picked:
        stem = Path((r.get("audio_filepath") or {}).get("path") or f"row{r['_row']}").stem
        cid = f"svarah_{_slug(r.get('primary_language'))}_{r['_row']:05d}_{_slug(stem)[:24]}"
        (out / f"{cid}.wav").write_bytes(raw)
        orig = r["text"]
        ref = clean(orig, not a.keep_markers)
        if not ref:
            (out / f"{cid}.wav").unlink()
            skipped["empty_after_marker_strip"] += 1
            continue
        (out / f"{cid}.txt").write_text(ref, encoding="utf-8")
        tags = {t: str(r.get(k)) for k, t in TAG_COLS.items() if r.get(k) is not None}
        tags.update(accent="indian_english", source="svarah")
        notes = {"svarah_text_original": orig, "svarah_file": r["_file"], "svarah_row": r["_row"]}
        (out / f"{cid}.json").write_text(
            json.dumps({"tags": tags, "notes": json.dumps(notes, ensure_ascii=False)}, ensure_ascii=False),
            encoding="utf-8")
    print(f"exported {len(list(out.glob('*.wav')))} of {len(cand)} eligible; skipped {dict(skipped)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    i = sp.add_parser("inspect")
    i.add_argument("src")
    i.add_argument("--out", required=True)
    e = sp.add_parser("export")
    e.add_argument("src")
    e.add_argument("--out", required=True)
    e.add_argument("--min-dur", type=float, default=0.0)
    e.add_argument("--max-dur", type=float, default=1e9)
    e.add_argument("--limit", type=int, default=0)
    e.add_argument("--seed", type=int, default=0)
    e.add_argument("--keep-markers", action="store_true")
    a = ap.parse_args()
    {"inspect": cmd_inspect, "export": cmd_export}[a.cmd](a)


if __name__ == "__main__":
    main()
