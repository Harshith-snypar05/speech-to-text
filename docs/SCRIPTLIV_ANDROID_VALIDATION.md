# Android Validation

## Status: NOT built, NOT run on a device or emulator

| Check | Result |
|---|---|
| `flutter analyze` | 0 errors, 5 info (scratch copy) |
| `flutter test` | 61 passed (scratch copy) |
| `flutter build apk` | **Not done.** Installed Flutter 3.44.6 / Dart 3.12.2 cannot resolve pubspec `^3.13.7` |
| Run on device/emulator | **Not done.** No emulator or device available |
| Mic capture, WebSocket on real hardware | **Unverified** |

## Changes for Android
- Debug-only cleartext traffic permitted so a staging `http://` / `ws://` relay works. Release builds must use TLS.
- Launcher icons installed from `assets/branding/android/`.

## To validate
Upgrade Flutter to a version satisfying the pubspec, then:
```
cd st_transcribe_app
flutter pub get
flutter run --dart-define=QA_BACKEND_HTTP=http://<host>:8772 --dart-define=QA_BACKEND_WS=ws://<host>:8772
```
Use the host LAN IP (or `10.0.2.2` on the emulator), not `localhost`. Then run the flow: sign in, consent, record, partial/final, stop, history, share.
