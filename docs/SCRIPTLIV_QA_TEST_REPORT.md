> **Historical (retired).** This report covers the removed QA tooling and the earlier QA-era test suites. Current results: `SCRIPTLIV_RELEASE_READINESS.md`.

# ScriptLiv QA Test Report (Phase H)

## What was run
| Suite | Where | Result |
|---|---|---|
| Backend unit/integration | `relays_phase7c` | 165 passed, 1 skipped |
| Three-account protocol E2E with **real Parakeet** | `benchmarks/results/redesign/e2e_three_accounts.py` | 69 / 69 |
| Browser E2E (Playwright Chromium, **fake mic**) | `benchmarks/results/redesign/browser_e2e.py` | 16 / 16 |
| Flutter `flutter analyze` (scratch copy) | `scratch_flutter_check` | 0 errors, 5 info lints |
| Flutter `flutter test` (scratch copy) | same | 61 passed |
| Website vitest / lint / typecheck | `scriptliv_web` | passing at last run |

Staging relay: `benchmarks/results/phase7d/start_redesign_relay.py` on :8772.

## Covered
Login, wrong password, consent gate, tester cannot see or reach `/console`, admin sees all three accounts, tester sees only own sessions, audio link authorisation and audit, recording state only after mic + socket, final lines appear, partial cleared on stop, no horizontal scroll at 1366 and 390 px.

## Not covered / caveats
- 69/69 is a **protocol-level** test, not a phone test. Browser run used a fake microphone.
- Real tester consent was not collected; the harness accepted consent at protocol level.
- No capacity claim: three accounts cannot support one.
- Flutter tests ran in a scratch copy with the SDK constraint lowered to `^3.12.0`.
- 5 info lints in Flutter remain unfixed.
- Screenshots: `benchmarks/results/redesign/shots/`.
