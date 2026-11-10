"""End-to-end benchmark client for the Parakeet relay. Acts like the Flutter
speaker: streams 16 kHz PCM16 over the real WebSocket protocol at real-time
pace and timestamps every transcript message that comes back. Touches no
production code and (no `session` param) writes nothing to the relay's
SQLite store.

What it measures, per clip and in aggregate:
  WER                     final text vs reference (micro-avg + bootstrap CI)
  time-to-first-word      first message (partial or final) of an utterance
                          minus the start of speech in the audio
  first-partial latency   same, partials only (None if engine has none)
  finalization latency    final message minus the END of speech. Includes the
                          relay's silence hang (default 0.6 s) -- reported
                          both with and without it (`after_hang`)
  partial revision rate   the relay only ever APPENDS partial words, so a
                          "revision" is a partial word that differs from the
                          word at the same index in the final text
  concurrency             --concurrency N parallel speaker sessions
  CPU / GPU               psutil + nvidia-smi sampling (optional)

Clock model: audio position `a` is considered captured at t0 + a, and each
chunk is sent when its last sample has been captured (like a mic callback).
So every latency here is "audio captured -> text received by client". It
EXCLUDES mic/OS capture latency, the Flutter render time and any tunnel
(Cloudflare) hop -- see README "Mic-to-screen".
"""
import argparse
import asyncio
import json
import platform
import random
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audio_utils import SAMPLE_RATE, read_wav, simulate_flushes, to_pcm16  # noqa: E402
from latency_match import legacy_index_pairing, match_events  # noqa: E402
from wer import corpus_wer, normalize, wer  # noqa: E402
from wer_policies import DISCLAIMER as WER_DISCLAIMER, policy_wer  # noqa: E402


def pct(values, q):
    return float(np.percentile(values, q)) if len(values) else None


def dist(values):
    return {"n": len(values), "p50": pct(values, 50), "p95": pct(values, 95),
            "max": float(max(values)) if len(values) else None,
            "mean": float(np.mean(values)) if len(values) else None}


# --------------------------------------------------------------------- stream
async def stream_clip(url: str, pcm: bytes, chunk_s: float, tail_s: float,
                      expected_finals: int, drain_s: float):
    """Returns (events, t0). events = [(t_rel_seconds, text, is_partial)]."""
    loop = asyncio.get_running_loop()
    events = []
    chunk_bytes = int(chunk_s * SAMPLE_RATE) * 2
    tail = bytes(int(tail_s * SAMPLE_RATE) * 2)
    async with websockets.connect(url, max_size=None, ping_interval=None) as ws:
        t0 = loop.time()

        async def rx():
            try:
                async for m in ws:
                    if isinstance(m, bytes):
                        continue
                    try:
                        d = json.loads(m)
                    except ValueError:
                        continue
                    if "text" in d:
                        events.append((loop.time() - t0, d["text"], bool(d.get("partial"))))
            except websockets.exceptions.ConnectionClosed:
                pass

        rx_task = asyncio.create_task(rx())
        data = pcm + tail
        k = 0
        for off in range(0, len(data), chunk_bytes):
            piece = data[off:off + chunk_bytes]
            k += 1
            wait = t0 + k * (chunk_s) - loop.time()  # chunk "captured" at end of its span
            if wait > 0:
                await asyncio.sleep(wait)
            await ws.send(piece)
        deadline = loop.time() + drain_s
        while loop.time() < deadline:
            if sum(1 for e in events if not e[2]) >= expected_finals:
                break
            await asyncio.sleep(0.05)
        rx_task.cancel()
    return events


