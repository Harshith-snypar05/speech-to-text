# iOS Validation

## Status: UNVERIFIED. No iOS support or build success is claimed.

No macOS or Xcode is available in this environment, so nothing iOS was built, signed or run.

## Prepared (unbuilt)
- `AppIcon.appiconset` installed from `assets/branding/ios/`.
- Dart code is platform-neutral; plugins in use (`record`, `web_socket_channel`, `share_plus`, `path_provider`, `shared_preferences`) support iOS in principle.

## Needs checking on a Mac
- `NSMicrophoneUsageDescription` present in `Info.plist`.
- App Transport Security: staging uses `http://`/`ws://`; needs an ATS exception for debug or TLS.
- Audio session behaviour, interruptions, background.
- Share sheet and audio file share.

## Commands (on macOS with Xcode)
```
cd st_transcribe_app
flutter pub get
cd ios && pod install && cd ..
flutter run -d <ios-device> --dart-define=QA_BACKEND_HTTP=http://<host>:8772 --dart-define=QA_BACKEND_WS=ws://<host>:8772
```
