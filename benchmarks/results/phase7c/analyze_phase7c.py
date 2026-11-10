"""Phase 7C analysis (read-only). Compares the new scheduler relay (phase7c_sched_*.jsonl, phase7c_flush_diag_*.jsonl,
phase7c_bench_*.json, phase7c_sys.jsonl) against the Phase 7B unmodified baseline (phase7b calls/flush diag).
Writes phase7c_comparison.json.

Baseline files (Phase 7B, unmodified relay with timing wrapper, same manifests and ws_bench conditions):
  subset12 N=1,2 : phase7b_calls_subset12.jsonl ; split by largest idle gap
  full60 N=2     : phase7b_calls_full_n2.jsonl (+ its analysis json)
  subset12 N=3,4 : phase7b_calls.jsonl (3 splits: warmup / N=3 / N=4)
"""
import json
import statistics as st
import sys
from pathlib import Path

H = Path(__file__).resolve().parent
B = H.parent / "phase7b"


def pct(x, p):
    x = sorted(x)
    return round(x[min(len(x) - 1, int(p / 100 * len(x)))], 4) if x else None


def dist(x):
    return {"n": len(x), "p50": pct(x, 50), "p95": pct(x, 95), "max": round(max(x), 4) if x else None}


def load_jsonl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


# --------------------------------------------------------------- job normalisation
def jobs_from_phase7c(path):
    """-> list of dicts: type, state, t_enq, t_start, t_end, n_samples, deadline, speaker"""
    out = []
    for r in load_jsonl(path):
        if r["kind"] == "job":
            out.append({"type": r["type"], "state": r["state"], "t_enq": r["t_enq"], "t_start": r["t_start"],
                        "t_end": r["t_end"], "n_samples": r["n_samples"], "abandoned": r["abandoned"], "speaker": r["speaker"],
                        "finals_q": r["finals_q"], "partials_q": r["partials_q"]})
    return sorted(out, key=lambda j: j["t_enq"])


def jobs_from_phase7b(path):
    rows = load_jsonl(path)
    calls = {r["id"]: r for r in rows if r["kind"] == "call"}
    for r in rows:
        if r["kind"] == "job":
            calls[r["id"]].update(t_start=r["t_inf_start"], t_end=r["t_inf_end"])
    out = []
    for c in sorted(calls.values(), key=lambda r: r["t_enq"]):
        ran = "t_start" in c
        out.append({"type": c["type"], "t_enq": c["t_enq"], "t_start": c.get("t_start"),
                    "t_end": c.get("t_end", c["t_return"]), "n_samples": c["n_samples"],
                    "state": ("cancelled_running" if c["cancelled"] and ran else
                              "cancelled_queued" if c["cancelled"] else "completed"),
                    "abandoned": c["cancelled"] and ran, "t_return": c["t_return"]})
    return out


def split_by_gaps(jobs, k):
    """Split on the k-1 largest idle gaps between consecutive jobs (by enqueue vs previous return)."""
    gaps, last = [], jobs[0].get("t_return", jobs[0]["t_end"])
    for i, j in enumerate(jobs[1:], 1):
        gaps.append((j["t_enq"] - last, i))
        last = max(last, j.get("t_return", j["t_end"]))
    cuts = sorted(i for _, i in sorted(gaps)[-(k - 1):]) if k > 1 else []
    segs, prev = [], 0
    for c in cuts + [len(jobs)]:
        segs.append(jobs[prev:c]); prev = c
    return segs


def cut_by_finals(jobs, cuts):
    """Cut a chronological job list after the k-th final for each k in cuts (warmup / level boundaries)."""
    segs, prev, nf, ci = [], 0, 0, 0
    for i, j in enumerate(jobs):
        if j["type"] == "final":
            nf += 1
            if ci < len(cuts) and nf == cuts[ci]:
                segs.append(jobs[prev:i + 1]); prev = i + 1; ci += 1
    segs.append(jobs[prev:])
    return segs


def summarize_jobs(L, flush=None):
    d = {"jobs": len(L)}
    for typ in ("final", "partial"):
        T = [j for j in L if j["type"] == typ]
        ran = [j for j in T if j.get("t_start") is not None]
        done = [j for j in ran if j["state"] == "completed"]
        d[typ] = {
            "requested_jobs": len(T), "dispatched": len(ran), "completed": len(done),
            "never_started": len(T) - len(ran),
            "states": {s: sum(1 for j in T if j["state"] == s) for s in sorted({j["state"] for j in T})},
            "queue_wait_s": dist([j["t_start"] - j["t_enq"] for j in done]),
            "inference_s": dist([j["t_end"] - j["t_start"] for j in done]),
            "total_s": dist([j["t_end"] - j["t_enq"] for j in done]),
            "inference_rtf_p50": pct([(j["t_end"] - j["t_start"]) / (j["n_samples"] / 16000) for j in done], 50),
            "busy_s": round(sum(j["t_end"] - j["t_start"] for j in ran), 2),
            "wasted_busy_s_abandoned": round(sum(j["t_end"] - j["t_start"] for j in ran if j.get("abandoned")), 2),
        }
    ran = [j for j in L if j.get("t_start") is not None]
    t0 = min(j["t_enq"] for j in L); t1 = max(j["t_end"] for j in L)
    busy = sum(j["t_end"] - j["t_start"] for j in ran)
    d["wall_s"] = round(t1 - t0, 1)
    d["worker_utilisation"] = round(busy / (t1 - t0), 3)
    d["partial_share_of_busy"] = round(d["partial"]["busy_s"] / busy, 3) if busy else None
    # finals that enqueued while a partial was running (wait behind a partial)
    fin = [j for j in ran if j["type"] == "final" and j["state"] == "completed"]
    part = [j for j in ran if j["type"] == "partial"]
    behind = sum(1 for f in fin if any(p["t_start"] < f["t_start"] and p["t_end"] > f["t_enq"] for p in part))
    d["finals_that_waited_behind_a_partial"] = {"n": behind, "of": len(fin)}
    if flush is not None:
        d["flush_outcomes"] = flush
    return d


