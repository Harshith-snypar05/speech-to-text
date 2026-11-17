import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';

/// Typed client for the ScriptLiv platform API (accounts, usage, sessions, sharing).
/// The base URL is build-time config; the bearer token is held by [PlatformSession].
class ApiException implements Exception {
  final int status;
  final String code;
  final String message;
  ApiException(this.status, this.code, this.message);
  bool get isAuth => status == 401;
  @override
  String toString() => message;
}

class PlatformSession {
  PlatformSession._();
  static String? token;
}

class UsageInfo {
  final String planName;
  final int includedMinutes;
  final double includedUsedSeconds;
  final double includedRemainingSeconds;
  final double addonRemainingSeconds;
  final double totalRemainingSeconds;
  final double percentUsed;
  final DateTime resetAt;
  final bool cancelAtPeriodEnd;
  final List<String> warnings;
  /// Earliest expiry among add-ons that still have minutes left; null when there are none.
  final DateTime? addonExpiresAt;
  UsageInfo(this.planName, this.includedMinutes, this.includedUsedSeconds, this.includedRemainingSeconds,
      this.addonRemainingSeconds, this.totalRemainingSeconds, this.percentUsed, this.resetAt, this.cancelAtPeriodEnd, this.warnings,
      {this.addonExpiresAt});
  factory UsageInfo.fromJson(Map<String, dynamic> j) => UsageInfo(
        j['plan_name'] as String? ?? '',
        (j['included_minutes'] as num?)?.toInt() ?? 0,
        (j['included_used_seconds'] as num?)?.toDouble() ?? 0,
        (j['included_remaining_seconds'] as num?)?.toDouble() ?? 0,
        (j['addon_remaining_seconds'] as num?)?.toDouble() ?? 0,
        (j['total_remaining_seconds'] as num?)?.toDouble() ?? 0,
        (j['percent_used'] as num?)?.toDouble() ?? 0,
        DateTime.fromMillisecondsSinceEpoch(((j['reset_at'] as num?) ?? 0).toInt() * 1000),
        j['cancel_at_period_end'] == true,
        [for (final w in (j['warnings'] as List? ?? const [])) (w as Map<String, dynamic>)['message'] as String],
        addonExpiresAt: _earliestAddonExpiry(j['addons']),
      );

  static DateTime? _earliestAddonExpiry(Object? addons) {
    num? best;
    for (final a in (addons as List? ?? const [])) {
      final m = a as Map<String, dynamic>;
      if (((m['remaining_seconds'] as num?) ?? 0) <= 0) continue;
      final e = m['expires_at'] as num?;
      if (e != null && (best == null || e < best)) best = e;
    }
    return best == null ? null : DateTime.fromMillisecondsSinceEpoch(best.toInt() * 1000);
  }
}

/// Server-synced preferences (same record the website's Settings page edits).
class ServerSettings {
  final String theme; // light | dark | system
  final String language;
  final bool preventAutoLock;
  final bool usageWarnings;
  final List<int> warnPercents;
  final int? personalLimitMinutes;
  final List<String> supportedLanguages;
  ServerSettings(this.theme, this.language, this.preventAutoLock, this.usageWarnings, this.warnPercents, this.personalLimitMinutes,
      this.supportedLanguages);
  factory ServerSettings.fromJson(Map<String, dynamic> j) {
    final s = (j['settings'] as Map<String, dynamic>?) ?? const {};
    final percents = [for (final p in (s['warn_percents'] as List? ?? const [])) (p as num).toInt()]..sort();
    return ServerSettings(
      s['theme'] as String? ?? 'system',
      s['language'] as String? ?? 'en',
      s['prevent_auto_lock'] != false,
      s['usage_warnings'] != false,
      percents,
      (s['personal_limit_minutes'] as num?)?.toInt(),
      [for (final l in (j['supported_languages'] as List? ?? const [])) l as String],
    );
  }
}

