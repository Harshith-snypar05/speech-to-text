"""Phase 6: read-only replay of the five Phase 5 dropped_empty_text buffers through the SAME Parakeet q8_0
engine class (production class imported read-only, default params). No relay, no VAD, no WebSocket.

Exact buffer reconstruction (no estimation):
  ws_bench streams pcm = to_pcm16(read_wav(wav)) + 1.5 s zero tail, in 1600-sample chunks.
  The relay buffer is reset (take()) at every flush, so a flush buffer covers
      [end - buffer_samples, end)  with  end = audio_received_bytes / 2.
  diag stores audio_received_s = round(bytes/32000, 3) and exact buffer_samples. `end` is recovered as
  round(audio_received_s*16000) and asserted to be a multiple of the 1600-sample chunk (so the 3-decimal
  rounding cannot hide an offset), and the start must equal the previous flush end (or 0).
Verification: the reconstructed slice's sample count must equal buffer_samples, and replaying the relay's
RMS rule over the slice must give the recorded speech_s / silence_s.

Conditions: A exact slice; B/C/D = A with 0.5/1/2 s of audio immediately BEFORE the slice prepended (clipped at
sample 0). No right context. Each x3. Controls: the earlier flushes of the same connections that produced text
(condition A, x3) to show the replay reproduces the relay (same text length as recorded).
Output only under results/phase6_replay/. Inputs are read-only.
"""
import asyncio, json, sys, time, wave
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "relays"))
from audio_utils import read_wav, to_pcm16  # noqa: E402

SR = 16000
CHUNK = 1600  # ws_bench default chunk_ms=100
TAIL = int(1.5 * SR)  # ws_bench default tail_s
RMS_THR, HANG, MINU = 0.01, 0.6, 0.3
ROOT = HERE.parent
RES = HERE / "results"
OUT = RES / "phase6_replay"
LIB = ROOT / "whisper.cpp" / "build-shared" / "bin"
MODEL = ROOT / "whisper.cpp" / "models" / "ggml-parakeet-tdt-0.6b-v3-q8_0.bin"
REPS = 3
CONDS = {"A": 0.0, "B": 0.5, "C": 1.0, "D": 2.0}
SUFFIX = ["assamese_03817", "assamese_06152", "kannada_00197", "kashmiri_03111", "bodo_03621"]


def write_wav(path, pcm: bytes):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(SR); f.writeframes(pcm)


def vad_replay(pcm: bytes):
    """Relay UtteranceBuffer.add_chunk accounting over a slice (chunked by 1600 samples)."""
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    sp = si = 0.0
    for o in range(0, len(x), CHUNK):
        c = x[o:o + CHUNK]
        rms = float(np.sqrt(np.mean(c ** 2)))
        if rms < RMS_THR:
            si += len(c) / SR
        else:
            si = 0.0; sp += len(c) / SR
    return round(sp, 3), round(si, 3)


