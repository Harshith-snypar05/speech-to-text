"""Phase 3 evidence pass: offline full-clip decode of the 60 Svarah clips with the SAME Parakeet q8_0 engine
(production class imported read-only, default params). Not a benchmark rerun: no WebSocket, no VAD, no relay.
Output is a NEW file; results/svarah_wer.json is never touched. No reference text is read or written."""
import argparse, asyncio, json, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "relays"))
from audio_utils import read_wav, to_pcm16  # noqa: E402


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True); ap.add_argument("--lib-dir", required=True)
    ap.add_argument("--model", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out_p = Path(a.out)
    assert not out_p.exists(), "refusing to overwrite"
    from engines.parakeet_native_engine import ParakeetNativeEngine
    eng = ParakeetNativeEngine(Path(a.lib_dir), Path(a.model))
    m = json.loads(Path(a.manifest).read_text(encoding="utf-8")); base = Path(a.manifest).parent
    res = []
    await eng.transcribe_final(to_pcm16(read_wav(base / m["clips"][0]["wav"]))[:96000])  # warm-up
    for c in m["clips"]:
        x = read_wav(base / c["wav"]); t = time.perf_counter()
        txt = await eng.transcribe_final(to_pcm16(x))
        res.append(dict(id=c["id"], duration_s=len(x) / 16000, text=txt, decode_s=time.perf_counter() - t))
        print(c["id"][:40], len(txt.split()), flush=True)
    out_p.write_text(json.dumps(dict(engine="ParakeetNativeEngine", model=a.model, clips=res), indent=1, ensure_ascii=False), encoding="utf-8")
if __name__ == "__main__":
    asyncio.run(main())
