"""Nemotron 0.6B worker-lifecycle investigation (staging only). usage: TH_WAV=<wav> python nemotron_concurrency_check.py <label> <reps>

One throwaway relay (port 8781, STT_STREAM_TAIL_HOLD_SECONDS=0.25, STT_ENGINE=nemotron) talks to the already-running ASR worker.
Each rep: 3 accounts stream the same recording concurrently at real-time pace; then (every rep) one single-stream probe.
Per account/rep: finals, words, first-word and final latency, close code/reason, errors. GPU sampled via nvidia-smi during
every rep; the worker log is diffed per rep. Runs whose finals/words differ from EXPECTED are marked invalid and excluded
from latency statistics. No setting is changed by this script. Worker inference queue wait is not instrumented: unavailable.
"""
import array, asyncio, json, math, os, re, shutil, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request, wave
from pathlib import Path

import numpy as np
import websockets

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "benchmarks" / "results" / "phase7d"))
import qa_scenarios as q  # noqa: E402

LABEL, REPS = sys.argv[1], int(sys.argv[2])
PORT, HOLD = 8781, 0.25
EXPECT_FINALS, EXPECT_WORDS = 7, 57  # from 15 clean single-stream Nemotron runs in raw_nemotron.json
WAV = Path(os.environ["TH_WAV"])
OUT = Path(__file__).parent
WORKER_LOG = ROOT.parent / "asr_env_logs" / "worker.log"
DT = 0.1

w = wave.open(str(WAV))
PCM = w.readframes(w.getnframes())
STEP = int(16000 * DT) * 2
CHUNKS = [PCM[i:i + STEP] for i in range(0, len(PCM), STEP)]
VOICED = []
for c in CHUNKS:
    a = array.array("h"); a.frombytes(c)
    VOICED.append(math.sqrt(sum(x * x for x in a) / max(1, len(a))) / 32768 > 0.01)
STARTS, sil, spk = [], 99.0, False
for i, v in enumerate(VOICED):
    if v:
        if not spk and sil >= 0.6:
            STARTS.append(i * DT)
        spk, sil = True, 0.0
    else:
        sil += DT
        if sil >= 0.6:
            spk = False


def last_voiced_before(t):
    for i in range(min(len(VOICED) - 1, int(t / DT)), -1, -1):
        if VOICED[i]:
            return (i + 1) * DT
    return 0.0


def norm(x):
    return re.sub(r"[^a-z0-9']", "", x.lower())


def start_relay(scratch, logf):
    env = dict(os.environ)
    for line in (ROOT / "staging_secrets" / "qa.env").read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1); env[k] = v
    env.pop("STT_QA_RETENTION_DAYS", None)
    env.pop("MONGODB_URI", None)
    env.update(STT_QA_ADMINS="tester.one@gmail.com", STT_LISTEN_PORT=str(PORT), STT_QA_DIR=str(scratch),
               STT_ENGINE="nemotron", STT_STREAM_TAIL_HOLD_SECONDS=str(HOLD))
    code = "import sys,asyncio;sys.path.insert(0,r'%s');import parakeet_relay;asyncio.run(parakeet_relay.main())" % (ROOT / "relays_phase7c")
    proc = subprocess.Popen([sys.executable, "-c", code], env=env, stdout=logf, stderr=logf)
    for _ in range(60):
        time.sleep(2)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/qa/me", timeout=10)
        except urllib.error.HTTPError:
            return proc
        except Exception:
            pass
    proc.kill(); raise SystemExit("relay did not start")


class Gpu(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True); self.s = []; self.stop = False

    def run(self):
        while not self.stop:
            try:
                o = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits"], text=True).strip().split(",")
                self.s.append((int(o[0]), int(o[1])))
            except Exception:
                pass
            time.sleep(0.5)


