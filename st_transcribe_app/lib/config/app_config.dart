/// Build-time configuration. No backend URL is hardcoded. Pass:
///   --dart-define=SL_API_HTTP=http://HOST:8790   ScriptLiv platform API (accounts, usage, sharing). Required for sign-in.
///   --dart-define=SL_WS=ws://HOST:8772           live transcription relay WebSocket
class AppConfig {
  AppConfig._();

  static const String slHttp = String.fromEnvironment('SL_API_HTTP');
  static const String slWs = String.fromEnvironment('SL_WS');

  static bool get platformMode => slHttp.isNotEmpty;

  /// Public marketing/account site for links like "Change plan" -- always the real domain, even when
  /// SL_API_HTTP/SL_WS point at a dev tunnel, so those links don't break or expire with the tunnel.
  static const String webOrigin = String.fromEnvironment('SL_WEB_ORIGIN', defaultValue: 'https://scriptliv.com');

  static const String copyright = '© Snypar Tech';

  /// WebSocket base of the relay; empty when the build has none.
  static String get wsBase => slWs;
}
