"""Phase 4 offline rescore of the existing Svarah baseline. No ASR, no relay, no audio.
READ-ONLY on results/svarah_wer.json; writes a NEW file results/svarah_phase4_rescore.json.

Reports, side by side and never overwriting the baseline:
  raw WER                  (wer.normalize, the baseline policy)
  number-normalized WER    (Phase 3 policy C)
  compound-normalized WER  (Phase 3 policy D, separate diagnostic)
plus timestamp-matched final-event counts and final latency for the same run.
Normalized WER is diagnostic only: it is not improved recognition accuracy.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from latency_match import match_events  # noqa: E402
from wer import corpus_wer  # noqa: E402
from wer_policies import DISCLAIMER, policy_wer  # noqa: E402

BASELINE = HERE / "results" / "svarah_wer.json"
OUT = HERE / "results" / "svarah_phase4_rescore.json"
HANG = 0.6


def tot(rows):
    c = corpus_wer(rows)
    return {"wer": c["wer"], "ci95": c["ci95"], "ref_words": c["ref_words"],
            "sub": sum(r["sub"] for r in rows), "del": sum(r["del"] for r in rows),
            "ins": sum(r["ins"] for r in rows), "errors": sum(r["errors"] for r in rows)}


def pctl(v, q):
    import numpy as np
    return round(float(np.percentile(v, q)), 3) if v else None


def main():
    lvl = json.loads(BASELINE.read_text(encoding="utf-8"))["levels"][0]
    before = BASELINE.read_bytes()
    per_clip, rows = [], {"raw": [], "number": [], "compound": []}
    lat_end, lat_flush, unmatched, extra = [], [], [], []
    for c in lvl["clips"]:
        s = policy_wer(c["reference"], c["hypothesis"])
        # baseline reproduction guard: raw policy must equal what the baseline stored
        assert (s["raw"]["sub"], s["raw"]["del"], s["raw"]["ins"], s["raw"]["ref_words"]) == \
            (c["sub"], c["del"], c["ins"], c["ref_words"]), c["id"]
        for k in rows:
            rows[k].append(s[k])
        m = match_events(c["expected_detail"], [(t, "", False) for t in c["final_times_s"]], HANG)
        for p in m["pairs"]:
            if p["final_latency_s"] is not None:
                lat_end.append(p["final_latency_s"])
            if p["final_after_flush_s"] is not None:
                lat_flush.append(p["final_after_flush_s"])
        unmatched += [dict(clip=c["id"], **u) for u in m["unmatched_expected"]]
        extra += [dict(clip=c["id"], **e) for e in m["extra_finals"]]
        per_clip.append({"id": c["id"], "wer_raw": s["raw"], "wer_number_normalized": s["number"],
                         "wer_compound_normalized": s["compound"], "match_counts": m["counts"]})
    summary = {k: tot(v) for k, v in rows.items()}
    assert summary["raw"]["errors"] == 376 and summary["raw"]["ins"] == 198, "baseline not reproduced"
    out = {
        "source": "results/svarah_wer.json (read-only; byte-identical after this script)",
        "note": DISCLAIMER,
        "wer_raw": summary["raw"], "wer_number_normalized": summary["number"],
        "wer_compound_normalized": summary["compound"],
        "policies": {"raw": "wer.normalize (baseline)", "number": "Phase 3 policy C", "compound": "Phase 3 policy D (C plus compound join)"},
        "latency_timestamp_matched": {
            "matched_pairs": len(lat_end), "unmatched_expected": unmatched, "extra_finals": extra,
            "final_minus_utterance_end_s": {"n": len(lat_end), "p50": pctl(lat_end, 50), "p95": pctl(lat_end, 95), "max": max(lat_end)},
            "final_minus_flush_reference_s": {"n": len(lat_flush), "p50": pctl(lat_flush, 50), "p95": pctl(lat_flush, 95), "max": max(lat_flush)},
            "ttfw": "not recomputed: baseline did not store partial message times (Phase 3 reconstructed it separately)"},
        "clips": per_clip,
    }
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    assert BASELINE.read_bytes() == before
    for k in ("raw", "number", "compound"):
        w = summary[k]
        print(f"{k:9s} WER {w['wer']*100:.2f}%  [{w['ci95'][0]*100:.1f}-{w['ci95'][1]*100:.1f}]  S{w['sub']} D{w['del']} I{w['ins']}  words {w['ref_words']}")
    print("unmatched expected:", len(unmatched), " extra finals:", len(extra))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
