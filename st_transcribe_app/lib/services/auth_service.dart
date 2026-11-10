import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../config/app_config.dart';
import 'platform_api.dart';

/// Sign-in state. Accounts live on the ScriptLiv platform API; the app never holds credentials of its own.
class AuthService {
  AuthService._();

  static const _kPlatformToken = 'sl_platform_token';

  static final ValueNotifier<String?> currentEmail = ValueNotifier(null);
  static bool get isLoggedIn => currentEmail.value != null;

  static SharedPreferences? _prefs;

  /// Set when an account exists but its email is not verified yet (just registered, or sign-in was refused).
  /// The login screen shows "check your email" while this is non-null. Nothing is signed in.
  static final ValueNotifier<String?> unverifiedEmail = ValueNotifier(null);

  /// Bearer token for the platform API; the relay accepts the same token on the WebSocket.
  static String? token;

  static Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    _prefs = prefs;
    if (!AppConfig.platformMode) return;
    final t = prefs.getString(_kPlatformToken);
    if (t == null) return;
    PlatformSession.token = t;
    try {
      final u = await PlatformApi.me();
      currentEmail.value = u['email'] as String?;
      token = t;
    } on ApiException catch (e) {
      if (e.isAuth) await _clear();
    } catch (_) {
      // offline: keep the token, stay signed out of the UI until the API answers
    }
  }

  static Future<void> _clear() async {
    PlatformSession.token = null;
    token = null;
    await _prefs?.remove(_kPlatformToken);
  }

  static Future<void> _set(String t, String email) async {
    PlatformSession.token = t;
    token = t;
    currentEmail.value = email;
    await _prefs?.setString(_kPlatformToken, t);
  }

  /// Returns null on success, else a message safe to show. A null return with [unverifiedEmail] set means the account
  /// exists but must verify its email first: the user is NOT signed in.
  static Future<String?> login(String email, String password) async {
    if (!AppConfig.platformMode) return 'This build is not connected to a ScriptLiv server.';
    final addr = email.trim().toLowerCase();
    try {
      final (t, e) = await PlatformApi.login(addr, password);
      await _set(t, e);
      return null;
    } on ApiException catch (e) {
      if (e.code == 'email_not_verified') {
        unverifiedEmail.value = addr;
        return null;
      }
      return e.message;
    } catch (_) {
      return 'Could not reach the server. Check your connection.';
    }
  }

  static Future<String?> register(String name, String email, String password) async {
    if (!AppConfig.platformMode) return 'This build is not connected to a ScriptLiv server.';
    try {
      unverifiedEmail.value = await PlatformApi.register(name.trim(), email.trim().toLowerCase(), password);
      return null;   // registering never signs in: the user verifies the email first, then signs in
    } on ApiException catch (e) {
      return e.message;
    } catch (_) {
      return 'Could not reach the server. Check your connection.';
    }
  }

  /// Asks for a fresh verification mail. Returns a message safe to show.
  static Future<String> resendVerification(String email) async {
    try {
      await PlatformApi.resendVerificationFor(email);
      return 'If this account still needs verification, a new link is on its way.';
    } on ApiException catch (e) {
      return e.message;
    } catch (_) {
      return 'Could not reach the server. Try again.';
    }
  }

  static Future<void> logout() async {
    await _clear();
    currentEmail.value = null;
  }
}
