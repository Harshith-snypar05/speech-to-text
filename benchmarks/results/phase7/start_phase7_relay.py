"""Phase 7 benchmark relay launcher.

Starts the UNMODIFIED parakeet relay on port 8769 so a Phase 7 benchmark
can run with Phase 7 diagnostics while Phase 5's relay keeps port 8768 and
its own diagnostics file (`results/phase5_flush_diag.jsonl`) untouched.

parakeet_relay.py hardcodes `LISTEN_PORT = 8768` and reads that module
global inside main(), so this imports the module (which loads the model,
exactly as running it directly would) and overrides the attribute before
main() runs. No production file is edited, no VAD/config/relay behaviour
changes -- same code path, same defaults.

Usage (from anywhere):
    STT_FLUSH_DIAG_FILE=<phase7>/phase7_flush_diag.jsonl \
        python start_phase7_relay.py
"""
import asyncio
import sys
from pathlib import Path

RELAYS_DIR = Path(__file__).resolve().parents[3] / "relays"
sys.path.insert(0, str(RELAYS_DIR))

import parakeet_relay  # noqa: E402  (module import loads the model)

PORT = 8769


def main():
    parakeet_relay.LISTEN_PORT = PORT
    asyncio.run(parakeet_relay.main())


if __name__ == "__main__":
    main()
