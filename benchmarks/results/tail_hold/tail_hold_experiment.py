"""STT_STREAM_TAIL_HOLD_SECONDS experiment (staging only). usage: TH_WAV=<wav> python tail_hold_experiment.py <engine> [reps]

Three throwaway relays (ports 8781-8783, one per hold value) share one ASR worker. The same recording is streamed at
real-time pace; reps are interleaved across holds with rotating order so drift hits all configs alike. Relays use a
scratch copy of qa.db (consent preserved, real account data untouched); the scratch dir is deleted at exit.
Metrics are measured from what a client receives. Nothing is approved or applied by this script.
"""
import array
import asyncio
import difflib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

import numpy as np
import websockets

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "benchmarks" / "results" / "phase7d"))
import qa_scenarios as q  # noqa: E402

ENGINE = sys.argv[1]
REPS = int(sys.argv[2]) if len(sys.argv) > 2 else 5
HOLDS = [0.25, 0.15, 0.10]
PORTS = {0.25: 8781, 0.15: 8782, 0.10: 8783}
assert not set(PORTS.values()) & {8768, 8769, 8772}
WAV = Path(os.environ["TH_WAV"])
OUT = Path(__file__).parent
DT = 0.1


def http(port, path):
    return urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}{path}"), timeout=10)


def start_relay(hold, scratch):
    port = PORTS[hold]
    env = dict(os.environ)
    for line in (ROOT / "staging_secrets" / "qa.env").read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            env[k] = v
    env.pop("STT_QA_RETENTION_DAYS", None)
    env.update(STT_QA_ADMINS="tester.one@gmail.com", STT_LISTEN_PORT=str(port), STT_QA_DIR=str(scratch),
               STT_ENGINE=ENGINE, STT_STREAM_TAIL_HOLD_SECONDS=str(hold))
    code = ("import sys,asyncio;sys.path.insert(0,r'%s');import parakeet_relay;asyncio.run(parakeet_relay.main())"
            % (ROOT / "relays_phase7c"))
    proc = subprocess.Popen([sys.executable, "-c", code], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        time.sleep(2)
        try:
            http(port, "/qa/me")
        except urllib.error.HTTPError:
            return proc
        except Exception:
            pass
    proc.kill()
    raise SystemExit(f"relay {port} did not start")


def norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())


_w = wave.open(str(WAV))
PCM = _w.readframes(_w.getnframes())
STEP = int(16000 * DT) * 2
CHUNKS = [PCM[i:i + STEP] for i in range(0, len(PCM), STEP)]
VOICED = []
for _c in CHUNKS:
    _a = array.array("h")
    _a.frombytes(_c)
    VOICED.append(math.sqrt(sum(x * x for x in _a) / max(1, len(_a))) / 32768 > 0.01)
STARTS = []  # voiced onset after >=0.6 s of silence
_sil, _speaking = 99.0, False
for _i, _v in enumerate(VOICED):
    if _v:
        if not _speaking and _sil >= 0.6:
            STARTS.append(_i * DT)
        _speaking, _sil = True, 0.0
    else:
        _sil += DT
        if _sil >= 0.6:
            _speaking = False
VOICED_S = sum(VOICED) * DT


def last_voiced_before(t):
    idx = min(len(VOICED) - 1, int(t / DT))
    for i in range(idx, -1, -1):
        if VOICED[i]:
            return (i + 1) * DT
    return 0.0


async def stream(port, token, tag):
    ev = []
    sid = f"th-{tag}-{int(time.time() * 1000)}"
    async with websockets.connect(f"ws://127.0.0.1:{port}/?role=speaker&session={sid}&token={token}", max_size=None) as ws:
        t0 = time.monotonic()

        async def rx():
            try:
                async for m in ws:
                    d = json.loads(m)
                    ev.append((time.monotonic() - t0, bool(d.get("partial")), d.get("text", "")))
            except Exception:
                pass

        rt = asyncio.create_task(rx())
        for i, c in enumerate(CHUNKS):
            await asyncio.sleep(max(0, t0 + i * DT - time.monotonic()))
            await ws.send(c)
        await asyncio.sleep(3.5)
        await ws.close()
        rt.cancel()
    return ev