class SessionItem {
  final String id;
  final String title;
  final DateTime? startedAt;
  final DateTime? endedAt;
  final bool sharing;
  final String? shareUrl;
  final List<String> transcript;
  SessionItem(this.id, this.title, this.startedAt, this.endedAt, this.sharing, this.shareUrl, this.transcript);
  factory SessionItem.fromJson(Map<String, dynamic> j) {
    DateTime? t(Object? s) => s == null ? null : DateTime.fromMillisecondsSinceEpoch(((s as num) * 1000).round());
    return SessionItem(
      j['session_id'] as String,
      j['title'] as String? ?? '',
      t(j['started_at']),
      t(j['ended_at']),
      j['sharing'] == true,
      j['share_url'] as String?,
      [for (final l in (j['transcript'] as List? ?? const [])) l as String],
    );
  }
}

class SharedView {
  final String title;
  final bool live;
  final List<String> transcript;
  SharedView(this.title, this.live, this.transcript);
  factory SharedView.fromJson(Map<String, dynamic> j) => SharedView(
        j['title'] as String? ?? '',
        j['live'] == true,
        [for (final l in (j['transcript'] as List? ?? const [])) l as String],
      );
}

class PlatformApi {
  PlatformApi._();

  static Uri _u(String path) => Uri.parse('${AppConfig.slHttp}$path');

  static Future<dynamic> _call(String method, String path, {Object? body, bool auth = true}) async {
    final req = http.Request(method, _u(path));
    req.headers['Content-Type'] = 'application/json';
    if (auth && PlatformSession.token != null) req.headers['Authorization'] = 'Bearer ${PlatformSession.token}';
    if (body != null) req.body = jsonEncode(body);
    final streamed = await req.send().timeout(const Duration(seconds: 15));
    final r = await http.Response.fromStream(streamed);
    dynamic data;
    if (r.body.isNotEmpty) {
      try {
        data = jsonDecode(r.body);
      } catch (_) {}
    }
    if (r.statusCode >= 400) {
      final e = (data is Map ? data['error'] : null) as Map?;
      throw ApiException(r.statusCode, e?['code'] as String? ?? 'error', e?['message'] as String? ?? 'Request failed (${r.statusCode}).');
    }
    return data;
  }

  /// Returns the JWT and the user's email.
  static Future<(String, String)> login(String email, String password) async {
    final d = await _call('POST', '/v1/auth/login', body: {'email': email, 'password': password}, auth: false) as Map<String, dynamic>;
    return (d['token'] as String, (d['user'] as Map<String, dynamic>)['email'] as String);
  }

  /// Creates the account only. There is no token: the email must be verified, then the user signs in.
  /// Returns the account's email.
  static Future<String> register(String name, String email, String password) async {
    final d = await _call('POST', '/v1/auth/register', body: {'name': name, 'email': email, 'password': password}, auth: false) as Map<String, dynamic>;
    return (d['user'] as Map<String, dynamic>)['email'] as String;
  }

  /// Signed-out resend of the verification mail. Same reply whether or not the account exists or needs it.
  static Future<void> resendVerificationFor(String email) async =>
      _call('POST', '/v1/auth/resend-verification', body: {'email': email}, auth: false);

  /// Always succeeds with the same reply (the server never reveals whether the account exists).
  static Future<String> forgotPassword(String email) async {
    final d = await _call('POST', '/v1/auth/forgot-password', body: {'email': email}, auth: false) as Map<String, dynamic>;
    return d['message'] as String? ?? 'If an account exists for that email, a reset link is on its way.';
  }

  static Future<void> resendVerification() async => _call('POST', '/v1/me/email/resend');

  static Future<Map<String, dynamic>> me() async => ((await _call('GET', '/v1/me')) as Map<String, dynamic>)['user'] as Map<String, dynamic>;

  static Future<UsageInfo> usage() async => UsageInfo.fromJson(await _call('GET', '/v1/usage') as Map<String, dynamic>);

  static Future<List<SessionItem>> sessions() async {
    final d = await _call('GET', '/v1/sessions') as Map<String, dynamic>;
    return [for (final s in d['sessions'] as List) SessionItem.fromJson(s as Map<String, dynamic>)];
  }

