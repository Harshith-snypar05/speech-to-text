"""Phase 7B measurement launcher (read-only investigation).

Imports the UNMODIFIED parakeet relay module (loads the same Parakeet TDT 0.6B v3 q8_0 model) and replaces
ONLY the two engine entry points on the engine INSTANCE, in this process, with timing copies that run the exact
same sequence the production methods run:
    samples = int16 -> float32 / 32768
    async with engine._call_lock: await loop.run_in_executor(engine._executor, engine._transcribe_sync, samples)
No production file is edited, scheduling is unchanged (same asyncio.Lock FIFO, same single-thread executor, same
partial cycle, same wait_for timeout in speaker_session). Only timestamps are added.

Per engine call, two JSONL records are written to STT_PHASE7B_LOG:
  kind=call: kind(final|partial), call id, n_samples, t_enq (call entered), t_lock (lock acquired), t_return
             (result returned or call cancelled), cancelled flag, active_calls_at_enq
  kind=job : call id, t_inf_start, t_inf_end (executor thread start/end of the real parakeet_full decode)
Queue wait = t_inf_start - t_enq (lock wait + executor hand-off). Inference = t_inf_end - t_inf_start.
A call that times out in speaker_session is cancelled at the await, but its executor job keeps running (and is
visible as a job record with no matching successful call return) -- that is measured here, not assumed.

Port 8770 (8768 = Phase 5 relay, 8769 = Phase 7 relay stay untouched).
"""
import asyncio, json, os, sys, threading, time
from pathlib import Path

RELAYS_DIR = Path(__file__).resolve().parents[3] / "relays"
sys.path.insert(0, str(RELAYS_DIR))

import numpy as np  # noqa: E402
import parakeet_relay  # noqa: E402  (loads the model)

LOG = Path(os.environ["STT_PHASE7B_LOG"])
PORT = 8770
_lock = threading.Lock()
_ids = iter(range(1, 10**9))
_active = 0
_fh = open(LOG, "a", encoding="utf-8", buffering=1)


def _w(rec):
    with _lock:
        _fh.write(json.dumps(rec) + "\n")


def install(engine):
    orig_sync = engine._transcribe_sync

    async def timed(kind, pcm_bytes):
        global _active
        cid = next(_ids)
        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        loop = asyncio.get_running_loop()
        rec = {"kind": "call", "id": cid, "type": kind, "n_samples": len(samples), "t_enq": time.monotonic(),
               "active_calls_at_enq": _active, "t_lock": None, "cancelled": False, "error": None}
        _active += 1

        def job():
            t0 = time.monotonic()
            try:
                return orig_sync(samples)
            finally:
                _w({"kind": "job", "id": cid, "t_inf_start": t0, "t_inf_end": time.monotonic()})

        try:
            async with engine._call_lock:
                rec["t_lock"] = time.monotonic()
                return await loop.run_in_executor(engine._executor, job)
        except asyncio.CancelledError:
            rec["cancelled"] = True
            raise
        except Exception as e:
            rec["error"] = repr(e)
            raise
        finally:
            _active -= 1
            rec["t_return"] = time.monotonic()
            _w(rec)

    async def transcribe_final(pcm_bytes):
        return await timed("final", pcm_bytes)

    async def transcribe_partial(pcm_bytes):
        return (await timed("partial", pcm_bytes)).split()

    engine.transcribe_final = transcribe_final
    engine.transcribe_partial = transcribe_partial


def main():
    install(parakeet_relay.engine)
    parakeet_relay.LISTEN_PORT = PORT
    asyncio.run(parakeet_relay.main())


if __name__ == "__main__":
    main()
