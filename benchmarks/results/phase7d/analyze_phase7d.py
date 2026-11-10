"""Phase 7D analysis: scheduler/inference/latency from phase7d_sched.jsonl + flush diag, system from phase7d_sys.jsonl,
over a wall-clock window. Usage: analyze_phase7d.py T_START_WALL T_END_WALL [label]"""
import json, statistics as st, sys
from collections import Counter
from pathlib import Path
H = Path(__file__).resolve().parent
def jl(p): return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
def pct(x,p):
    x=sorted(x); return round(x[min(len(x)-1,int(p/100*len(x)))],3) if x else None
t0,t1=float(sys.argv[1]),float(sys.argv[2]); label=sys.argv[3] if len(sys.argv)>3 else "run"
S=[s for s in jl(H/"phase7d_sys.jsonl") if t0<=s["t_wall"]<=t1]
J=[j for j in jl(H/"phase7d_sched.jsonl") if j["kind"]=="job"]
K=[j for j in jl(H/"phase7d_sched.jsonl") if j["kind"]=="skip"]
# sched log uses monotonic; select by offset: map via first/last sys sample pairing
off=S[0]["t_wall"]-S[0]["t_mono"] if S else 0
J=[j for j in J if t0<=j["t_enq"]+off<=t1]; K=[k for k in K if t0<=k.get("t",k.get("t_enq",0))+off<=t1] if K and ("t" in K[0] or "t_enq" in K[0]) else K
out={"label":label,"window_s":round(t1-t0,1)}
for typ in("final","partial"):
    T=[j for j in J if j["type"]==typ]; done=[j for j in T if j["state"]=="completed"]
    out[typ]={"jobs":len(T),"states":dict(Counter(j["state"] for j in T)),
      "queue_wait_p50_p95_max":[pct([j["t_start"]-j["t_enq"] for j in done],50),pct([j["t_start"]-j["t_enq"] for j in done],95),round(max([j["t_start"]-j["t_enq"] for j in done] or [0]),3)],
      "infer_p50_p95":[pct([j["t_end"]-j["t_start"] for j in done],50),pct([j["t_end"]-j["t_start"] for j in done],95)],
      "total_p95":pct([j["t_end"]-j["t_enq"] for j in done],95)}
busy=sum(j["t_end"]-j["t_start"] for j in J if j.get("t_start") is not None)
out["worker_utilisation"]=round(busy/(t1-t0),3)
out["abandoned_jobs"]=sum(1 for j in J if j.get("abandoned"))
out["skips"]=dict(Counter(k.get("reason") for k in K))
if S:
    out["system"]={"samples":len(S),"sys_cpu_mean":round(st.mean(s["sys_cpu"] for s in S),1),"sys_cpu_max":max(s["sys_cpu"] for s in S),
      "relay_cpu_mean_pct_core":round(st.mean(s["relay_cpu"] for s in S),1),"free_mb_min":min(s["free_mb"] for s in S),
      "free_mb_median":st.median(s["free_mb"] for s in S),"relay_rss_mb_max":max(s["relay_ws_mb"] for s in S),
      "relay_rss_mb_first_last":[S[0]["relay_ws_mb"],S[-1]["relay_ws_mb"]],"mem_pct_max":max(s["mem_pct"] for s in S)}
print(json.dumps(out,indent=1)); (H/f"phase7d_perf_{label}.json").write_text(json.dumps(out,indent=1))
