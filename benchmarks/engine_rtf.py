"""Engine-only real-time factor (RTF), no WebSocket, no VAD. Imports the
production engine classes read-only and times transcribe_final() on each
corpus clip.   RTF = processing_seconds / audio_seconds   (lower is better,
<1 means faster than real time).

  python engine_rtf.py --manifest corpus/manifest.json --engine native \
      --lib-dir ../whisper.cpp/build-shared/bin --model ../whisper.cpp/models/ggml-parakeet-tdt-0.6b-v3-q8_0.bin
  python engine_rtf.py ... --engine cli --cli ../whisper.cpp/build/bin/parakeet-cli

STATUS: written but not yet run -- the model / whisper.cpp build are not on
the machine this was authored on. Run it where they exist.
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
from wer import corpus_wer, wer  # noqa: E402


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True)
    p.add_argument("--engine", choices=["native", "cli"], required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--lib-dir", help="native: dir containing libparakeet.* and ggml libs")
    p.add_argument("--cli", help="cli: path to parakeet-cli")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--out", default="benchmarks/results/engine_rtf.json")
    a = p.parse_args()

    if a.engine == "native":
        from engines.parakeet_native_engine import ParakeetNativeEngine
        engine = ParakeetNativeEngine(Path(a.lib_dir), Path(a.model))
    else:
        from engines.parakeet_engine import ParakeetEngine
        engine = ParakeetEngine(Path(a.cli), Path(a.model), SAMPLE_RATE, 2)

    m = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    base = Path(a.manifest).parent
    rows, rtfs = [], []
    first = to_pcm16(read_wav(base / m["clips"][0]["wav"]))
    t = time.perf_counter()
    await engine.transcribe_final(first)  # cold call, reported separately
    cold = time.perf_counter() - t
    for c in m["clips"]:
        x = read_wav(base / c["wav"])
        pcm, dur = to_pcm16(x), len(x) / SAMPLE_RATE
        times, text = [], ""
        for _ in range(a.repeats):
            t = time.perf_counter()
            text = await engine.transcribe_final(pcm)
            times.append(time.perf_counter() - t)
        rtf = float(np.median(times)) / dur
        rtfs.append(rtf)
        rows.append({"id": c["id"], "audio_s": dur, "median_s": float(np.median(times)), "rtf": rtf,
                     "tags": c.get("tags", {}), **wer(c["reference"], text)})
        print(f"{c['id']:<28} {dur:6.1f}s  median {np.median(times):6.3f}s  RTF {rtf:.3f}")
    summary = {"engine": a.engine, "cold_first_call_s": cold, "rtf_p50": float(np.median(rtfs)),
               "rtf_p95": float(np.percentile(rtfs, 95)), "wer": corpus_wer(rows)}
    print(json.dumps(summary, indent=2))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"summary": summary, "clips": rows}, indent=2), encoding="utf-8")
    shut = getattr(engine, "shutdown", None)
    if shut:
        r = shut()
        if asyncio.iscoroutine(r):
            await r


if __name__ == "__main__":
    asyncio.run(main())
