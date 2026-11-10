# Phase 7C: modified files and commit identifiers

Repo: `relays_phase7c/` (isolated copy; the project root is not a git repo). Nothing merged, nothing deployed.

| Commit | Meaning |
|---|---|
| `874b131` | Phase 7C baseline: verbatim copy of `relays/` (pre-change) |
| `387525e` | Phase 7C: finals-first scheduler, partial backpressure, final deadlines, dropped-final accounting |

Files changed in `387525e` (diffstat vs `874b131`, 11 files, +1278/-31):
- `core/scheduler.py` (new, 319)
- `core/config.py`, `core/flush_diagnostics.py`, `core/speaker_session.py`
- `engines/base_engine.py`, `engines/parakeet_native_engine.py`
- `tests/test_phase7c_scheduler.py` (new, 536), `tests/test_engines.py`, `tests/test_phase7_asr.py`
- `supervisor.py`, `combined_proxy.py` (copied unchanged from `relays/` so the copy's tests import)

Untouched: `relays/` (equal to `874b131` apart from CRLF), production relays PID 67396 (:8768) and PID 40624 (:8769), `svarah_wer.json` (md5 CCB7FBCF1C434DE7EAABD70BE12EF6C4), `phase5_flush_diag.jsonl` (87 lines), Phase 5/6/6C/7/7B artifacts.

Benchmark-side (not in git), all in `benchmarks/results/phase7c/`: launcher `start_phase7c_relay.py`, `run_matrix.sh`, `run_drift_baseline.sh`, `run_ab.sh`, `sampler.py`, analysis scripts, manifests, raw logs and reports.
Test relays used: :8771 (Phase 7C copy), :8770 (unmodified baseline control). Both stopped; ports free.
