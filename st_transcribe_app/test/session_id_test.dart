import 'package:flutter_test/flutter_test.dart';
import 'package:st_transcribe/services/session_id.dart';

// Matches the relay's validation regexes (relays/core/protocol.py):
// session id ^[A-Za-z0-9_-]{6,64}$, access code ^[A-Za-z0-9]{4,32}$
final _sessionIdPattern = RegExp(r'^[A-Za-z0-9_-]{6,64}$');
final _accessCodePattern = RegExp(r'^[A-Za-z0-9]{4,32}$');

void main() {
  test('generateSessionId produces a 10-char token matching the relay-accepted format', () {
    final id = generateSessionId();
    expect(id.length, 10);
    expect(_sessionIdPattern.hasMatch(id), isTrue, reason: '"$id" must match the server-side validation pattern');
  });

  test('generateSessionId produces different values across calls', () {
    final ids = List.generate(50, (_) => generateSessionId());
    expect(ids.toSet().length, 50, reason: 'no collisions expected across 50 draws from a secure RNG');
  });

  test('generateAccessCode produces an 8-char token matching the relay-accepted format', () {
    final code = generateAccessCode();
    expect(code.length, 8);
    expect(_accessCodePattern.hasMatch(code), isTrue, reason: '"$code" must match the server-side validation pattern');
  });

  test('generateAccessCode excludes visually-ambiguous characters (0/O/1/I)', () {
    final codes = List.generate(100, (_) => generateAccessCode());
    final combined = codes.join();
    expect(combined.contains('0'), isFalse);
    expect(combined.contains('O'), isFalse);
    expect(combined.contains('1'), isFalse);
    expect(combined.contains('I'), isFalse);
  });

  test('generateAccessCode produces different values across calls', () {
    final codes = List.generate(50, (_) => generateAccessCode());
    expect(codes.toSet().length, 50);
  });
}
