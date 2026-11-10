"""Phase 7 diagnostics summariser (read-only; touches no production code).

Reads phase7_flush_diag.jsonl (written by the Phase 7 relay on :8769) and
prints the area-A / area-E numbers the reports need:

  * flush outcomes and reasons -- how many empties were dropped, and of how
    many distinct buffers
  * decode_s / buffer_s / RTF, split between the concurrency-1 and
    concurrency-2 levels of the benchmark run
  * queue wait = decode_s(level N=2) - decode_s(level N=1). decode_s is
    timed around wait_for(transcribe_final), so it already contains lock
    wait; model work does not change between levels, so the difference is
    serialization cost.

Level split: ws_bench runs levels sequentially, so there is one unusually
large wall-clock gap between them. The script splits on the largest gap
when it is >= MIN_LEVEL_GAP_S and says so; otherwise it reports one level.

Usage:  python summarize_phase7.py [path/to/phase7_flush_diag.jsonl]
"""
import json
import sys
from collections import Counter
from pathlib import Path

MIN_LEVEL_GAP_S = 3.0

HERE = Path(__file__).resolve().parent


def pct(values, q):
    values = sorted(values)
    if not values:
        return None
    i = min(int(round(q / 100 * (len(values) - 1))), len(values) - 1)
    return values[i]


def dist(name, values):
    if not values:
        return f"{name:16s} n=0"
    return (f"{name:16s} n={len(values):3d} p50={pct(values, 50):.3f} "
            f"p95={pct(values, 95):.3f} max={max(values):.3f} "
            f"mean={sum(values) / len(values):.3f}")


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "phase7_flush_diag.jsonl"
    recs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if not recs:
        print("no records")
        return

    print(f"== {path.name}: {len(recs)} flush records, "
          f"conn_id {min(r['conn_id'] for r in recs)}..{max(r['conn_id'] for r in recs)}")
    print("outcomes:", dict(Counter(r["outcome"] for r in recs)))
    print("reasons :", dict(Counter(r.get("reason") for r in recs)))

    decoded = [r for r in recs if r.get("decode_attempted") and r.get("decode_s") is not None]
    empties = [r for r in recs if r["outcome"] == "dropped_empty_text"]
    distinct = {(r["buffer_s"], r["speech_s"]) for r in empties}
    print(f"decoded={len(decoded)}  empty_drops={len(empties)}  "
          f"distinct_empty_buffers={len(distinct)}")
    for buffer_s, speech_s in sorted(distinct):
        print(f"   buffer_s={buffer_s} speech_s={speech_s}  "
              f"x{sum(1 for r in empties if (r['buffer_s'], r['speech_s']) == (buffer_s, speech_s))}")

    # ---- level split on the largest wall-clock gap
    recs_sorted = sorted(recs, key=lambda r: r["ts_wall"])
    gaps = [(recs_sorted[i + 1]["ts_wall"] - recs_sorted[i]["ts_wall"], i)
            for i in range(len(recs_sorted) - 1)]
    biggest, at = max(gaps)
    if biggest >= MIN_LEVEL_GAP_S:
        levels = [recs_sorted[:at + 1], recs_sorted[at + 1:]]
        print(f"\nlevel split: largest gap {biggest:.1f}s at record {at + 1} "
              f"-> {len(levels[0])} + {len(levels[1])} records")
    else:
        levels = [recs_sorted]
        print(f"\nno level gap >= {MIN_LEVEL_GAP_S}s (largest {biggest:.1f}s) -> single level")

    for i, level in enumerate(levels, 1):
        dec = [r for r in level if r.get("decode_attempted") and r.get("decode_s") is not None]
        # A timeout record's decode_s is the 10 s wait_for cap, not model
        # work -- mixing them in would make the level look slow rather
        # than queued, so they are split out.
        timed_out = [r for r in dec if r["outcome"] == "dropped_timeout"]
        done = [r for r in dec if r["outcome"] != "dropped_timeout"]
        print(f"\n-- segment {i} ({len(level)} flushes, {len(dec)} decodes, "
              f"{len(timed_out)} timed out at the final-flush timeout)")
        print("  completed decodes only:")
        print(dist("  decode_s", [r["decode_s"] for r in done]))
        print(dist("  buffer_s", [r["buffer_s"] for r in done]))
        print(dist("  RTF", [r["decode_s"] / r["buffer_s"] for r in done if r.get("buffer_s")]))
        if timed_out:
            print(dist("  timeout_s", [r["decode_s"] for r in timed_out]))
        print("  outcomes:", dict(Counter(r["outcome"] for r in level)))

    if len(levels) == 2:
        def p50_completed(level):
            v = [r["decode_s"] for r in level
                 if r.get("decode_s") is not None and r["outcome"] != "dropped_timeout"]
            return pct(v, 50) if v else None
        a, b = p50_completed(levels[0]), p50_completed(levels[1])
        if a is not None and b is not None:
            print(f"\ncompleted-decode p50: segment1 {a:.3f}s -> segment2 {b:.3f}s "
                  f"({b - a:+.3f}s); segment 1 = concurrency 1, segment 2 = concurrency 2. "
                  f"Model work is unchanged between levels, so the difference is lock wait.")
        t2 = sum(1 for r in levels[1] if r["outcome"] == "dropped_timeout")
        t1 = sum(1 for r in levels[0] if r["outcome"] == "dropped_timeout")
        print(f"final-flush timeouts: segment1 {t1}, segment2 {t2} "
              f"(timeout = STT_FINAL_FLUSH_TIMEOUT_SECONDS, utterance abandoned)")


if __name__ == "__main__":
    main()
