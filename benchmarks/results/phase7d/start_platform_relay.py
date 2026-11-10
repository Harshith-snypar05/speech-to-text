"""Staging relay launcher with the ScriptLiv platform (accounts, metering, sharing) wired in. :8772, staging only.
Same as start_redesign_relay.py, plus: SCRIPTLIV_API_URL / SCRIPTLIV_RELAY_SECRET / MONGODB_* from staging_secrets/api.env
(only those keys; the JWT secret stays with the API). Secrets are read from files and never printed.
Production relays (:8768/:8769) are not touched."""
import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
def load(name, only=None):
    for line in (ROOT / "staging_secrets" / name).read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            if only is None or k in only:
                os.environ[k] = v
# QA tester accounts, QA audio archive and QA diagnostics are intentionally NOT loaded: all accounts are normal customers.
load("api.env", {"MONGODB_URI", "MONGODB_DB", "SCRIPTLIV_API_URL", "SCRIPTLIV_RELAY_SECRET"})
for _k in [k for k in os.environ if k.startswith("STT_QA_")]:
    os.environ.pop(_k)
H = Path(__file__).resolve().parent
os.environ["STT_LISTEN_PORT"] = "8772"
# Customer sessions need a streaming engine. eou120m is the current staging default (override with STT_ENGINE).
os.environ.setdefault("STT_ENGINE", "eou120m")
# Second-pass text refinement with a Nemotron worker (:8781, own process; the live EOU path never waits for it).
# Set STT_REFINE_ENGINE= (empty) to turn it off. The jsonl log holds transcript text, so it stays under data/ on this machine.
os.environ.setdefault("STT_REFINE_ENGINE", "nemotron")
os.environ.setdefault("STT_REFINE_WORKER_URL", "ws://127.0.0.1:8781")
os.environ.setdefault("STT_REFINE_LOG_FILE", str(ROOT / "relays_phase7c" / "data" / "refine_log.jsonl"))
os.environ.setdefault("STT_SCHED_LOG_FILE", str(H / "redesign_sched.jsonl"))
os.environ.setdefault("STT_FLUSH_DIAG_FILE", str(H / "redesign_flush_diag.jsonl"))
assert os.environ.get("SCRIPTLIV_API_URL") and os.environ.get("SCRIPTLIV_RELAY_SECRET"), "api.env missing relay keys"
sys.path.insert(0, str(ROOT / "relays_phase7c"))
import asyncio, parakeet_relay  # noqa: E402
asyncio.run(parakeet_relay.main())