def flush_counts(path):
    from collections import Counter
    try:
        R = load_jsonl(path)
        w = min(r["conn_id"] for r in R)   # warmup connection excluded
        return dict(Counter(r["outcome"] for r in R if r["conn_id"] != w))
    except FileNotFoundError:
        return None


def bench_level(path, conc):
    d = json.load(open(path))
    lv = [l for l in d["levels"] if l.get("concurrency") == conc or l.get("n") == conc]
    return lv[0] if lv else None


def sys_summary(path, t_lo=None, t_hi=None):
    try:
        S = load_jsonl(path)
    except FileNotFoundError:
        return None
    if t_lo is not None:
        S = [s for s in S if t_lo <= s["t_mono"] <= t_hi]
    if not S:
        return None
    return {"samples": len(S), "sys_cpu_mean": round(st.mean(s["sys_cpu"] for s in S), 1),
            "sys_cpu_median": round(st.median(s["sys_cpu"] for s in S), 1), "sys_cpu_max": max(s["sys_cpu"] for s in S),
            "relay_cpu_mean_pct_of_core": round(st.mean(s["relay_cpu"] for s in S), 1),
            "free_mb_min": min(s["free_mb"] for s in S), "relay_rss_mb_max": max(s["relay_ws_mb"] for s in S),
            "mhz_median": round(st.median(s["mhz"] for s in S if s["mhz"]), 0)}


def main():
    out = {"baseline": "Phase 7B unmodified relay (timing wrapper only)", "new": "Phase 7C scheduler relay copy", "levels": {}}
    sched = {}
    for tag in ("subset12_n1", "subset12_n2", "subset12_n3", "subset12_n4", "full60_n2"):
        p = H / f"phase7c_sched_{tag}.jsonl"
        if not p.exists():
            continue
        J = jobs_from_phase7c(p)
        # drop the warmup session: split on the largest idle gap when there is one clearly separate run
        wsp = min(j["speaker"] for j in J if j["speaker"] is not None)   # warmup session = first connection
        main_jobs = [j for j in J if j["speaker"] != wsp]
        entry = {"new": summarize_jobs(main_jobs, flush_counts(H / f"phase7c_flush_diag_{tag}.jsonl")),
                 "new_warmup_jobs_excluded": len(J) - len(main_jobs)}
        conc = int(tag.split("_n")[1])
        b = bench_level(H / f"phase7c_bench_{tag}.json", conc)
        if b:
            entry["new_bench"] = {k: b[k] for k in b if k in ("wer", "wer_pct", "finals", "n_finals", "partials_received",
                                                           "final_latency_after_hang_s", "first_partial_s", "ttfw_s",
                                                           "partial_revision_rate", "duplicates", "missing")}
        out["levels"][tag] = entry
    # baselines
    try:
        j = jobs_from_phase7b(B / "phase7b_calls_subset12.jsonl")
        # 7B's own gap split mis-assigned the N=1/N=2 boundary (see report); cut by final counts instead:
        # 4 warmup finals, then 39 finals for the 12-clip N=1 level, remainder is N=2.
        _, s1, s2 = cut_by_finals(j, [4, 43])
        out["levels"].setdefault("subset12_n1", {})["baseline"] = summarize_jobs(s1)
        out["levels"].setdefault("subset12_n2", {})["baseline"] = summarize_jobs(s2)
        j = jobs_from_phase7b(B / "phase7b_calls.jsonl")
        w, s3, s4 = split_by_gaps(j, 3)
        out["levels"].setdefault("subset12_n3", {})["baseline"] = summarize_jobs(s3)
        out["levels"].setdefault("subset12_n4", {})["baseline"] = summarize_jobs(s4)
        j = jobs_from_phase7b(B / "phase7b_calls_full_n2.jsonl")
        out["levels"].setdefault("full60_n2", {})["baseline"] = summarize_jobs(cut_by_finals(j, [4])[1])
    except FileNotFoundError as e:
        out["baseline_error"] = str(e)
    (H / "phase7c_comparison.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for tag, e in out["levels"].items():
        for which in ("baseline", "new"):
            d = e.get(which)
            if not d:
                continue
            f = d["final"]
            print(f"{tag:12s} {which:8s} finals req/disp/done {f['requested_jobs']}/{f['dispatched']}/{f['completed']} "
                  f"states {f['states']} qwait p50/p95/max {f['queue_wait_s']['p50']}/{f['queue_wait_s']['p95']}/{f['queue_wait_s']['max']} "
                  f"total p95 {f['total_s']['p95']} util {d['worker_utilisation']} part_share {d['partial_share_of_busy']} "
                  f"partials req {d['partial']['requested_jobs']} states {d['partial']['states']} flush {d.get('flush_outcomes')}")


if __name__ == "__main__":
    main()
