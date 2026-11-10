"""Harness self-test. Spins up a MOCK relay (fake deterministic engine, the
real UtteranceBuffer VAD loaded by file path) and runs ws_bench against it
with synthetic tone-burst "speech", then checks the numbers the harness
reports against values known by construction.

This validates the MEASURING INSTRUMENT only. It says nothing about
Parakeet. It needs no model, GPU or recordings:  python selftest.py
"""
import asyncio
import importlib.util
import json
import sys
import tempfile
from argparse import Namespace
from pathlib import Path

import numpy as np
import websockets

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ws_bench  # noqa: E402
from audio_utils import SAMPLE_RATE, write_wav  # noqa: E402

spec = importlib.util.spec_from_file_location("audio_processor", HERE.parent / "relays" / "core" / "audio_processor.py")
ap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ap)

VOCAB = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima".split()
WORD_S, GAP_S, UTT_GAP_S = 0.35, 0.05, 1.2
FINAL_DELAY_S, PARTIAL_DELAY_S = 0.13, 0.05
ERR_EVERY = 5  # 5th word of each 8-word clip wrong in finals -> WER = 1/8 = 12.5% by construction


def make_clip(path: Path, words_per_utt: list[int]):
    rng = np.random.default_rng(1)
    parts, ref, idx = [np.zeros(int(0.5 * SAMPLE_RATE), np.float32)], [], 0
    for n in words_per_utt:
        for _ in range(n):
            t = np.arange(int(WORD_S * SAMPLE_RATE)) / SAMPLE_RATE
            parts.append((0.2 * np.sin(2 * np.pi * (200 + 30 * (idx % 7)) * t)).astype(np.float32))
            parts.append(np.zeros(int(GAP_S * SAMPLE_RATE), np.float32))
            ref.append(VOCAB[idx % len(VOCAB)])
            idx += 1
        parts.append(np.zeros(int(UTT_GAP_S * SAMPLE_RATE), np.float32))
    write_wav(path, np.concatenate(parts))
    return " ".join(ref)


def n_words(pcm: bytes) -> int:
    x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
    fr = len(x) // 320
    rms = np.sqrt(np.mean(x[:fr * 320].reshape(fr, 320) ** 2, axis=1))
    return int(round((rms > 0.01).sum() * 0.02 / (WORD_S + GAP_S - 0.0)))  # ~one word per 0.4 s


async def mock_handler(ws):
    buf = ap.UtteranceBuffer(SAMPLE_RATE, 2, 0.01, 0.6, 0.3, 8.0)
    emitted, gen, sent = 0, 0, 0

    async def send(text, partial):
        await ws.send(json.dumps({"text": text, "partial": partial}))

    async def partials():
        nonlocal sent
        k = 0
        while True:
            await asyncio.sleep(0.5)
            if not buf.has_pending_utterance():
                continue
            g = gen
            words = [VOCAB[(emitted + i) % len(VOCAB)] for i in range(n_words(bytes(buf.buffer)))]
            await asyncio.sleep(PARTIAL_DELAY_S)
            if g != gen or len(words) <= sent:
                continue
            k += 1
            new = words[sent:]
            if k % 3 == 0:
                new[-1] = "zz"  # a partial the final will contradict -> counted as a revision
            sent = len(words)
            await send(" ".join(new), True)

    task = asyncio.create_task(partials())
    try:
        async for m in ws:
            if isinstance(m, str):
                continue
            if buf.add_chunk(m):
                gen += 1
                sent = 0
                snap = buf.take()
                await asyncio.sleep(FINAL_DELAY_S)
                n = n_words(snap)
                words = []
                for i in range(n):
                    g_idx = emitted + i
                    words.append("xx" if (g_idx + 1) % ERR_EVERY == 0 else VOCAB[g_idx % len(VOCAB)])
                emitted += n
                await send(" ".join(words), False)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        task.cancel()


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="bench_selftest_"))
    clips = []
    for cid, shape in (("a", [4, 4]), ("b", [5, 3])):
        ref = make_clip(tmp / f"{cid}.wav", shape)
        clips.append({"id": cid, "wav": f"{cid}.wav", "reference": ref, "tags": {"kind": "synthetic"}})
    (tmp / "manifest.json").write_text(json.dumps({"clips": clips}))

    async with websockets.serve(mock_handler, "localhost", 0, max_size=None) as server:
        port = server.sockets[0].getsockname()[1]
        args = Namespace(manifest=str(tmp / "manifest.json"), url=f"ws://localhost:{port}/?role=speaker",
                         out=str(tmp / "out.json"), concurrency="1,2", chunk_ms=100, tail_s=1.5, hang_s=0.6,
                         drain_s=5.0, rms_threshold=0.01, max_utt_s=8.0, adaptive=False, noise_mult=2.5, stagger=0.3, warmup=1, relay_pid=None, seed=0, note="selftest")
        await ws_bench.amain(args)

    rep = json.loads((tmp / "out.json").read_text())
    s1, s2 = rep["levels"][0]["summary"], rep["levels"][1]["summary"]
    checks = {
        "all utterances finalized (N=1)": s1["segment_mismatch_clips"] == 0,
        "all utterances finalized (N=2)": s2["segment_mismatch_clips"] == 0,
        "no stream errors": not rep["levels"][0]["errors"] and not rep["levels"][1]["errors"],
        "WER == 12.5% by construction": s1["wer"]["wer"] is not None and abs(s1["wer"]["wer"] - 0.125) < 1e-9,
        "after-hang final latency in [0.05, 0.45]s": s1["final_latency_after_hang_s"]["p50"] is not None
        and 0.05 <= s1["final_latency_after_hang_s"]["p50"] <= 0.45,
        "partials were produced": s1["first_partial_s"]["n"] > 0,
        "revisions detected (>0)": (s1["partial_revision_rate"] or 0) > 0,
        "N=2 saw twice the clips": s2["clips"] == 2 * s1["clips"],
    }
    print("\nSELFTEST")
    for k, ok in checks.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {k}")
    sys.exit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    asyncio.run(main())
