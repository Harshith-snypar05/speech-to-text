import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:st_transcribe/screens/login_screen.dart';
import 'package:st_transcribe/services/auth_service.dart';

void main() {
  setUp(() {
    AuthService.currentEmail.value = null;
  });

  testWidgets('sign-in without a configured server shows an error and does not log in', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: LoginScreen()));
    await tester.enterText(find.widgetWithText(TextField, 'Email'), 'ann@example.com');
    await tester.enterText(find.widgetWithText(TextField, 'Password'), 'wrong');
    await tester.tap(find.text('Log In'));
    await tester.pumpAndSettle();

    expect(find.text('This build is not connected to a ScriptLiv server.'), findsOneWidget);
    expect(AuthService.isLoggedIn, isFalse);
  });

  testWidgets('login screen offers account creation', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: LoginScreen()));
    await tester.tap(find.text('New here? Create an account'));
    await tester.pumpAndSettle();
    expect(find.text('Create account'), findsWidgets);
  });
}
