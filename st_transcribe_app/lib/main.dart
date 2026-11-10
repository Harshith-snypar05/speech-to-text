import 'package:flutter/material.dart';
import 'config/app_config.dart';
import 'models/transcript.dart';
import 'screens/splash_screen.dart';
import 'screens/platform_session_screen.dart';
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
          title: 'ScriptLiv',
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
                return MaterialPageRoute(builder: (_) => const AppFlow());
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
                // Shared links: https://.../s/<token> arrives as /s/<token>; scriptliv://s/<token> arrives as /<token>.
                final segs = uri.pathSegments;
                final token = segs.length == 2 && segs[0] == 's'
                    ? segs[1]
                    : (segs.length == 1 && RegExp(r'^[A-Za-z0-9_-]{16,}$').hasMatch(segs[0]) ? segs[0] : null);
                if (token != null && AppConfig.platformMode) {
                  return MaterialPageRoute(builder: (_) => SharedViewScreen(token: token));
                }
                return MaterialPageRoute(builder: (_) => const AppFlow());
            }
          },
        );
      },
    );
  }
}
