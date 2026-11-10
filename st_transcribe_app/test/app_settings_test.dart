import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:st_transcribe/services/app_settings.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await AppSettings.load();
  });

  test('defaults to the Parakeet preset and its local-dev URL', () {
    expect(AppSettings.enginePreset.value, TranscriptionEnginePreset.parakeet);
    expect(AppSettings.backendUrl.value, 'ws://localhost:8768');
  });

  test('defaults to live transcription mode, medium text, dark theme', () {
    expect(AppSettings.transcriptionMode.value, TranscriptionMode.live);
    expect(AppSettings.textSize.value, AppTextSize.medium);
    expect(AppSettings.themeMode.value, ThemeMode.dark);
    expect(AppSettings.micDeviceId.value, isNull);
  });

  test('setEnginePreset back to parakeet resets backendUrl to its default', () async {
    await AppSettings.setBackendUrl('wss://example.com:9999');
    await AppSettings.setEnginePreset(TranscriptionEnginePreset.parakeet);
    expect(AppSettings.enginePreset.value, TranscriptionEnginePreset.parakeet);
    expect(AppSettings.backendUrl.value, 'ws://localhost:8768');
  });

  test('switching to Custom preset does not overwrite a previously-set URL', () async {
    await AppSettings.setBackendUrl('wss://example.com:9999');
    await AppSettings.setEnginePreset(TranscriptionEnginePreset.custom);
    expect(AppSettings.backendUrl.value, 'wss://example.com:9999');
  });

  test('settings persist across a fresh load() (simulates app restart)', () async {
    await AppSettings.setTextSize(AppTextSize.large);
    await AppSettings.setThemeMode(ThemeMode.dark);
    await AppSettings.setTranscriptionMode(TranscriptionMode.accurate);
    await AppSettings.setMicDevice('device-42', 'USB Mic');
    await AppSettings.setBackendUrl('wss://custom.example.com');
    await AppSettings.setEnginePreset(TranscriptionEnginePreset.custom);

    // Reset in-memory notifiers to defaults, then reload from storage --
    // if persistence works, load() should restore everything above.
    await AppSettings.load();

    expect(AppSettings.textSize.value, AppTextSize.large);
    expect(AppSettings.themeMode.value, ThemeMode.dark);
    expect(AppSettings.transcriptionMode.value, TranscriptionMode.accurate);
    expect(AppSettings.micDeviceId.value, 'device-42');
    expect(AppSettings.micDeviceLabel.value, 'USB Mic');
    expect(AppSettings.backendUrl.value, 'wss://custom.example.com');
    expect(AppSettings.enginePreset.value, TranscriptionEnginePreset.custom);
  });

  test('setMicDevice(null, null) clears a previously-set device', () async {
    await AppSettings.setMicDevice('device-1', 'Some Mic');
    await AppSettings.setMicDevice(null, null);
    expect(AppSettings.micDeviceId.value, isNull);
    await AppSettings.load();
    expect(AppSettings.micDeviceId.value, isNull, reason: 'clearing must persist, not just update in-memory state');
  });

  group('isValidBackendUrl', () {
    test('accepts ws:// and wss:// with a host', () {
      expect(isValidBackendUrl('ws://localhost:8768'), isTrue);
      expect(isValidBackendUrl('wss://example.com:9999'), isTrue);
    });

    test('rejects non-websocket schemes', () {
      expect(isValidBackendUrl('http://localhost:8767'), isFalse);
      expect(isValidBackendUrl('https://example.com'), isFalse);
    });

    test('rejects malformed or hostless input', () {
      expect(isValidBackendUrl('not a url'), isFalse);
      expect(isValidBackendUrl('ws://'), isFalse);
      expect(isValidBackendUrl(''), isFalse);
    });
  });
}