  static Future<SessionItem> session(String id) async =>
      SessionItem.fromJson(await _call('GET', '/v1/sessions/${Uri.encodeComponent(id)}') as Map<String, dynamic>);

  static Future<SessionItem> share(String id) async =>
      SessionItem.fromJson(await _call('POST', '/v1/sessions/${Uri.encodeComponent(id)}/share') as Map<String, dynamic>);

  static Future<SessionItem> unshare(String id) async =>
      SessionItem.fromJson(await _call('DELETE', '/v1/sessions/${Uri.encodeComponent(id)}/share') as Map<String, dynamic>);

  static Future<void> deleteSession(String id) async => _call('DELETE', '/v1/sessions/${Uri.encodeComponent(id)}');

  static Future<SharedView> shared(String token) async =>
      SharedView.fromJson(await _call('GET', '/v1/shared/${Uri.encodeComponent(token)}', auth: false) as Map<String, dynamic>);

  // ---- account ----
  static Future<Map<String, dynamic>> updateName(String name) async =>
      ((await _call('PATCH', '/v1/me', body: {'name': name})) as Map<String, dynamic>)['user'] as Map<String, dynamic>;

  /// Starts an email change; the new address stays pending until its link is opened. Returns the pending address.
  static Future<String> changeEmail(String newEmail, String password) async {
    final d = await _call('POST', '/v1/me/email', body: {'new_email': newEmail, 'password': password}) as Map<String, dynamic>;
    return d['pending_email'] as String? ?? newEmail;
  }

  /// Returns the replacement token: every other device is signed out by the change.
  static Future<String> changePassword(String current, String next) async {
    final d = await _call('POST', '/v1/me/password', body: {'current_password': current, 'new_password': next}) as Map<String, dynamic>;
    return d['token'] as String;
  }

  // ---- settings ----
  static Future<ServerSettings> settings() async => ServerSettings.fromJson(await _call('GET', '/v1/settings') as Map<String, dynamic>);

  static Future<ServerSettings> saveSettings(Map<String, dynamic> patch) async =>
      ServerSettings.fromJson(await _call('PUT', '/v1/settings', body: patch) as Map<String, dynamic>);

  // ---- billing (read + cancel/resume; buying happens on the website) ----
  static Future<Map<String, dynamic>> subscription() async => await _call('GET', '/v1/subscription') as Map<String, dynamic>;

  static Future<void> cancelPlan() async => _call('POST', '/v1/subscription/cancel');

  static Future<void> resumePlan() async => _call('POST', '/v1/subscription/resume');

  static Future<Map<String, dynamic>?> paymentMethod() async =>
      ((await _call('GET', '/v1/billing/payment-method')) as Map<String, dynamic>)['payment_method'] as Map<String, dynamic>?;

  static Future<List<Map<String, dynamic>>> payments() async {
    final d = await _call('GET', '/v1/billing/payments') as Map<String, dynamic>;
    return [for (final p in (d['payments'] as List? ?? const [])) p as Map<String, dynamic>];
  }

  static Future<Map<String, dynamic>> billingDetails() async =>
      ((await _call('GET', '/v1/billing/details')) as Map<String, dynamic>)['details'] as Map<String, dynamic>? ?? {};

  static Future<Map<String, dynamic>> saveBillingDetails(Map<String, dynamic> d) async =>
      ((await _call('PUT', '/v1/billing/details', body: d)) as Map<String, dynamic>)['details'] as Map<String, dynamic>? ?? {};

  // ---- account removal / feedback ----
  /// Permanently deletes the account and its data. Needs the password; a live paid plan must be cancelled first.
  static Future<void> deleteAccount(String password) async => _call('DELETE', '/v1/me', body: {'password': password});

  /// kind: feature | bug | other
  static Future<void> sendFeedback(String kind, String title, String message) async =>
      _call('POST', '/v1/feedback', body: {'kind': kind, 'title': title, 'message': message});
}
