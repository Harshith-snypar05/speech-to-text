import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:st_transcribe/services/auth_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await AuthService.load();
  });

  test('starts logged out with no stored session', () {
    expect(AuthService.isLoggedIn, isFalse);
    expect(AuthService.currentEmail.value, isNull);
  });

  test('login succeeds for a known test account, case- and whitespace-insensitive on email', () async {
    final ok = await AuthService.login(' Tester.One@Gmail.com ', 'Orbit#47Falcon');
    expect(ok, isTrue);
    expect(AuthService.isLoggedIn, isTrue);
    expect(AuthService.currentEmail.value, 'tester.one@gmail.com');
  });

  test('login fails for a wrong password on a known account', () async {
    final ok = await AuthService.login('tester.one@gmail.com', 'wrong-password');
    expect(ok, isFalse);
    expect(AuthService.isLoggedIn, isFalse);
  });

  test('login fails for an unknown account', () async {
    final ok = await AuthService.login('nobody@gmail.com', 'whatever');
    expect(ok, isFalse);
  });

  test('all three test accounts work', () async {
    for (final entry in testAccounts.entries) {
      await AuthService.logout();
      final ok = await AuthService.login(entry.key, entry.value);
      expect(ok, isTrue, reason: '${entry.key} should log in with its own password');
    }
  });

  test('logged-in state persists across a fresh load() (simulates app restart)', () async {
    await AuthService.login('tester.two@gmail.com', 'Nimbus#82Delta');
    await AuthService.load();
    expect(AuthService.currentEmail.value, 'tester.two@gmail.com');
  });

  test('logout clears the persisted session', () async {
    await AuthService.login('tester.three@gmail.com', 'Cobalt#19Raven');
    await AuthService.logout();
    expect(AuthService.isLoggedIn, isFalse);
    await AuthService.load();
    expect(AuthService.currentEmail.value, isNull);
  });
}