def analyse(ev):
    """Group events into utterances (partials since previous final, then the final) and measure."""
    utts, cur = [], []
    for t, partial, text in ev:
        if partial:
            cur.append((t, text))
        else:
            utts.append((cur, t, text))
            cur = []
    fp, stable_first, fin_lat, exposed, emitted, final_words = [], [], [], 0, 0, 0
    for parts, tf, ftext in utts:
        F = [norm(x) for x in ftext.split()]
        final_words += len(F)
        fin_lat.append(tf - last_voiced_before(tf))
        if not parts:
            continue
        starts = [s for s in STARTS if s <= parts[0][0]]
        s_u = starts[-1] if starts else 0.0
        fp.append(parts[0][0] - s_u)
        idx, first_stable = 0, None
        for t, text in parts:
            for wd in text.split():
                emitted += 1
                ok = idx < len(F) and norm(wd) == F[idx]
                if not ok:
                    exposed += 1
                elif first_stable is None:
                    first_stable = t - s_u
                idx += 1
        if first_stable is not None:
            stable_first.append(first_stable)
    n_part = sum(1 for _, p, _ in ev if p)
    return dict(first_partial=fp, first_stable=stable_first, final_lat=fin_lat, emitted=emitted, exposed=exposed,
                partials=n_part, partials_per_voiced_s=n_part / VOICED_S, finals=len(utts), final_words=final_words,
                final_text=" ".join(norm(x) for _, _, t in utts for x in t.split()))


def pct(xs, p):
    return float(np.percentile(xs, p)) if len(xs) else None


async def main():
    scratch = Path(tempfile.mkdtemp(prefix="th_qa_"))
    shutil.copy(ROOT / "staging_data_qa" / "qa.db", scratch / "qa.db")
    procs = {}
    results = {"engine": ENGINE, "reps": REPS, "holds": HOLDS, "wav": WAV.name, "voiced_s": VOICED_S, "runs": []}
    try:
        for h in HOLDS:
            procs[h] = start_relay(h, scratch)
        emails = sorted(q.creds())
        toks = {}
        for h in HOLDS:
            q.BASE = f"http://127.0.0.1:{PORTS[h]}"
            for e in emails:
                t = q.login(e, q.creds()[e])
                assert t, f"login failed {e}"
                s, b = q.http("/qa/me", token=t)
                assert json.loads(b).get("consent"), f"{e} lacks consent; experiment never changes consent"
                toks[(h, e)] = t
        for mode in ("single", "concurrent3"):
            for r in range(REPS):
                order = HOLDS[r % 3:] + HOLDS[:r % 3]
                for h in order:
                    who = emails[:1] if mode == "single" else emails[:3]
                    evs = await asyncio.gather(*[stream(PORTS[h], toks[(h, e)], f"{mode}{r}-{i}") for i, e in enumerate(who)])
                    for e, ev in zip(who, evs):
                        a = analyse(ev)
                        a.update(mode=mode, rep=r, hold=h, account=emails.index(e))
                        results["runs"].append(a)
                    print(mode, r, h, "done", flush=True)
    finally:
        for p in procs.values():
            p.terminate()
        shutil.rmtree(scratch, ignore_errors=True)
    base = {(x["mode"], x["rep"], x["account"]): x["final_text"] for x in results["runs"] if x["hold"] == 0.25}
    for x in results["runs"]:
        b = base.get((x["mode"], x["rep"], x["account"]), "")
        x["text_similarity_to_baseline"] = difflib.SequenceMatcher(None, b.split(), x["final_text"].split()).ratio()
        x["word_delta_vs_baseline"] = len(x["final_text"].split()) - len(b.split())
    (OUT / f"raw_{ENGINE}.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    summ = {}
    for mode in ("single", "concurrent3"):
        for h in HOLDS:
            rs = [x for x in results["runs"] if x["mode"] == mode and x["hold"] == h]
            if not rs:
                continue

            def cat(k):
                return [v for x in rs for v in x[k]]

            em = sum(x["emitted"] for x in rs)
            summ[f"{mode}/{h}"] = dict(
                runs=len(rs),
                first_partial_med=pct(cat("first_partial"), 50), first_partial_p90=pct(cat("first_partial"), 90),
                first_partial_p95=pct(cat("first_partial"), 95),
                first_stable_med=pct(cat("first_stable"), 50), first_stable_p90=pct(cat("first_stable"), 90),
                first_stable_p95=pct(cat("first_stable"), 95),
                final_med=pct(cat("final_lat"), 50), final_p90=pct(cat("final_lat"), 90), final_p95=pct(cat("final_lat"), 95),
                partials_per_voiced_s=float(np.mean([x["partials_per_voiced_s"] for x in rs])),
                incomplete_word_exposure=(sum(x["exposed"] for x in rs) / em) if em else None, emitted_words=em,
                final_words_mean=float(np.mean([x["final_words"] for x in rs])),
                finals_mean=float(np.mean([x["finals"] for x in rs])),
                min_text_similarity_to_baseline=min(x["text_similarity_to_baseline"] for x in rs),
                max_abs_word_delta_vs_baseline=max(abs(x["word_delta_vs_baseline"]) for x in rs))
    (OUT / f"summary_{ENGINE}.json").write_text(json.dumps(summ, indent=1), encoding="utf-8")
    print(json.dumps(summ, indent=1))


asyncio.run(main())
