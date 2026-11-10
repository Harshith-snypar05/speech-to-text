"""Correlate relay flush diagnostics (JSONL from STT_FLUSH_DIAG_FILE) with a ws_bench result.
Read-only on both inputs. Prints / writes a per-clip table showing, for each expected
utterance with no final, which relay flush record (if any) covers its audio and why no
final was produced.

Correlation key: benchmark clips are streamed one per WebSocket connection, so each
relay `conn_id` is one clip. conn_ids appear in connection order; the bench streams
(warmup clips first, then clips in manifest order at concurrency 1). Use --skip-conns
to skip warmup connections. At concurrency > 1 connections interleave: not supported.
Within a connection `audio_received_s` is on the same clock as ws_bench expected_detail
(audio seconds), and `seq` orders the flushes.

Usage: python flush_correlate.py --diag diag.jsonl --bench results/run.json [--skip-conns 1] [--out x.json]
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path


def load_diag(path):
    recs = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    by_conn = defaultdict(list)
    for r in recs:
        if r.get("kind") == "flush":
            by_conn[r["conn_id"]].append(r)
    return {k: sorted(v, key=lambda r: r["seq"]) for k, v in sorted(by_conn.items())}


def correlate(diag_by_conn, clips, skip=0):
    conns = list(diag_by_conn)[skip:]
    out = []
    for i, c in enumerate(clips):
        conn = conns[i] if i < len(conns) else None
        flushes = diag_by_conn.get(conn, [])
        lm = c.get("latency_match") or {}
        unmatched = lm.get("unmatched_expected", [])
        extra = lm.get("extra_finals", [])
        rows = []
        for u in unmatched:
            # flush whose audio position falls at/after this utterance's end and before the next expected start
            cand = [f for f in flushes if f["audio_received_s"] >= u["end_s"] - 0.3]
            f = cand[0] if cand else None
            rows.append({"expected_index": u["expected_index"], "expected_end_s": u["end_s"],
                         "forced_expected": u["forced"],
                         "relay_flush_seq": f["seq"] if f else None,
                         "relay_outcome": f["outcome"] if f else "no_flush_record",
                         "relay_reason": f["reason"] if f else None,
                         "buffer_s": f["buffer_s"] if f else None, "speech_s": f["speech_s"] if f else None,
                         "decode_attempted": f["decode_attempted"] if f else None,
                         "text_empty": f["text_empty"] if f else None,
                         "exception": f["exception"] if f else None})
        out.append({"clip": c["id"], "conn_id": conn, "relay_flushes": len(flushes),
                    "relay_outcomes": [f["outcome"] for f in flushes],
                    "bench_finals": c["finals_received"], "bench_expected": c["utterances_expected"],
                    "unmatched_explained": rows, "extra_finals": extra})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--diag", required=True)
    ap.add_argument("--bench", required=True)
    ap.add_argument("--skip-conns", type=int, default=0)
    ap.add_argument("--out")
    a = ap.parse_args()
    bench = json.loads(Path(a.bench).read_text(encoding="utf-8"))["levels"][0]["clips"]
    res = correlate(load_diag(a.diag), bench, a.skip_conns)
    for r in res:
        if r["unmatched_explained"] or r["extra_finals"] or r["bench_finals"] != r["bench_expected"]:
            print(f"{r['clip']}: conn {r['conn_id']} flushes {r['relay_outcomes']}")
            for u in r["unmatched_explained"]:
                print(f"   expected #{u['expected_index']} end {u['expected_end_s']}: {u['relay_outcome']} ({u['relay_reason']}) "
                      f"buffer {u['buffer_s']}s speech {u['speech_s']}s decode={u['decode_attempted']} empty={u['text_empty']}")
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
