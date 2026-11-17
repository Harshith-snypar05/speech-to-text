"""Local manual test page for nvidia/canary-qwen-2.5b. Run with asr_venv python; open http://127.0.0.1:7860"""
import json, os, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import soundfile as sf
import torch
from nemo.collections.speechlm2.models import SALM

HERE = os.path.dirname(os.path.abspath(__file__))
t0 = time.time()
model = SALM.from_pretrained("nvidia/canary-qwen-2.5b").eval().to(torch.bfloat16).to("cuda")
print(f"model ready in {time.time() - t0:.0f}s, vram {torch.cuda.memory_allocated() / 1e9:.1f} GB", flush=True)
lock = threading.Lock()

# fast live engine: Parakeet TDT 0.6b (English). Canary stays the accurate second pass.
import nemo.collections.asr as nemo_asr
t1 = time.time()
fast = nemo_asr.models.ASRModel.from_pretrained("nvidia/parakeet-tdt-0.6b-v2", map_location="cuda").eval()
try:
    fast = fast.to(torch.bfloat16)
    probe = os.path.join(HERE, "_probe.wav")
    sf.write(probe, [0.0] * 16000, 16000)
    fast.transcribe([probe])
    os.remove(probe)
    print("parakeet bf16 ok", flush=True)
except Exception as e:
    print("parakeet bf16 failed, using fp32:", type(e).__name__, str(e)[:200], flush=True)
    fast = fast.float()
fast_lock = threading.Lock()
print(f"parakeet ready in {time.time() - t1:.0f}s, total vram {torch.cuda.memory_allocated() / 1e9:.1f} GB", flush=True)


def transcribe_fast(path):
    out = fast.transcribe([path], verbose=False)
    r = out[0] if isinstance(out, (list, tuple)) else out
    return (getattr(r, "text", r) or "").strip()


def transcribe(path):
    ids = model.generate(
        prompts=[[{"role": "user", "content": f"Transcribe the following: {model.audio_locator_tag}", "audio": [path]}]],
        max_new_tokens=512)
    return model.tokenizer.ids_to_text(ids[0].cpu())


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        with open(os.path.join(HERE, "index.html"), "rb") as f:
            self._send(200, f.read(), "text/html; charset=utf-8")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(n)
        fd, p = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            with open(p, "wb") as f:
                f.write(data)
            info = sf.info(p)
            dur = info.duration
            if dur > 40:
                return self._send(400, json.dumps({"error": f"clip is {dur:.0f}s; model max is 40s"}))
            use_fast = self.path.startswith("/fast")
            with (fast_lock if use_fast else lock):
                s = time.time()
                text = transcribe_fast(p) if use_fast else transcribe(p)
                torch.cuda.synchronize()
                el = time.time() - s
            print(f"[{'parakeet' if use_fast else 'canary'} {dur:.1f}s audio, {el:.2f}s] {text}", flush=True)
            self._send(200, json.dumps({"text": text, "audio_s": round(dur, 2), "infer_s": round(el, 2)}))
        except Exception as e:
            self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}))
        finally:
            os.remove(p)


print("open http://127.0.0.1:7860", flush=True)
ThreadingHTTPServer(("127.0.0.1", 7860), H).serve_forever()
