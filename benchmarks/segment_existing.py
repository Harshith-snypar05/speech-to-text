"""Phase 2: configurable evaluation segments + manifest for the existing recordings.

Input : working WAVs (16 kHz mono PCM16) made by inventory_existing.py from the untouched originals.
Output: dataset_existing/manifest.json (always lists every segment of every requested length) and
        clip WAVs for the lengths named in --materialize only.

Cut policy ("don't cut words"): for a target length L, the next boundary is the middle of the longest
silent run found in [0.8 L, 1.15 L] after the segment start (silent = frame RMS below a per-recording
threshold, run >= --min-gap s). If none, widen to [0.6 L, 1.4 L]. If still none, cut at the lowest-energy
frame in the wide window and flag boundary_quality = "cut_in_speech_likely". Nothing is trimmed or gain-changed.

NOT independent: every segment of one recording shares speaker(s), room and microphone, and segments of
different lengths overlap in time. `independence_group` = recording_id; split/aggregate by it.

Facts left unknown on purpose: speaker_id (null), reference transcript (transcript_missing). language and
accent are the USER's statement (Indian English), not verified per file; recording_condition is unknown.
"""
import argparse
import json
import wave
from pathlib import Path

import numpy as np

SR = 16000
FR = 320  # 20 ms

# Provenance hints. These come from file names / container tags ONLY and are unverified.
SOURCE_HINTS = {
    "rec01": "lecture-style (filename 'Introduction to Operating Systems'); speaker count unknown",
    "rec02": "lecture-style (filename 'Introduction To Computing'); speaker count unknown",
    "rec03": "lecture-style (filename 'Introduction to UNIX System Calls'); speaker count unknown",
    "rec04": "unknown content (filename 'audiotreanscribed'); speaker count unknown",
    "rec05": "web video audio, interview-style title (tag: Asian Boss); speaker count unknown, likely multiple",
    "rec06": "web video audio, single-creator channel tag; speaker count unknown",
    "rec07": "web video audio, single-creator channel tag; speaker count unknown",
}


def load(path):
    with wave.open(str(path)) as w:
        assert w.getframerate() == SR and w.getnchannels() == 1 and w.getsampwidth() == 2
        return np.frombuffer(w.readframes(w.getnframes()), np.int16)


def write(path, pcm):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def frame_rms(pcm):
    n = len(pcm) // FR * FR
    f = pcm[:n].reshape(-1, FR).astype(np.float32) / 32768
    return np.sqrt((f ** 2).mean(1))


def threshold(rms):
    """Per-recording 'silent' threshold: 30 dB under speech level, floored by 3x the noise floor, capped at the
    production fixed threshold 0.01. Used for CUT PLACEMENT only; it is not a VAD ground truth."""
    p95, p10 = np.percentile(rms, 95), np.percentile(rms, 10)
    return float(min(0.01, max(p95 * 10 ** (-30 / 20), 3 * p10, 0.0005)))


def silent_runs(rms, thr, lo_f, hi_f, min_f):
    """Runs of silent frames inside [lo_f, hi_f): returns (start, length) list."""
    seg = rms[lo_f:hi_f] < thr
    d = np.diff(np.r_[0, seg.astype(np.int8), 0])
    st, en = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
    return [(lo_f + s, e - s) for s, e in zip(st, en) if e - s >= min_f]


