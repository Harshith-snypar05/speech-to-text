"""Parakeet-only transcript consistency passes (isolated; production code imported read-only).

Loads the production ParakeetNativeEngine ONCE (same lib + q8_0 model the relay uses, default params) and, per pilot
clip, runs:
  B   full-clip offline transcribe_final()                       (independent re-transcription)
  B2  identical call again                                       (determinism check, NOT independent evidence)
  C   overlapping windows (--win s, --hop s) each transcribe_final(), merged by overlap text-alignment
  D   offline replay of the relay's UtteranceBuffer (production class, production config values) over the clip +
      bench tail, transcribe_final() on each flushed snapshot -- what the relay would transcribe, without sockets.
Raw output only -> results/parakeet_raw_passes.json. Comparison/status is done by analyze_consistency.py.
No ASR other than that engine. No model/parameter change. No reference transcripts are used or created.
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "relays"))
from audio_utils import SAMPLE_RATE, read_wav, to_pcm16  # noqa: E402
from wer import normalize  # noqa: E402


def merge_windows(texts):
    """Join window transcripts, dropping the overlapped prefix of each next window by aligning it to the tail of the
    words so far (difflib). Heuristic -- records match counts so weak joins are visible."""
    from difflib import SequenceMatcher
    acc, info = [], []
    for k, t in enumerate(texts):
        w = t.split()
        if not acc:
            acc += w
            info.append(dict(window=k, dropped=0, matched=None))
            continue
        tail_raw = acc[-12:]
        tn, wn = [normalize(x) for x in tail_raw], [normalize(x) for x in w[:12]]
        tn = [x[0] if x else "" for x in tn]
        wn = [x[0] if x else "" for x in wn]
        blocks = [b for b in SequenceMatcher(None, tn, wn, autojunk=False).get_matching_blocks() if b.size]
        matched = sum(b.size for b in blocks)
        if matched >= 2:
            cut = max(b.b + b.size for b in blocks)
            acc += w[cut:]
            info.append(dict(window=k, dropped=cut, matched=matched))
        else:
            acc += w
            info.append(dict(window=k, dropped=0, matched=matched, weak_join=True))
    return " ".join(acc), info


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="dataset_existing/pilot/manifest.json")
    ap.add_argument("--lib-dir", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--win", type=float, default=8.0)
    ap.add_argument("--hop", type=float, default=6.0)
    ap.add_argument("--out", default="results/parakeet_raw_passes.json")
    a = ap.parse_args()

    from core import config as C  # noqa: E402  production values, read-only
    from core.audio_processor import UtteranceBuffer  # noqa: E402
    from engines.parakeet_native_engine import ParakeetNativeEngine  # noqa: E402
    engine = ParakeetNativeEngine(Path(a.lib_dir), Path(a.model))

    m = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    base = Path(a.manifest).parent
    out = dict(meta=dict(engine="ParakeetNativeEngine", model=a.model, lib_dir=a.lib_dir, win_s=a.win, hop_s=a.hop,
                         relay_cfg=dict(thr=C.SILENCE_RMS_THRESHOLD, hang=C.SILENCE_HANG_SECONDS,
                                        min_utt=C.MIN_UTTERANCE_SECONDS, max_utt=C.MAX_UTTERANCE_SECONDS,
                                        adaptive=C.ADAPTIVE_NOISE_FLOOR)), clips=[])
    # warm-up (not recorded)
    await engine.transcribe_final(to_pcm16(read_wav(base / m["clips"][0]["wav"]))[: SAMPLE_RATE * 2 * 3])
    for c in m["clips"]:
        x = read_wav(base / c["wav"])
        pcm = to_pcm16(x)
        dur = len(x) / SAMPLE_RATE
        rec = dict(id=c["id"], duration_s=dur, error=None)
        try:
            t = time.perf_counter(); rec["B"] = await engine.transcribe_final(pcm); rec["B_s"] = time.perf_counter() - t
            rec["B2"] = await engine.transcribe_final(pcm)
            # C: overlapping windows
            W, H = int(a.win * SAMPLE_RATE), int(a.hop * SAMPLE_RATE)
            starts, s = [], 0
            while True:
                starts.append(s)
                if s + W >= len(x):
                    break
                s += H
            if len(starts) > 1 and len(x) - starts[-1] < 3 * SAMPLE_RATE:  # tiny tail: fold into previous window
                starts.pop()
            wins = []
            for i, s in enumerate(starts):
                e = len(x) if i == len(starts) - 1 else min(len(x), s + W)
                txt = await engine.transcribe_final(pcm[s * 2:e * 2])
                wins.append(dict(start_s=s / SAMPLE_RATE, end_s=e / SAMPLE_RATE, text=txt))
            merged, info = merge_windows([w["text"] for w in wins])
            rec["C"] = merged
            rec["C_windows"] = wins
            rec["C_merge"] = info
            # D: offline replay of the production UtteranceBuffer
            buf = UtteranceBuffer(C.SAMPLE_RATE, C.BYTES_PER_SAMPLE, C.SILENCE_RMS_THRESHOLD, C.SILENCE_HANG_SECONDS,
                                  C.MIN_UTTERANCE_SECONDS, C.MAX_UTTERANCE_SECONDS,
                                  adaptive_noise_floor=C.ADAPTIVE_NOISE_FLOOR, noise_floor_multiplier=C.NOISE_FLOOR_MULTIPLIER)
            data = pcm + bytes(int(1.5 * SAMPLE_RATE) * 2)
            step = int(0.1 * SAMPLE_RATE) * 2
            flushes, t_audio = [], 0.0

            async def do_flush(t_end, why):
                pending = buf.has_pending_utterance()
                speech_s = buf.speech_s
                snap = buf.take()
                if not pending:
                    flushes.append(dict(t_end=t_end, why=why, pending=False, snap_s=len(snap) / 32000, speech_s=speech_s,
                                        text=None, decode_s=None))
                    return
                t = time.perf_counter()
                txt = await engine.transcribe_final(snap)
                flushes.append(dict(t_end=t_end, why=why, pending=True, snap_s=len(snap) / 32000, speech_s=speech_s,
                                    text=txt, empty=(not txt), decode_s=time.perf_counter() - t))

            for off in range(0, len(data), step):
                t_audio = (off + step) / 32000
                if buf.add_chunk(data[off:off + step]):
                    await do_flush(t_audio, "boundary")
            if buf.buffer:
                await do_flush(t_audio, "disconnect")
            rec["D_flushes"] = flushes
            rec["D"] = " ".join(f["text"] for f in flushes if f.get("text"))
        except Exception as e:  # noqa: BLE001
            rec["error"] = repr(e)
        out["clips"].append(rec)
        print(rec["id"], "err" if rec["error"] else f"B={len(rec.get('B','').split())}w C={len(rec.get('C','').split())}w "
              f"D={len(rec.get('D','').split())}w flushes={len(rec.get('D_flushes', []))}", flush=True)
    Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    sh = getattr(engine, "shutdown", None)
    if sh:
        r = sh()
        if asyncio.iscoroutine(r):
            await r


if __name__ == "__main__":
    asyncio.run(main())
