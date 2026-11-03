import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Known relay backends for local development, plus a Custom slot for a
/// tunnel URL or a real deployment. Selecting a preset here is what
/// replaces the old hardcoded `kTranscriptionBackendUrl` constant --
/// changing backend no longer requires editing code and rebuilding.
enum TranscriptionEnginePreset {
  fasterWhisper('faster-whisper', 'ws://localhost:8767'),
  whisperCpp('whisper.cpp', 'ws://localhost:8765'),
  openaiWhisper('openai/whisper', 'ws://localhost:8766'),
  parakeet('Parakeet TDT', 'ws://localhost:8768'),
  custom('Custom', '');

  final String label;
  final String defaultUrl;
  const TranscriptionEnginePreset(this.label, this.defaultUrl);
}

enum AppTextSize {
  small('Small', 0.9),
  medium('Medium', 1.0),
  large('Large', 1.15);

  final String label;
  final double scale;
  const AppTextSize(this.label, this.scale);
}

/// `true` shows word-by-word partials as they stream in; `false` hides
/// partials entirely and only shows committed per-sentence finals. Purely
/// a client-side display choice -- the relay sends the same messages
/// either way, this just decides what the UI does with partials.
enum TranscriptionMode { live, accurate }

bool isValidBackendUrl(String value) {
  final uri = Uri.tryParse(value.trim());
  if (uri == null) return false;
  if (uri.scheme != 'ws' && uri.scheme != 'wss') return false;
  if (uri.host.isEmpty) return false;
  return true;
}

/// When the app is served from a real host (not localhost -- e.g. behind
/// relays/combined_proxy.py, which serves the app and proxies the relay
/// on the same port), the backend is reachable at that same origin. Used
/// as the first-load default so a shared link works with zero per-device
/// Settings configuration. Returns null for local dev (`flutter run`,
/// localhost/127.0.0.1), where it wouldn't mean anything -- the app's own
/// dev-server port isn't the relay.
String? detectSameOriginBackendUrl() {
  if (!kIsWeb) return null;
  final base = Uri.base;
  final host = base.host;
  if (host.isEmpty || host == 'localhost' || host == '127.0.0.1') return null;
  final scheme = base.scheme == 'https' ? 'wss' : 'ws';
  final port = base.hasPort ? ':${base.port}' : '';
  return '$scheme://$host$port';
}

/// Persisted app settings, loaded once at startup. Each field is a
/// ValueNotifier so widgets can listen directly without a state
/// management package -- small enough surface area that `setState` +
/// ValueNotifier is simpler than pulling in a dependency for this.
class AppSettings {
  AppSettings._();

  static const _kBackendUrl = 'settings_backend_url';
  static const _kEnginePreset = 'settings_engine_preset';
  static const _kTextSize = 'settings_text_size';
  static const _kThemeMode = 'settings_theme_mode';
  static const _kTranscriptionMode = 'settings_transcription_mode';
  static const _kMicId = 'settings_mic_id';
  static const _kMicLabel = 'settings_mic_label';

  static final ValueNotifier<String> backendUrl =
      ValueNotifier(TranscriptionEnginePreset.fasterWhisper.defaultUrl);
  static final ValueNotifier<TranscriptionEnginePreset> enginePreset =
      ValueNotifier(TranscriptionEnginePreset.fasterWhisper);
  static final ValueNotifier<AppTextSize> textSize = ValueNotifier(AppTextSize.medium);
  static final ValueNotifier<ThemeMode> themeMode = ValueNotifier(ThemeMode.system);
  static final ValueNotifier<TranscriptionMode> transcriptionMode = ValueNotifier(TranscriptionMode.live);
  static final ValueNotifier<String?> micDeviceId = ValueNotifier(null);
  static final ValueNotifier<String?> micDeviceLabel = ValueNotifier(null);

  static SharedPreferences? _prefs;

  static Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    _prefs = prefs;

    final presetName = prefs.getString(_kEnginePreset);
    enginePreset.value = TranscriptionEnginePreset.values.firstWhere(
      (p) => p.name == presetName,
      orElse: () => TranscriptionEnginePreset.fasterWhisper,
    );

    final storedUrl = prefs.getString(_kBackendUrl);
    if (storedUrl != null) {
      backendUrl.value = storedUrl;
    } else {
      final sameOrigin = detectSameOriginBackendUrl();
      if (sameOrigin != null) {
        enginePreset.value = TranscriptionEnginePreset.custom;
        backendUrl.value = sameOrigin;
      } else {
        backendUrl.value = enginePreset.value.defaultUrl;
      }
    }

    final sizeName = prefs.getString(_kTextSize);
    textSize.value = AppTextSize.values.firstWhere((s) => s.name == sizeName, orElse: () => AppTextSize.medium);

    final modeName = prefs.getString(_kThemeMode);
    themeMode.value = ThemeMode.values.firstWhere((m) => m.name == modeName, orElse: () => ThemeMode.system);

    final transcriptionModeName = prefs.getString(_kTranscriptionMode);
    transcriptionMode.value = TranscriptionMode.values.firstWhere(
      (m) => m.name == transcriptionModeName,
      orElse: () => TranscriptionMode.live,
    );

    micDeviceId.value = prefs.getString(_kMicId);
    micDeviceLabel.value = prefs.getString(_kMicLabel);
  }

  static Future<void> setBackendUrl(String url) async {
    backendUrl.value = url;
    await _prefs?.setString(_kBackendUrl, url);
  }

  static Future<void> setEnginePreset(TranscriptionEnginePreset preset) async {
    enginePreset.value = preset;
    await _prefs?.setString(_kEnginePreset, preset.name);
    if (preset != TranscriptionEnginePreset.custom) {
      await setBackendUrl(preset.defaultUrl);
    }
  }

  static Future<void> setTextSize(AppTextSize size) async {
    textSize.value = size;
    await _prefs?.setString(_kTextSize, size.name);
  }

  static Future<void> setThemeMode(ThemeMode mode) async {
    themeMode.value = mode;
    await _prefs?.setString(_kThemeMode, mode.name);
  }

  static Future<void> setTranscriptionMode(TranscriptionMode mode) async {
    transcriptionMode.value = mode;
    await _prefs?.setString(_kTranscriptionMode, mode.name);
  }

  static Future<void> setMicDevice(String? id, String? label) async {
    micDeviceId.value = id;
    micDeviceLabel.value = label;
    if (id == null) {
      await _prefs?.remove(_kMicId);
      await _prefs?.remove(_kMicLabel);
    } else {
      await _prefs?.setString(_kMicId, id);
      await _prefs?.setString(_kMicLabel, label ?? id);
    }
  }
}
