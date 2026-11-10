"""Phase 6C: read-only follow-up to Phase 6. Same production ParakeetNativeEngine class (Parakeet TDT 0.6B v3 q8_0,
default params), imported read-only. No relay, no VAD, no WebSocket; the running diagnostic relay is not touched.

Inputs (read-only): results/phase6_replay/phase6_replay_results.json (exact sample boundaries of the dropped slices
and of earlier flushes), results/phase5_manifest.json (WAV paths), results/svarah_offline_fullclip.json.
Output only under results/phase6c/.

Experiments (each variant x3 repetitions; exact sample boundaries recorded):
  1 zero-padded left context 0.5/1/2 s on the exact slice (no real audio added).
  2 slice-start shifts -200,-100,-50,+50,+100,+200 ms, endpoint unchanged, nothing prepended.
  3 Kannada slice-length sweep (left/right truncation, trailing-silence trim, longer real left context) and a
    read-only dump of the decoder default parameters.
  4 overlap: previous finals are re-derived by replaying the earlier flushes (condition A, as the relay did);
    every non-empty recovered text (Phase 6 B/C/D and Phase 6C variants) is compared with the previous final.
"""
import asyncio, ctypes, difflib, json, re, sys, time, wave
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "relays"))
from audio_utils import read_wav, to_pcm16  # noqa: E402

SR = 16000
TAIL = int(1.5 * SR)
REPS = 3
RES = HERE / "results"
OUT = RES / "phase6c"
ROOT = HERE.parent
LIB = ROOT / "whisper.cpp" / "build-shared" / "bin"
MODEL = ROOT / "whisper.cpp" / "models" / "ggml-parakeet-tdt-0.6b-v3-q8_0.bin"
SUF = ["assamese_03817", "assamese_06152", "kannada_00197", "kashmiri_03111", "bodo_03621"]


def write_wav(path, pcm: bytes):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(SR); f.writeframes(pcm)


def words(t):
    return [w for w in (re.sub(r"[^a-z0-9]", "", x.lower()) for x in t.split()) if w]


def overlap(prev_text, rec_text, full_text):
    P, R, F = words(prev_text), words(rec_text), words(full_text)
    if not R:
        return None
    k = 0
    for kk in range(min(len(R), len(P)), 0, -1):
        if R[:kk] == P[-kk:]:
            k = kk; break
    sm = difflib.SequenceMatcher(None, P[-(len(R) + 3):], R, autojunk=False)
    fuzzy = sum(b.size for b in sm.get_matching_blocks() if b.size >= 2)
    smf = difflib.SequenceMatcher(None, F, R, autojunk=False)
    infull = sum(b.size for b in smf.get_matching_blocks() if b.size >= 2)
    return {"recovered_words": len(R), "exact_leading_dup_words": k, "fuzzy_words_matching_previous_final_tail": fuzzy,
            "novel_words_est": len(R) - fuzzy, "words_in_fullclip_blocks": infull}