async def main():
    assert not OUT.exists(), "refusing to overwrite phase6_replay"
    (OUT / "audio").mkdir(parents=True)
    diag = [json.loads(l) for l in (RES / "phase5_flush_diag.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    by_conn = {}
    for r in diag:
        by_conn.setdefault(r["conn_id"], []).append(r)
    for v in by_conn.values():
        v.sort(key=lambda r: r["seq"])
    man = json.loads((RES / "phase5_manifest.json").read_text(encoding="utf-8"))["clips"]
    full = {c["id"]: c for c in json.loads((RES / "svarah_offline_fullclip.json").read_text(encoding="utf-8"))["clips"]}
    # phase5 runs: conns (2..7), (9..14), (16..21) = manifest order [assamese_03817, assamese_06152, bengali, bodo, kannada, kashmiri]
    order = [c["id"] for c in man]
    runs = {1: 2, 2: 9, 3: 16}
    # boundary stability across the three diagnostic runs
    stable = True
    for i in range(6):
        sig = [[(r["audio_received_s"], r["buffer_samples"], r["outcome"]) for r in by_conn[b + i]] for b in runs.values()]
        stable &= sig[0] == sig[1] == sig[2]
    print("flush boundaries identical across the 3 Phase 5 runs:", stable)

    from engines.parakeet_native_engine import ParakeetNativeEngine
    eng = ParakeetNativeEngine(LIB, MODEL)

    async def decode(pcm: bytes):
        t = time.perf_counter()
        txt = await eng.transcribe_final(pcm)
        return txt, round(time.perf_counter() - t, 4)

    await decode(to_pcm16(read_wav(man[0]["wav"]))[:96000])  # warm-up, as in svarah_offline_decode.py

    results = []
    for suf in SUFFIX:
        idx = next(i for i, cid in enumerate(order) if cid.startswith("svarah_" + suf))
        clip = man[idx]
        conn = 2 + idx  # Phase 5 run 1
        recs = by_conn[conn]
        pcm = to_pcm16(read_wav(clip["wav"])) + bytes(TAIL * 2)
        n_total = len(pcm) // 2
        samples = np.frombuffer(pcm, dtype=np.int16)
        prev_end = 0
        flushes = []
        for r in recs:
            end = round(r["audio_received_s"] * SR)
            start = end - r["buffer_samples"]
            ok = {"end_multiple_of_chunk": end % CHUNK == 0 or end == n_total,
                  "start_equals_previous_end": start == prev_end,
                  "within_stream": 0 <= start < end <= n_total}
            flushes.append((r, start, end, ok))
            prev_end = end
        dropped = [f for f in flushes if f[0]["outcome"] == "dropped_empty_text"]
        assert len(dropped) == 1, (suf, [f[0]["outcome"] for f in flushes])
        cl = {"clip": clip["id"], "phase5_conn_run1": conn,
              "phase3_fullclip_text": full[clip["id"]]["text"], "phase3_fullclip_duration_s": full[clip["id"]]["duration_s"],
              "flush_table": [], "dropped": None, "controls": []}

        async def run_slice(tag, start, end, ctx_s, reps):
            cs = max(0, start - int(ctx_s * SR))
            seg = samples[cs:end].tobytes()
            p = OUT / "audio" / f"{suf}_{tag}.wav"
            write_wav(p, seg)
            rr = []
            for k in range(reps):
                txt, ds = await decode(seg)
                rr.append({"rep": k + 1, "text": txt, "empty": txt == "", "decode_s": ds})
            return {"tag": tag, "wav": str(p.relative_to(OUT)), "start_sample": cs, "end_sample": end,
                    "context_samples": start - cs, "sample_count": end - cs, "duration_s": round((end - cs) / SR, 4),
                    "reps": rr}

        for r, s, e, ok in flushes:
            cl["flush_table"].append({"seq": r["seq"], "outcome": r["outcome"], "reason": r["reason"], "start_sample": s, "end_sample": e,
                                      "buffer_samples": r["buffer_samples"], "speech_s": r["speech_s"], "checks": ok})
        r, s, e, ok = dropped[0]
        slice_pcm = samples[s:e].tobytes()
        sp, si = vad_replay(slice_pcm)
        ver = {"sample_count_matches_buffer_samples": (e - s) == r["buffer_samples"],
               "sample_rate": SR,
               "duration_matches_buffer_s": round((e - s) / SR, 3) == r["buffer_s"],
               "vad_replay_speech_s": sp, "recorded_speech_s": r["speech_s"],
               "vad_replay_silence_s": si, "recorded_silence_s": r["silence_s"],
               "vad_matches_record": (sp == round(r["speech_s"], 3) and si == round(r["silence_s"], 3)),
               "boundary_checks": ok}
        cl["dropped"] = {"seq": r["seq"], "reason": r["reason"], "start_sample": s, "end_sample": e, "start_s": round(s / SR, 4),
                         "end_s": round(e / SR, 4), "buffer_samples": r["buffer_samples"], "verification": ver, "conditions": {}}
        for cname, cs in CONDS.items():
            cl["dropped"]["conditions"][cname] = await run_slice(f"dropped_{cname}", s, e, cs, REPS)
            reps = cl["dropped"]["conditions"][cname]["reps"]
            print(suf, cname, [("EMPTY" if x["empty"] else f"{len(x['text'].split())}w") for x in reps], flush=True)
        # controls: earlier flushes that produced text (A only)
        for r2, s2, e2, ok2 in flushes:
            if r2["outcome"] == "final_sent":
                c = await run_slice(f"control_seq{r2['seq']}_A", s2, e2, 0.0, REPS)
                c["seq"] = r2["seq"]; c["recorded_text_len"] = r2["text_len"]
                c["replay_text_len_matches_record"] = [len(x["text"]) == r2["text_len"] for x in c["reps"]]
                cl["controls"].append(c)
                print(suf, "control seq", r2["seq"], c["replay_text_len_matches_record"], flush=True)
        results.append(cl)

    (OUT / "phase6_replay_results.json").write_text(json.dumps(
        {"engine": "ParakeetNativeEngine (production class, default params)", "model": str(MODEL),
         "phase5_boundaries_identical_across_runs": stable, "reps": REPS, "conditions": CONDS, "clips": results},
        indent=1, ensure_ascii=False), encoding="utf-8")
    print("wrote", OUT / "phase6_replay_results.json")


if __name__ == "__main__":
    asyncio.run(main())