# ------------------------------------------------------------------- analysis
def analyse_clip(clip: dict, events: list, utterances: list, hang_s: float) -> dict:
    finals = [e for e in events if not e[2]]
    final_text = " ".join(e[1] for e in finals)
    w = wer(clip["reference"], final_text)

    groups, cur = [], []  # partials since the previous final belong to the next final
    for e in sorted(events, key=lambda e: e[0]):
        if e[2]:
            cur.append(e)
        else:
            groups.append((cur, e))
            cur = []

    # Partial-revision stats still use arrival-order groups (they compare a
    # group's partials with its own final; no expected-utterance pairing).
    rev_words = rev_total = 0
    prefix_ok = prefix_total = 0
    for partials, fin in groups:
        if partials:
            p_words = normalize(" ".join(p[1] for p in partials))
            f_words = normalize(fin[1])
            for j, pw in enumerate(p_words):
                rev_total += 1
                if j >= len(f_words) or f_words[j] != pw:
                    rev_words += 1
            prefix_total += 1
            prefix_ok += int(p_words == f_words[:len(p_words)])

    # Latency: timestamp matching (Phase 4), not index pairing.
    m = match_events(utterances, events, hang_s)
    mp = m["pairs"]
    ttfw = [p["ttfw_s"] for p in mp if p["ttfw_s"] is not None]
    first_partial = [p["first_partial_s"] for p in mp if p["first_partial_s"] is not None]
    final_lat = [p["final_latency_s"] for p in mp if p["final_latency_s"] is not None]
    final_lat_after_hang = [p["final_latency_after_hang_s"] for p in mp if p["final_latency_after_hang_s"] is not None]
    final_after_flush = [p["final_after_flush_s"] for p in mp if p["final_after_flush_s"] is not None]
    legacy = legacy_index_pairing(utterances, events, hang_s)
    pw_scores = policy_wer(clip["reference"], final_text)

    return {
        "id": clip["id"], "tags": clip.get("tags", {}), "reference": clip["reference"],
        "hypothesis": final_text, **w,
        "utterances_expected": len(utterances), "expected_detail": utterances,
        "final_times_s": [round(e[0], 3) for e in finals],
        "final_words": [len(normalize(e[1])) for e in finals], "finals_received": len(finals),
        "partials_received": sum(1 for e in events if e[2]),
        # raw event timestamps, unrounded: [t_s, is_partial, text]
        "events_raw": [[e[0], bool(e[2]), e[1]] for e in sorted(events, key=lambda e: e[0])],
        # Phase 4: timestamp-matched latency; TTFW and final latency are separate.
        "ttfw_s": ttfw, "first_partial_s": first_partial,
        "final_latency_s": final_lat, "final_latency_after_hang_s": final_lat_after_hang,
        "final_after_flush_s": final_after_flush,
        "latency_match": {"pairs": mp, "unmatched_expected": m["unmatched_expected"],
                          "extra_finals": m["extra_finals"], "counts": m["counts"], "params": m["params"]},
        "legacy_index_paired": legacy,  # old method, kept for comparison only
        # WER: `sub/del/ins/errors/ref_words` above and summary `wer` stay RAW (baseline policy).
        "wer_raw": pw_scores["raw"],
        "wer_number_normalized": pw_scores["number"],
        "wer_compound_normalized": pw_scores["compound"],
        "partial_words": rev_total, "partial_words_revised": rev_words,
        "partial_prefix_ok": prefix_ok, "partial_prefix_total": prefix_total,
    }


def aggregate(results: list, hang_s: float) -> dict:
    flat = lambda key: [v for r in results for v in r[key]]  # noqa: E731
    pw = sum(r["partial_words"] for r in results)
    out = {
        "clips": len(results),
        "wer": corpus_wer(results),
        "ttfw_s": dist(flat("ttfw_s")),
        "first_partial_s": dist(flat("first_partial_s")),
        "final_latency_s": dist(flat("final_latency_s")),
        "final_latency_after_hang_s": dist(flat("final_latency_after_hang_s")),
        "partial_revision_rate": (sum(r["partial_words_revised"] for r in results) / pw) if pw else None,
        "partial_prefix_stable_rate": (
            sum(r["partial_prefix_ok"] for r in results) / max(sum(r["partial_prefix_total"] for r in results), 1)
            if pw else None),
        "segment_mismatch_clips": sum(1 for r in results if r["finals_received"] != r["utterances_expected"]),
        "final_after_flush_s": dist(flat("final_after_flush_s")),
        "latency_matching": {
            "method": "timestamp, one-to-one monotonic (latency_match.py)",
            "matched": sum(r["latency_match"]["counts"]["matched"] for r in results),
            "unmatched_expected": sum(r["latency_match"]["counts"]["unmatched_expected"] for r in results),
            "extra_finals": sum(r["latency_match"]["counts"]["extra_finals"] for r in results),
            "clips_with_unmatched_or_extra": [r["id"] for r in results if
                                               r["latency_match"]["counts"]["unmatched_expected"]
                                               or r["latency_match"]["counts"]["extra_finals"]],
        },
        # Diagnostic WER variants; raw `wer` above is the baseline and is never replaced.
        "wer_raw": corpus_wer([r["wer_raw"] for r in results]),
        "wer_number_normalized": corpus_wer([r["wer_number_normalized"] for r in results]),
        "wer_compound_normalized": corpus_wer([r["wer_compound_normalized"] for r in results]),
        "wer_note": WER_DISCLAIMER,
        "hang_s_assumed": hang_s,
    }
    by_tag = defaultdict(lambda: defaultdict(list))
    for r in results:
        for k, v in r["tags"].items():
            by_tag[k][str(v)].append(r)
    out["wer_by_tag"] = {k: {v: corpus_wer(rows) for v, rows in sorted(vals.items())}
                         for k, vals in by_tag.items()}
    return out