async def main():
    assert not OUT.exists(), "refusing to overwrite phase6c"
    (OUT / "audio").mkdir(parents=True)
    p6 = json.loads((RES / "phase6_replay" / "phase6_replay_results.json").read_text(encoding="utf-8"))
    man = {c["id"]: c for c in json.loads((RES / "phase5_manifest.json").read_text(encoding="utf-8"))["clips"]}

    from engines.parakeet_native_engine import ParakeetNativeEngine, _SAMPLING_GREEDY
    from core.transcript_manager import collapse_repetition
    eng = ParakeetNativeEngine(LIB, MODEL)
    lib, ctx = eng._lib, eng._ctx

    # --- decoder default parameters (read-only inspection) ---
    fp = lib.parakeet_full_default_params(_SAMPLING_GREEDY)
    params = {f[0]: (getattr(fp, f[0]) if f[1] in (ctypes.c_int, ctypes.c_bool) else None) for f in fp._fields_
              if f[1] in (ctypes.c_int, ctypes.c_bool)}
    params["new_segment_callback/others"] = "NULL (not set)"

    def raw_decode(samples_f32):
        ptr = samples_f32.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        p = lib.parakeet_full_default_params(_SAMPLING_GREEDY)  # identical to ParakeetNativeEngine._transcribe_sync
        ret = lib.parakeet_full(ctx, p, ptr, len(samples_f32))
        if ret != 0:
            raise RuntimeError(f"parakeet_full returned {ret}")
        n = lib.parakeet_full_n_segments(ctx)
        parts = []
        for i in range(n):
            t = lib.parakeet_full_get_segment_text(ctx, i)
            if t:
                parts.append(t.decode("utf-8", errors="replace"))
        raw = " ".join(parts).strip()
        return collapse_repetition(raw), raw, n

    loop = asyncio.get_running_loop()

    async def decode(pcm: bytes):
        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        async with eng._call_lock:
            t = time.perf_counter()
            txt, raw, n = await loop.run_in_executor(eng._executor, raw_decode, x)
            return txt, raw, n, round(time.perf_counter() - t, 4)

    await decode(to_pcm16(read_wav(man[p6["clips"][0]["clip"]]["wav"]))[:96000])  # warm-up

    async def run_variant(name, samples, lead_zeros, a, b, store):
        seg = bytes(lead_zeros * 2) + samples[a:b].tobytes()
        wav = f"audio/{store['_suf']}_{name}.wav"
        write_wav(OUT / wav, seg)
        reps = []
        for k in range(REPS):
            txt, raw, n, ds = await decode(seg)
            reps.append({"rep": k + 1, "text": txt, "raw_text": raw, "n_segments": n, "empty": txt == "", "decode_s": ds})
        rec = {"name": name, "wav": wav, "lead_zero_samples": lead_zeros, "src_start_sample": a, "src_end_sample": b,
               "sample_count": lead_zeros + (b - a), "duration_s": round((lead_zeros + b - a) / SR, 4),
               "reps_identical": len({r["text"] for r in reps}) == 1, "reps": reps}
        return rec

    out_clips = []
    for suf in SUF:
        c6 = next(c for c in p6["clips"] if c["clip"].startswith("svarah_" + suf))
        cid = c6["clip"]
        s, e = c6["dropped"]["start_sample"], c6["dropped"]["end_sample"]
        samples = np.frombuffer(to_pcm16(read_wav(man[cid]["wav"])) + bytes(TAIL * 2), dtype=np.int16)
        full_text = c6["phase3_fullclip_text"]
        store = {"_suf": suf}
        cl = {"clip": cid, "dropped_slice": {"start_sample": s, "end_sample": e, "samples": e - s},
              "exp1_zero_pad": [], "exp2_shifts": [], "exp3_sweep": [], "previous_finals": [], "exp4_overlap": []}

        # regression check: exact slice A reproduces Phase 6
        a_rec = await run_variant("regress_A", samples, 0, s, e, store)
        cl["regress_exact_slice"] = {**a_rec, "phase6_A_empty": all(r["empty"] for r in c6["dropped"]["conditions"]["A"]["reps"])}

        for pad_s in (0.5, 1.0, 2.0):  # Exp 1
            n = int(pad_s * SR)
            v = await run_variant(f"zeropad_{pad_s}s", samples, n, s, e, store); v["pad_s"] = pad_s
            cl["exp1_zero_pad"].append(v)
            print(suf, "pad", pad_s, [("EMPTY" if r["empty"] else f"{len(r['text'].split())}w") for r in v["reps"]], flush=True)

        for d_ms in (-200, -100, -50, 50, 100, 200):  # Exp 2
            a = s + d_ms * SR // 1000
            v = await run_variant(f"shift_{d_ms:+d}ms", samples, 0, a, e, store); v["shift_ms"] = d_ms
            cl["exp2_shifts"].append(v)
            print(suf, "shift", d_ms, [("EMPTY" if r["empty"] else f"{len(r['text'].split())}w") for r in v["reps"]], flush=True)

        if suf == "kannada_00197":  # Exp 3
            sweep = []
            for k in (1, 2, 3, 4):
                sweep.append(("left_trunc", f"lefttrunc_{k*0.5}s", 0, s + k * 8000, e))
            for k in (1, 2, 3, 4):
                sweep.append(("right_trunc", f"righttrunc_{k*0.5}s", 0, s, e - k * 8000))
            sweep.append(("silence_trim", "righttrunc_0.6s_hang", 0, s, e - 9600))
            for ctx_s in (3, 4, 6, 8):
                sweep.append(("real_left_context", f"realctx_{ctx_s}s", 0, s - ctx_s * SR, e))
            for kind, nm, lz, a, b in sweep:
                v = await run_variant(nm, samples, lz, a, b, store); v["kind"] = kind
                cl["exp3_sweep"].append(v)
                print(suf, nm, [("EMPTY" if r["empty"] else f"{len(r['text'].split())}w") for r in v["reps"]], flush=True)
            # energy profile (100 ms RMS) of the dropped slice
            x = samples[s:e].astype(np.float32) / 32768.0
            cl["exp3_energy_100ms_rms"] = [round(float(np.sqrt(np.mean(x[i:i + 1600] ** 2))), 4) for i in range(0, len(x), 1600)]

        # Exp 4: previous finals = replay of the earlier final_sent flushes (condition A, as the relay did)
        for f in c6["flush_table"]:
            if f["outcome"] == "final_sent":
                v = await run_variant(f"prevfinal_seq{f['seq']}", samples, 0, f["start_sample"], f["end_sample"], store)
                v["seq"] = f["seq"]; v["recorded_text_len"] = next(
                    ctl["recorded_text_len"] for ctl in c6["controls"] if ctl["seq"] == f["seq"])
                v["replay_len_matches_record"] = [len(r["text"]) == v["recorded_text_len"] for r in v["reps"]]
                cl["previous_finals"].append(v)
        prev = cl["previous_finals"][-1]["reps"][0]["text"] if cl["previous_finals"] else ""
        cl["previous_final_used"] = {"seq": cl["previous_finals"][-1]["seq"] if cl["previous_finals"] else None, "text": prev}
        cands = []
        for cn, cv in c6["dropped"]["conditions"].items():
            if cn != "A" and not cv["reps"][0]["empty"]:
                cands.append((f"phase6_{cn}_real_ctx_{ {'B':0.5,'C':1,'D':2}[cn] }s", cv["reps"][0]["text"], cv["start_sample"]))
        for grp in ("exp1_zero_pad", "exp2_shifts", "exp3_sweep"):
            for v in cl[grp]:
                if not v["reps"][0]["empty"]:
                    cands.append((f"phase6c_{v['name']}", v["reps"][0]["text"], v["src_start_sample"]))
        for nm, txt, st in cands:
            o = overlap(prev, txt, full_text)
            o.update(name=nm, text=txt, source_start_sample=st, starts_before_slice=st < s)
            cl["exp4_overlap"].append(o)
        out_clips.append(cl)

    (OUT / "phase6c_results.json").write_text(json.dumps(
        {"engine": "ParakeetNativeEngine (production class, default params)", "model": str(MODEL), "reps": REPS,
         "decoder_default_params": params,
         "model_hparams_from_relay_log": {"n_audio_ctx": 5000, "n_mels": 128, "n_fft": 512},
         "clips": out_clips}, indent=1, ensure_ascii=False), encoding="utf-8")
    print("wrote", OUT / "phase6c_results.json")


if __name__ == "__main__":
    asyncio.run(main())
