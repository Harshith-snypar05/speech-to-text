# Phase 7D simulated mobile-app test (headless Flutter)

**What this is:** the app's real, unmodified Dart code (`AuthService` QA login/consent, `TranscriptionClient`, `LiveTranscriptParser`, `ConnectionStatus`) run under `flutter test` (Flutter 3.44.6 VM, scratch copy with the SDK constraint lowered to ^3.12). Only the `record` plugin is replaced by a fake mic (`flutter_sim/fake_record`) that streams a PCM file in real time (100 ms chunks, then silence like a live mic). Three separate processes = three "phones", against the staging relay :8772 with real Parakeet.

**What this is NOT:** no widgets rendered, no Android/iOS runtime, no real mic/permissions, no OS network stack or backgrounding. UI rendering of partials/finals is still unverified. An emulator (Pixel_9_Pro_XL AVD exists) was not used: free RAM ~1.6 GB with the relay running.

## Results (`phase7d_flutter_sim.json`, `flutter_sim/outb*.json`)
| Account | App statuses | Client finals | Backend finals | Match | Dups | Audio download | Other account's audio |
|---|---|---|---|---|---|---|---|
| tester.one | connecting, connected | 3 | 3 | yes | 0 | 200, bit-exact | 404 |
| tester.two | connecting, connected | 3 | 3 | yes | 0 | 200, bit-exact | 404 |
| tester.three | connecting, connected | 6 | 6 | yes | 0 | 200, bit-exact | 404 |
Login, consent-accept, token-on-WS all worked via the app's own code path; partials arrived (10/14/15 callbacks).

## Findings
1. **App bug (fixed in this phase's Flutter change set): close code 4403 caused an endless reconnect loop.** Account B opening account A's session id got 4403; the client only treated 4400/4401 as terminal, so it showed `connected -> networkLost -> reconnecting` about 2x/second indefinitely (retry counter reset on every successful handshake). Fixed: `transcription_client.dart` now treats 4403 as `unauthorized`. Re-run: `connecting, connected, unauthorized`, no loop. New md5 `6c6761893321821eac4e239ec52f32b6`.
   Related, not fixed: the same reset-on-handshake pattern would loop for any server that accepts then closes immediately.
2. **Harness artifact, not a bug:** the first run (mic stops after the file) lost the last final from the client (stored in backend but only flushed on disconnect). With continuous silence like a real mic, all finals arrive. Consistent with the earlier reconnect finding: a final produced after the socket dies is undeliverable.

## Still needs a real device
Widget rendering of partials/finals, the consent screen, mic permission, backgrounding/network switch, real-device audio quality.