async def stream(token, tag):
    ev, info = [], {"close": None, "exc": None}
    sid = f"nc-{tag}-{int(time.time() * 1000)}"
    try:
        async with websockets.connect(f"ws://127.0.0.1:{PORT}/?role=speaker&session={sid}&token={token}", max_size=None) as ws:
            t0 = time.monotonic()

            async def rx():
                try:
                    async for m in ws:
                        d = json.loads(m); ev.append((time.monotonic() - t0, bool(d.get("partial")), d.get("text", "")))
                except Exception as e:
                    info["exc"] = repr(e)[:200]

            rt = asyncio.create_task(rx())
            for i, c in enumerate(CHUNKS):
                await asyncio.sleep(max(0, t0 + i * DT - time.monotonic()))
                await ws.send(c)
            await asyncio.sleep(3.5)
            info["close"] = (ws.close_code, ws.close_reason)
            await ws.close(); rt.cancel()
    except Exception as e:
        info["exc"] = repr(e)[:200]
    return ev, info


def analyse(ev, info):
    utts, cur = [], []
    for t, p, text in ev:
        if p: cur.append((t, text))
        else: utts.append((cur, t, text)); cur = []
    fp, fl, words = [], [], 0
    for parts, tf, ft in utts:
        words += len(ft.split()); fl.append(tf - last_voiced_before(tf))
        if parts:
            st = [s for s in STARTS if s <= parts[0][0]]
            fp.append(parts[0][0] - (st[-1] if st else 0.0))
    return dict(finals=len(utts), words=words, first_word=fp, final_lat=fl, last_event_t=ev[-1][0] if ev else None,
                partials=sum(1 for _, p, _ in ev if p), close=info["close"], exc=info["exc"],
                valid=(len(utts) == EXPECT_FINALS and words == EXPECT_WORDS and not info["exc"]),
                events=[(round(t, 3), p, tx) for t, p, tx in ev])


def log_lines():
    try:
        return WORKER_LOG.read_text(errors="replace").splitlines()
    except Exception:
        return []


async def main():
    scratch = Path(tempfile.mkdtemp(prefix="nc_qa_"))
    shutil.copy(ROOT / "staging_data_qa" / "qa.db", scratch / "qa.db")
    logf = open(OUT / f"relay_{LABEL}.log", "w")
    proc = start_relay(scratch, logf)
    res = {"label": LABEL, "expect": [EXPECT_FINALS, EXPECT_WORDS], "hold": HOLD, "reps": []}
    try:
        emails = sorted(q.creds()); q.BASE = f"http://127.0.0.1:{PORT}"
        toks = {}
        for e in emails:
            t = q.login(e, q.creds()[e]); assert t, f"login {e}"
            toks[e] = t
        for r in range(REPS):
            for kind, who in (("concurrent3", emails[:3]), ("single", emails[:1])):
                n0 = len(log_lines()); g = Gpu(); g.start()
                out = await asyncio.gather(*[stream(toks[e], f"{kind}{r}-{i}") for i, e in enumerate(who)])
                g.stop = True; g.join(2)
                new = [l for l in log_lines()[n0:] if re.search(r"error|exception|traceback|warning|timeout", l, re.I)]
                for i, (ev, info) in enumerate(out):
                    a = analyse(ev, info); a.update(kind=kind, rep=r, account=i)
                    a["gpu_mem_mib_max"] = max((m for m, _ in g.s), default=None)
                    a["gpu_util_pct_max"] = max((u for _, u in g.s), default=None)
                    a["gpu_util_pct_mean"] = float(np.mean([u for _, u in g.s])) if g.s else None
                    a["worker_log_problems"] = new[:5]
                    res["reps"].append(a)
                print(kind, r, [(x["finals"], x["words"], x["valid"]) for x in res["reps"][-len(who):]], flush=True)
    finally:
        proc.terminate(); logf.close(); shutil.rmtree(scratch, ignore_errors=True)
    (OUT / f"nemotron_check_{LABEL}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


asyncio.run(main())