# ------------------------------------------------------------------ resources
class ResourceSampler:
    def __init__(self, relay_pid=None, period=1.0):
        self.period, self.samples, self._task = period, [], None
        self.proc = None
        try:
            import psutil
            self.psutil = psutil
            if relay_pid:
                self.proc = psutil.Process(relay_pid)
                self.proc.cpu_percent(None)
            psutil.cpu_percent(None)
        except Exception:
            self.psutil = None
        self.nvsmi = shutil.which("nvidia-smi")

    def _gpu(self):
        if not self.nvsmi:
            return None
        try:
            out = subprocess.run(
                [self.nvsmi, "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3).stdout.strip().splitlines()[0]
            u, m = [float(v) for v in out.split(",")]
            return u, m
        except Exception:
            return None

    async def _run(self):
        while True:
            await asyncio.sleep(self.period)
            s = {}
            if self.psutil:
                s["sys_cpu"] = self.psutil.cpu_percent(None)
                if self.proc:
                    try:
                        s["relay_cpu"] = self.proc.cpu_percent(None)
                        s["relay_rss_mb"] = self.proc.memory_info().rss / 1e6
                    except Exception:
                        pass
            g = await asyncio.to_thread(self._gpu)
            if g:
                s["gpu_util"], s["gpu_mem_mb"] = g
            self.samples.append(s)

    def start(self):
        self._task = asyncio.create_task(self._run())

    def stop(self) -> dict:
        if self._task:
            self._task.cancel()
        keys = {k for s in self.samples for k in s}
        return {k: {"mean": float(np.mean([s[k] for s in self.samples if k in s])),
                    "max": float(max(s[k] for s in self.samples if k in s))} for k in sorted(keys)} \
            | {"_samples": len(self.samples)}


# ----------------------------------------------------------------------- main
def load_manifest(path: Path):
    m = json.loads(path.read_text(encoding="utf-8"))
    base = path.parent
    clips = []
    for c in m["clips"]:
        c = dict(c)
        c["wav_path"] = (base / c["wav"]).resolve()
        c["timing_path"] = (base / c["timing_wav"]).resolve() if c.get("timing_wav") else c["wav_path"]
        clips.append(c)
    return clips


async def run_level(args, clips, concurrency: int, prepared: dict) -> dict:
    sampler = ResourceSampler(args.relay_pid)
    rng = random.Random(args.seed)
    results, errors = [], []

    async def worker(wid: int):
        await asyncio.sleep(rng.uniform(0, args.stagger) if concurrency > 1 else 0)
        order = clips[wid % len(clips):] + clips[:wid % len(clips)]
        for clip in order:
            pcm, utts = prepared[clip["id"]]
            try:
                ev = await stream_clip(args.url, pcm, args.chunk_ms / 1000, args.tail_s,
                                       len(utts), args.drain_s)
            except Exception as e:  # keep the run alive; record the failure
                errors.append({"clip": clip["id"], "worker": wid, "error": repr(e)})
                continue
            r = analyse_clip(clip, ev, utts, args.hang_s)
            r["worker"] = wid
            results.append(r)

    sampler.start()
    t = time.time()
    await asyncio.gather(*(worker(i) for i in range(concurrency)))
    wall = time.time() - t
    return {"concurrency": concurrency, "wall_s": wall, "errors": errors,
            "resources": sampler.stop(), "summary": aggregate(results, args.hang_s), "clips": results}


def fmt(v, nd=3):
    return "-" if v is None else f"{v:.{nd}f}"


def print_report(levels):
    print("\n| N | clips | WER | p50 TTFW s | p95 TTFW s | p50 final s | p95 final s | p95 final-after-hang s "
          "| revision rate | errors | GPU util mean/max | relay CPU mean/max |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for L in levels:
        s, res = L["summary"], L["resources"]
        w = s["wer"]
        wtxt = "-" if w["wer"] is None else (f"{w['wer'] * 100:.2f}%"
                                              + (f" [{w['ci95'][0] * 100:.1f}-{w['ci95'][1] * 100:.1f}]" if w["ci95"] else ""))
        g, c = res.get("gpu_util"), res.get("relay_cpu")
        gtxt = "-" if not g else "%.0f/%.0f" % (g["mean"], g["max"])
        ctxt = "-" if not c else "%.0f/%.0f" % (c["mean"], c["max"])
        print(f"| {L['concurrency']} | {s['clips']} | {wtxt} | {fmt(s['ttfw_s']['p50'])} | {fmt(s['ttfw_s']['p95'])} "
              f"| {fmt(s['final_latency_s']['p50'])} | {fmt(s['final_latency_s']['p95'])} "
              f"| {fmt(s['final_latency_after_hang_s']['p95'])} | {fmt(s['partial_revision_rate'], 3)} "
              f"| {len(L['errors'])} | {gtxt} | {ctxt} |")
    base = levels[0]["summary"]["wer_by_tag"]
    for k, vals in base.items():
        print(f"\nWER by `{k}` (N={levels[0]['concurrency']}):")
        for v, w in vals.items():
            ci = f" [{w['ci95'][0] * 100:.1f}-{w['ci95'][1] * 100:.1f}]" if w["ci95"] else ""
            print(f"  {v:<18} {fmt(None if w['wer'] is None else w['wer'] * 100, 2)}%{ci}  "
                  f"({w['clips']} clips, {w['ref_words']} words)")


async def amain(args):
    clips = load_manifest(Path(args.manifest))
    prepared = {}
    for c in clips:
        pcm = to_pcm16(read_wav(c["wav_path"]))
        utts = c.get("utterances") or simulate_flushes(read_wav(c["wav_path"]), args.chunk_ms / 1000, args.tail_s,
                                                      args.rms_threshold, args.hang_s, max_s=args.max_utt_s,
                                                      adaptive=args.adaptive, noise_mult=args.noise_mult)
        prepared[c["id"]] = (pcm, utts)

    for _ in range(args.warmup):  # first call pays model/Metal/CUDA warm-up; keep it out of the numbers
        pcm, utts = prepared[clips[0]["id"]]
        await stream_clip(args.url, pcm, args.chunk_ms / 1000, args.tail_s, len(utts), args.drain_s)

    levels = []
    for n in [int(x) for x in args.concurrency.split(",")]:
        print(f"== concurrency {n}: {len(clips)} clips x {n} sessions ==", flush=True)
        levels.append(await run_level(args, clips, n, prepared))

    report = {"meta": {"when": time.strftime("%Y-%m-%dT%H:%M:%S"), "host": platform.platform(),
                       "python": platform.python_version(), "url": args.url, "note": args.note,
                       "chunk_ms": args.chunk_ms, "tail_s": args.tail_s, "hang_s_assumed": args.hang_s,
                       "warmup": args.warmup, "manifest": str(args.manifest),
                       "caveat": "latency = audio captured -> text received by this client; excludes mic, UI, tunnel"},
              "levels": levels}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print_report(levels)
    print(f"\nfull results: {out}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--manifest", required=True)
    p.add_argument("--url", default="ws://localhost:8768/?role=speaker")
    p.add_argument("--out", default="benchmarks/results/run.json")
    p.add_argument("--concurrency", default="1", help="comma list of parallel sessions, e.g. 1,2,4,8")
    p.add_argument("--chunk-ms", type=int, default=100, help="size of each audio frame sent (match the app!)")
    p.add_argument("--tail-s", type=float, default=1.5, help="trailing silence so the VAD flushes the last utterance")
    p.add_argument("--hang-s", type=float, default=0.6, help="relay STT_SILENCE_HANG_SECONDS (for after-hang numbers)")
    p.add_argument("--rms-threshold", type=float, default=0.01, help="relay STT_SILENCE_RMS_THRESHOLD")
    p.add_argument("--max-utt-s", type=float, default=8.0, help="relay STT_MAX_UTTERANCE_SECONDS")
    p.add_argument("--adaptive", action="store_true", help="model relay STT_ADAPTIVE_NOISE_FLOOR=1 in ground-truth flush simulation")
    p.add_argument("--noise-mult", type=float, default=2.5, help="relay STT_NOISE_FLOOR_MULTIPLIER")
    p.add_argument("--drain-s", type=float, default=8.0, help="max wait for finals after the audio ends")
    p.add_argument("--stagger", type=float, default=1.0, help="random start offset (s) per session when N>1")
    p.add_argument("--warmup", type=int, default=1)
    p.add_argument("--relay-pid", type=int, default=None, help="relay process id for CPU/RSS sampling")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--note", default="", help="free text stored in the results (hardware, engine, relay env)")
    asyncio.run(amain(p.parse_args()))


if __name__ == "__main__":
    main()
