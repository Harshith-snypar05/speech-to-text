import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:record/record.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:st_transcribe/services/auth_service.dart';
import 'package:st_transcribe/services/connection_status.dart';
import 'package:st_transcribe/services/transcription_client.dart';

const email = String.fromEnvironment('SIM_EMAIL');
const pw = String.fromEnvironment('SIM_PW');
const pcm = String.fromEnvironment('SIM_PCM');
const sid = String.fromEnvironment('SIM_SID');
const wsUrl = String.fromEnvironment('SIM_WS');
const out = String.fromEnvironment('SIM_OUT');
const mode = String.fromEnvironment('SIM_MODE', defaultValue: 'normal');
const secs = int.fromEnvironment('SIM_SECS', defaultValue: 20);

void main() {
  test('app flow', () async {
    SharedPreferences.setMockInitialValues({});
    await AuthService.load();
    final log = <Map<String, dynamic>>[];
    final sw = Stopwatch()..start();
    void ev(String k, [dynamic v]) => log.add({'t': sw.elapsedMilliseconds, 'k': k, 'v': v});

    ev('login', await AuthService.login(email, pw));
    ev('consent_required', !AuthService.qaConsent);
    if (!AuthService.qaConsent) ev('consent_accept', await AuthService.acceptQaConsent());

    AudioRecorder.pcmPath = pcm;
    final c = TranscriptionClient(wsUrl: wsUrl, sessionId: sid, qaToken: AuthService.qaToken, maxRetries: 2);
    final finals = <String>[];
    final partials = <String>[];
    c.onStatus.listen((s) => ev('status', s.name));
    c.onText.listen((t) { finals.add(t); ev('final', t); });
    c.onPartial.listen((t) { partials.add(t); ev('partial', t.length); });
    ev('start_ok', await c.start().then((_) => true).catchError((e) { ev('start_err', '$e'); return false; }));
    await Future.delayed(Duration(seconds: secs));
    if (mode == 'normal') await c.stop();
    ev('end_status', c.status.name);
    File(out).writeAsStringSync(jsonEncode({
      'email': email, 'sid': sid, 'finals': finals, 'partials': partials.length,
      'sent_bytes': AudioRecorder.sentBytes, 'events': log,
    }));
    AuthService.logout();
    c.dispose();
  }, timeout: const Timeout(Duration(minutes: 5)));
}
