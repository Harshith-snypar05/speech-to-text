"""Phase 7B system sampler (read-only): every 2 s append system CPU %, free memory, page-fault counter,
current CPU MHz, and the instrumented relay's working set / CPU % to a JSONL file. Stops when STOP file appears."""
import json, sys, time
from pathlib import Path
import psutil

out = Path(sys.argv[1]); pid = int(sys.argv[2]); stop = Path(sys.argv[3])
p = psutil.Process(pid)
p.cpu_percent(None)
psutil.cpu_percent(None)
with open(out, "a", encoding="utf-8", buffering=1) as f:
    while not stop.exists():
        time.sleep(2)
        vm = psutil.virtual_memory()
        try:
            mi = p.memory_info()
            rec = {"t_mono": time.monotonic(), "t_wall": time.time(), "sys_cpu": psutil.cpu_percent(None),
                   "free_mb": round(vm.available / 2**20), "mem_pct": vm.percent,
                   "mhz": (psutil.cpu_freq().current if psutil.cpu_freq() else None),
                   "relay_cpu": p.cpu_percent(None), "relay_ws_mb": round(mi.rss / 2**20),
                   "relay_pagefaults": getattr(mi, "num_page_faults", None)}
        except psutil.Error:
            break
        f.write(json.dumps(rec) + "\n")
