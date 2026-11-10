# ScriptLiv — Final Implementation Report

## Delivered
- **Website** `scriptliv_web/`: landing (matches img_ref), login, consent, app (home, record, history, settings), admin-only `/console`.
- **Flutter** `st_transcribe_app/`: splash, onboarding, sign-in, home ("Hello, <name>"), recording with real mic-driven waveform, live transcription, history, transcript view/share, settings; Home/Transcripts/Settings nav with centre mic.
- **Backend** (`relays_phase7c`, branch `redesign-staging`): Phase 7D QA layer; Parakeet and scheduler untouched.
- Docs in `speech-to-text/docs/SCRIPTLIV_*.md`.

## Verified vs not verified
| Item | State |
|---|---|
| Backend suite | 165 passed, 1 skipped |
| 3-account protocol E2E, real Parakeet | 69/69 (protocol level, not a phone) |
| Website in real browser, fake mic | 16/16 |
| Flutter analyze / test | 0 errors / 61 passed — **in a scratch copy** with SDK constraint lowered |
| Flutter build, Android device | **Not done** (SDK too old, no emulator) |
| iOS | **Unverified**, no Xcode |

## Run commands
Staging backend:
```
python benchmarks/results/phase7d/start_redesign_relay.py      # listens on :8772
```
Website:
```
cd scriptliv_web
npm ci
QA_BACKEND_HTTP=http://127.0.0.1:8772 NEXT_PUBLIC_WS_URL=ws://127.0.0.1:8772 npm run build
npx next start -p 3100
```
(`NEXT_PUBLIC_WS_URL` is baked at build time; rebuild if it changes.)

Android app (Flutter satisfying pubspec `^3.13.7`):
```
cd st_transcribe_app
flutter pub get
flutter run --dart-define=QA_BACKEND_HTTP=http://<host>:8772 --dart-define=QA_BACKEND_WS=ws://<host>:8772
```
iOS app (macOS + Xcode required; unverified):
```
cd st_transcribe_app && flutter pub get && (cd ios && pod install)
flutter run -d <ios-device> --dart-define=QA_BACKEND_HTTP=http://<host>:8772 --dart-define=QA_BACKEND_WS=ws://<host>:8772
```

## Decisions needed
1. **Retention**: staging launcher removes the retention env; no period is implemented. Supply an approved value (original `qa.env` had 30).
2. **QA admin**: `tester.one` is the staging default admin. Confirm who should be.
3. Collect **real tester consent**; harness only simulated it.
4. TLS before any non-LAN use (token currently in WS query string).

## Flags and caveats
- Palette switched to img_ref (`#6A00FF` etc.), superseding `#7C5CFF`.
- Pricing/unverified claims from the reference omitted.
- Logo is a vector redraw; shadcn-style UI is hand-written.
- **Security**: staging passwords were printed into session output and `passwords.txt` exists on disk. Treat as exposed; rotate. Not committed. Old plaintext test accounts remain in `auth_service.dart` for non-QA builds.
- Audio encryption key resides on the relay host.
- Android debug-only cleartext added; release needs TLS.
- Three accounts support no capacity claim.
- `scriptliv_web` and `assets/` are in a non-git folder; Flutter repo has unrelated uncommitted `relays/` changes. Nothing was committed, merged or deployed for this segment.
- 5 info lints in Flutter remain.
