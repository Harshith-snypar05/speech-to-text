import 'package:flutter/material.dart';
import 'models/transcript.dart';
import 'screens/auth_gate.dart';
import 'screens/session_screen.dart';
import 'screens/settings_screen.dart';
import 'screens/transcript_detail_screen.dart';
import 'screens/viewer_screen.dart';
import 'services/app_settings.dart';
import 'services/auth_service.dart';
import 'theme.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AppSettings.load();
  await AuthService.load();
  runApp(const STTranscribeApp());
}

class STTranscribeApp extends StatelessWidget {
  const STTranscribeApp({super.key});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge([AppSettings.themeMode, AppSettings.textSize]),
      builder: (context, _) {
        return MaterialApp(
          title: 'ST Transcribe',
          debugShowCheckedModeBanner: false,
          theme: appTheme,
          darkTheme: appDarkTheme,
          themeMode: AppSettings.themeMode.value,
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(context).copyWith(
              textScaler: TextScaler.linear(AppSettings.textSize.value.scale),
            ),
            child: child!,
          ),
          initialRoute: '/',
          onGenerateRoute: (settings) {
            // Hash-based web routing puts any query string inside the route
            // name itself (e.g. "/viewer?session=abc"), so split path/query here
            // rather than relying on settings.name matching a bare path.
            final uri = Uri.parse(settings.name ?? '/');
            switch (uri.path) {
              case '/':
                return MaterialPageRoute(builder: (_) => const AuthGate());
              case '/session':
                return MaterialPageRoute(builder: (_) => const SessionScreen());
              case '/settings':
                return MaterialPageRoute(builder: (_) => const SettingsScreen());
              case '/viewer':
                return MaterialPageRoute(
                  builder: (_) => ViewerScreen(
                    sessionId: uri.queryParameters['session'],
                    accessCode: uri.queryParameters['code'],
                  ),
                );
              case '/transcript':
                final meta = settings.arguments as TranscriptMeta;
                return MaterialPageRoute(builder: (_) => TranscriptDetailScreen(meta: meta));
              default:
                return MaterialPageRoute(builder: (_) => const AuthGate());
            }
          },
        );
      },
    );
  }
}
