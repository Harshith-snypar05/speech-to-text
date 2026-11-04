import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Hardcoded test accounts -- stand-in until real authentication (Gmail
/// OAuth, or a backend-verified login) replaces this. Swapping it out
/// later only means rewriting [AuthService.login]'s body to call that
/// instead; the gate in main.dart and the persisted "logged in" state
/// stay the same.
const Map<String, String> testAccounts = {
  'tester.one@gmail.com': 'Orbit#47Falcon',
  'tester.two@gmail.com': 'Nimbus#82Delta',
  'tester.three@gmail.com': 'Cobalt#19Raven',
};

class AuthService {
  AuthService._();

  static const _kLoggedInEmail = 'auth_logged_in_email';

  static final ValueNotifier<String?> currentEmail = ValueNotifier(null);
  static bool get isLoggedIn => currentEmail.value != null;

  static SharedPreferences? _prefs;

  static Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    _prefs = prefs;
    currentEmail.value = prefs.getString(_kLoggedInEmail);
  }

  static Future<bool> login(String email, String password) async {
    final normalized = email.trim().toLowerCase();
    if (testAccounts[normalized] != password) return false;
    currentEmail.value = normalized;
    await _prefs?.setString(_kLoggedInEmail, normalized);
    return true;
  }

  static Future<void> logout() async {
    currentEmail.value = null;
    await _prefs?.remove(_kLoggedInEmail);
  }
}