def plan(rms, total_f, L, min_gap):
    thr = threshold(rms)
    Lf, min_f = int(L / 0.02), int(min_gap / 0.02)
    segs, s = [], 0
    while s < total_f:
        if total_f - s <= int(1.15 * Lf):
            segs.append((s, total_f, "end_of_recording")); break
        cut, q = None, None
        for lo, hi in ((0.8, 1.15), (0.6, 1.4)):
            runs = silent_runs(rms, thr, s + int(lo * Lf), min(s + int(hi * Lf), total_f), min_f)
            if runs:
                st, ln = max(runs, key=lambda r: r[1])
                cut, q = st + ln // 2, "pause_cut"
                break
        if cut is None:
            lo, hi = s + int(0.6 * Lf), min(s + int(1.4 * Lf), total_f)
            cut, q = lo + int(np.argmin(rms[lo:hi])), "cut_in_speech_likely"
        segs.append((s, cut, q)); s = cut
    return segs, thr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio-dir", default="dataset_existing/audio_full")
    ap.add_argument("--inventory", default="results/existing_audio_inventory.json")
    ap.add_argument("--out-dir", default="dataset_existing")
    ap.add_argument("--lengths", default="10,20,30,60")
    ap.add_argument("--materialize", default="30", help="comma list of lengths to write as WAV clips ('' = none)")
    ap.add_argument("--min-gap", type=float, default=0.2, help="min silent run (s) usable as a cut point")
    ap.add_argument("--language", default="en")
    ap.add_argument("--accent", default="indian_english")
    a = ap.parse_args()
    out = Path(a.out_dir)
    inv = {f["recording_id"]: f for f in json.loads(Path(a.inventory).read_text(encoding="utf-8"))["files"]}
    lengths = [int(x) for x in a.lengths.split(",")]
    mat = {int(x) for x in a.materialize.split(",") if x}
    clips, stats = [], {}
    for rid, f in sorted(inv.items()):
        pcm = load(f["working_wav"])
        rms = frame_rms(pcm)
        for L in lengths:
            segs, thr = plan(rms, len(rms), L, a.min_gap)
            q = {}
            for k, (s, e, quality) in enumerate(segs):
                q[quality] = q.get(quality, 0) + 1
                cid = f"{rid}_L{L:02d}_{k:04d}"
                path = None
                if L in mat:
                    d = out / "clips" / f"L{L:02d}"
                    d.mkdir(parents=True, exist_ok=True)
                    path = d / f"{cid}.wav"
                    write(path, pcm[s * FR:e * FR])
                seg_rms = rms[s:e]
                clips.append(dict(
                    recording_id=rid, source_filename=f["source_filename"], clip_id=cid, segment_length_target_s=L,
                    start_time=round(s * 0.02, 2), end_time=round(e * 0.02, 2), duration=round((e - s) * 0.02, 2),
                    sample_rate=SR, channels=1, speaker_id=None, speaker_status="unknown",
                    language=a.language, language_status="user_stated_unverified",
                    accent=a.accent, accent_status="user_stated_unverified",
                    recording_condition="unknown", source_hint=SOURCE_HINTS.get(rid),
                    transcript_path=None, transcript_status="transcript_missing",
                    audio_path=str(path) if path else None, materialized=bool(path),
                    boundary_quality=quality, independence_group=rid,
                    seg_rms_p95=round(float(np.percentile(seg_rms, 95)), 4),
                    seg_voiced_frac_fixed_0p01=round(float((seg_rms >= 0.01).mean()), 3),
                    processing=["decode source (PyAV) -> mono downmix -> resample 16 kHz -> PCM16 working WAV (full length)",
                                f"slice frames [{s * FR}:{e * FR}] of working WAV (no gain, no filtering)"]))
            stats.setdefault(rid, {})[L] = dict(n=len(segs), cut_threshold_rms=round(thr, 5), boundary_quality=q)
    sources = [dict(recording_id=r, source_filename=f["source_filename"], source_path=f["source_path"],
                    source_sha256=f["source_sha256"], working_wav=f["working_wav"], duration_s=f["decoded_duration_s"],
                    native=dict(codec=f["codec"], rate=f["native_rate"], channels=f["native_channels"]),
                    processing=["PyAV decode", "downmix to mono", "resample to 16000 Hz", "PCM16 WAV"])
               for r, f in sorted(inv.items())]
    man = dict(
        _note="Original audio untouched. transcript_missing for ALL clips: no verified references exist, so no WER. "
              "speaker_id unknown everywhere. Segments of one recording are not independent samples.",
        policy=dict(lengths=lengths, materialized=sorted(mat), min_gap_s=a.min_gap, cut="see segment_existing.py docstring"),
        sources=sources, segment_stats=stats, clips=clips)
    (out / "manifest.json").write_text(json.dumps(man, indent=1, ensure_ascii=False), encoding="utf-8")
    for rid, d in stats.items():
        print(rid, {L: (v["n"], v["boundary_quality"]) for L, v in d.items()})
    print(f"{len(clips)} manifest entries; materialized lengths {sorted(mat)}")


if __name__ == "__main__":
    main()
