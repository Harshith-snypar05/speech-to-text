"""Phase 7C relay launcher (isolated copy, port 8771). Imports relays_phase7c/parakeet_relay.py UNMODIFIED
apart from the Phase 7C scheduler work in that copy, and only overrides the listen port.
Env: STT_SCHED_LOG_FILE, STT_FLUSH_DIAG_FILE (raw timing logs)."""
import asyncio, sys
from pathlib import Path

RELAYS = Path(__file__).resolve().parents[3] / "relays_phase7c"
sys.path.insert(0, str(RELAYS))
import parakeet_relay  # noqa: E402

parakeet_relay.LISTEN_PORT = 8771
asyncio.run(parakeet_relay.main())
