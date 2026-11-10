"""Phase 7B analysis of phase7b_calls.jsonl (+ flush diag). Read-only; writes phase7b_analysis.json."""
import json, statistics as st
from pathlib import Path

H = Path(__file__).resolve().parent
rows = [json.loads(l) for l in (H / "phase7b_calls.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
calls = {r["id"]: r for r in rows if r["kind"] == "call"}
for r in rows:
    if r["kind"] == "job":
        calls[r["id"]].update(t_inf_start=r["t_inf_start"], t_inf_end=r["t_inf_end"])
C = sorted(calls.values(), key=lambda r: r["t_enq"])
# level split: largest idle gap between consecutive calls' (enq, return)
gaps = []
last = C[0]["t_return"]
for i, r in enumerate(C[1:], 1):
    gaps.append((r["t_enq"] - last, i)); last = max(last, r["t_return"])
g, idx = max(gaps)
levels = {"N=1": C[:idx], "N=2": C[idx:]}


def pct(x, p):
    x = sorted(x)
    return round(x[min(len(x) - 1, int(p / 100 * len(x)))], 4) if x else None


out = {"split_gap_s": round(g, 2)}
for name, L in levels.items():
    d = {"calls": len(L)}
    for typ in ("final", "partial"):
        T = [r for r in L if r["type"] == typ]
        ran = [r for r in T if "t_inf_start" in r]
        done = [r for r in T if not r["cancelled"] and "t_inf_start" in r]
        q = [r["t_inf_start"] - r["t_enq"] for r in done]
        inf = [r["t_inf_end"] - r["t_inf_start"] for r in done]
        tot = [r["t_return"] - r["t_enq"] for r in done]
        aud = [r["n_samples"] / 16000 for r in done]
        d[typ] = {
            "calls": len(T), "cancelled": sum(r["cancelled"] for r in T),
            "never_started": sum(1 for r in T if "t_inf_start" not in r),
            "completed": len(done),
            "queue_wait_s": {"p50": pct(q, 50), "p95": pct(q, 95), "max": round(max(q), 4) if q else None},
            "inference_s": {"p50": pct(inf, 50), "p95": pct(inf, 95), "max": round(max(inf), 4) if inf else None},
            "total_s": {"p50": pct(tot, 50), "p95": pct(tot, 95)},
            "audio_s_mean": round(st.mean(aud), 2) if aud else None,
            "inference_rtf_p50": pct([i / a for i, a in zip(inf, aud)], 50),
            "worker_busy_s": round(sum(r["t_inf_end"] - r["t_inf_start"] for r in ran), 2),
            "wasted_busy_s_cancelled": round(sum(r["t_inf_end"] - r["t_inf_start"] for r in T if r["cancelled"] and "t_inf_start" in r), 2),
        }
    t0 = min(r["t_enq"] for r in L); t1 = max(r.get("t_inf_end", r["t_return"]) for r in L)
    busy = sum(r["t_inf_end"] - r["t_inf_start"] for r in L if "t_inf_start" in r)
    d["wall_s"] = round(t1 - t0, 1)
    d["worker_utilisation"] = round(busy / (t1 - t0), 3)
    d["partial_share_of_busy"] = round(d["partial"]["worker_busy_s"] / busy, 3) if busy else None
    d["max_active_calls"] = max(r["active_calls_at_enq"] for r in L) + 1
    # final waiting behind a partial: was a partial job running when this final was enqueued?
    fin = [r for r in L if r["type"] == "final" and "t_inf_start" in r and not r["cancelled"]]
    part = [r for r in L if r["type"] == "partial" and "t_inf_start" in r]
    behind = 0; wait_behind = []
    for f in fin:
        blockers = [p for p in part if p["t_inf_start"] < f["t_inf_start"] and p["t_inf_end"] > f["t_enq"]]
        if blockers:
            behind += 1
            wait_behind.append(sum(min(p["t_inf_end"], f["t_inf_start"]) - max(p["t_inf_start"], f["t_enq"]) for p in blockers))
    d["finals_that_waited_behind_partials"] = {"n": behind, "of": len(fin), "mean_wait_s_attributable_to_partials": round(st.mean(wait_behind), 3) if wait_behind else 0}
    out[name] = d
(H / "phase7b_analysis.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps(out, indent=1))
