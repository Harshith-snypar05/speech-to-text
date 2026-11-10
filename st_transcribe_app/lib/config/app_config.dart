/// Build-time configuration. No backend URL is hardcoded. Pass:
///   --dart-define=SL_API_HTTP=http://HOST:8790   ScriptLiv platform API (accounts, usage, sharing). Required for sign-in.
///   --dart-define=SL_WS=ws://HOST:8772           live transcription relay WebSocket
class AppConfig {
  AppConfig._();

  static const String slHttp = String.fromEnvironment('SL_API_HTTP');
  static const String slWs = String.fromEnvironment('SL_WS');

  static bool get platformMode => slHttp.isNotEmpty;

  static const String copyright = '© Snypar Tech';

  /// WebSocket base of the relay; empty when the build has none.
  static String get wsBase => slWs;
}
