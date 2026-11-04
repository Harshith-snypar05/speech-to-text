import 'package:flutter/material.dart';
import '../services/auth_service.dart';
import 'home_screen.dart';
import 'login_screen.dart';

/// Root of the `/` route: shows the login screen until a test account
/// signs in, then the normal app. Viewer links (`/viewer?session=...`)
/// bypass this entirely -- that's a public, shareable read-only link,
/// not part of the authenticated app.
class AuthGate extends StatelessWidget {
  const AuthGate({super.key});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: AuthService.currentEmail,
      builder: (context, _) => AuthService.isLoggedIn ? const HomeScreen() : const LoginScreen(),
    );
  }
}
