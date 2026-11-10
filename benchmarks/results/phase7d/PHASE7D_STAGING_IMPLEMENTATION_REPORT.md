# Phase 7D staging implementation report

Status: staging validated at protocol level. **The Flutter app was not run** (no device/mic/screen available to me). Nothing merged or deployed. Production relays (PID 67396 :8768, PID 40624 :8769), `relays/`, and `svarah_wer.json` (md5 ccb7fbcf...) verified untouched after the run.

## Commits (`relays_phase7c/`, branch `phase7d-staging`)
- `874b131` Phase 7C baseline copy; `387525e` Phase 7C scheduler (reviewed unchanged: 11 files +1278/-31, 29 tests)
- `90a8913` QA access layer; `2e462cf` fix (token field on `ConnectionParams`, missing in first commit, found by live run; regression test added)
- Tests: 150 passed, 1 skipped (135+1 from 7C, +15 new in `tests/test_phase7d_qa.py`).

## What was built (all behind `STT_QA_ENABLED=1`; default off = 7C behaviour)
- `core/qa.py`: allowlist of max 3 accounts (scrypt hashes), HMAC bearer tokens with expiry, login lockout (5 fails / 5 min), consent record, session-to-account binding, AES-256-GCM chunked audio (AAD = session|connection|frame) and encrypted transcript text, audit table, retention purge, account data deletion, event log (finals, drops with outcome, partial counts) per account/session/connection.
- `core/qa_http.py`: `/qa/login`, `/qa/consent`, `/qa/consent/accept`, `/qa/sessions`, `/qa/sessions/<id>/transcript|audio`, served from the relay's `process_request`. Other-account and nonexistent session give identical 404.
- `parakeet_relay.py`: `STT_LISTEN_PORT` env (default 8768), QA gate on speaker WebSocket (4401 no/bad token, 4403 no consent or session owned by another account). `core/speaker_session.py`: optional `qa=` hooks (audio tee, final, drop, partial); hook failures are swallowed (tested). `core/protocol.py`: `token` query param.
- `qa_admin.py`: provision, audit, sessions, purge, delete-account (server-side only; actor `cli:<user>`, audited).
- Flutter (not in git; not compiled on a device): `auth_service.dart` (backend login when built with `--dart-define=QA_BACKEND_HTTP=...`, token memory-only), `auth_gate.dart` (consent screen), `transcription_client.dart` + `session_screen.dart` (send token), `pubspec.yaml` (+`http`). `dart analyze` clean in a scratch copy with the SDK constraint lowered (installed Dart 3.12.2 < pubspec `^3.13.7`; real build needs a newer SDK).

## Not changed (constraints)
Parakeet engine/decoder params, VAD, segmentation, scheduler logic, empty-decode handling. No retries added.

## Staging run
`benchmarks/results/phase7d/start_phase7d_relay.py` on :8772 (own `data/`, `staging_data_qa/`, CPU build). Secrets in `staging_secrets/` (outside repo): per-account passwords (`passwords.txt`, hand out then delete), token secret, audio key.

## Gaps / not done (be explicit)
- Real Flutter client on three accounts/devices: **not done**. My client (`qa_scenarios.py`) speaks the same wire protocol at real-time pace.
- Real tester consent: **not obtained**. Consent in tests was accepted programmatically for the test accounts; real consent needs the testers to tap it in the app.
- Flutter has no session-history, playback, or download UI; download works over the backend API only.
- Key management: audio key lives in `qa.env` on the same host (no KMS/rotation). Retention default 30 days is my proposal, not agreed.
- Transport: plain `ws://`/`http://` on localhost; production use needs TLS. Token travels in the WebSocket query string (do not log it; `combined_proxy.py` logs the path, so do not front staging with it as is). Login is GET+Basic because `process_request` has no body. Flutter web would need CORS (not added); use native builds.
- Hardcoded plaintext test accounts remain in `auth_service.dart` for non-QA builds (pre-existing; unused in QA mode).
