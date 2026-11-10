# Phase 7D rollback plan

Nothing is deployed. Production still runs the original `relays/` (PID 67396 on :8768, PID 40624 on :8769), never modified.

- Staging is isolated: separate directory `relays_phase7c/` (git branch `phase7d-staging`), port :8772, separate `data/` and `staging_data_qa/`. The staging process is already stopped. To stop again: kill the `start_phase7d_relay.py` process.
- Remove test data and credentials: delete `staging_data_qa/` and `staging_secrets/` (or `qa_admin.py delete-account EMAIL`).
- Code rollback levels:
  1. `STT_QA_ENABLED` unset/0 (default): QA code inert, behaviour equals Phase 7C.
  2. `git checkout 387525e`: Phase 7C without QA.
  3. `git checkout 874b131`, or keep using `relays/`: pre-7C relay.
  Commits: `874b131` baseline, `387525e` Phase 7C, `90a8913` QA layer, `2e462cf` token fix.
- If ever promoted: switch the supervisor to the new directory; rollback = point it back to `relays/` and restart. `transcripts.db` schema is unchanged by 7C/7D; QA data lives in its own DB under `STT_QA_DIR`.
- Flutter: QA behaviour only when built with `--dart-define=QA_BACKEND_HTTP=...`; otherwise unchanged. The app dir is not under git: back up `auth_service.dart`, `auth_gate.dart`, `transcription_client.dart`, `session_screen.dart`, `pubspec.yaml` before promoting. Modified files and md5s are in the implementation report.
- No merge, deploy or production change without your explicit approval.
