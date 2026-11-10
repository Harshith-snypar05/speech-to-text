import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:st_transcribe/services/auth_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await AuthService.logout();
    await AuthService.load();
  });

  test('starts logged out with no stored session', () {
    expect(AuthService.isLoggedIn, isFalse);
    expect(AuthService.currentEmail.value, isNull);
    expect(AuthService.token, isNull);
  });

  test('a build without a server cannot sign in, and no credentials are built in', () async {
    final err = await AuthService.login('anyone@example.com', 'whatever-123');
    expect(err, isNotNull);
    expect(AuthService.isLoggedIn, isFalse);
    final reg = await AuthService.register('Ann', 'ann@example.com', 'whatever-123');
    expect(reg, isNotNull);
    expect(AuthService.isLoggedIn, isFalse);
  });

  test('logout clears the session', () async {
    AuthService.currentEmail.value = 'ann@example.com';
    AuthService.token = 'x';
    await AuthService.logout();
    expect(AuthService.isLoggedIn, isFalse);
    expect(AuthService.token, isNull);
  });
}
