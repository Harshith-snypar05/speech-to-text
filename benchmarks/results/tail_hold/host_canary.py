"""Host-level stall canary (diagnostics only). usage: python host_canary.py <out.jsonl> <seconds>
Independent process: logs every time its own 50 ms sleep is late by >0.2 s (OS/CPU scheduling stall) and samples GPU
SM clock / util / power once a second. Lets a failed rep be matched against host stalls vs worker behaviour."""
import json, subprocess, sys, time
out, dur = sys.argv[1], float(sys.argv[2])
f = open(out, "w", buffering=1)
end = time.time() + dur; nxt = 0
while time.time() < end:
    t = time.perf_counter(); time.sleep(0.05); late = time.perf_counter() - t - 0.05
    if late > 0.2: f.write(json.dumps({"ev": "stall", "t": round(time.time(), 3), "late": round(late, 3)}) + "\n")
    if time.time() >= nxt:
        nxt = time.time() + 1
        try:
            o = subprocess.check_output(["nvidia-smi", "--query-gpu=clocks.sm,utilization.gpu,power.draw", "--format=csv,noheader,nounits"], text=True, timeout=5).strip().split(",")
            f.write(json.dumps({"ev": "gpu", "t": round(time.time(), 3), "sm": int(o[0]), "util": int(o[1]), "w": float(o[2])}) + "\n")
        except Exception as e:
            f.write(json.dumps({"ev": "gpu_err", "t": round(time.time(), 3), "e": repr(e)[:80]}) + "\n")
