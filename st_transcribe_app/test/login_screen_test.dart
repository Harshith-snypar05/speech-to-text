import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:st_transcribe/screens/login_screen.dart';
import 'package:st_transcribe/services/auth_service.dart';

void main() {
  setUp(() {
    AuthService.currentEmail.value = null;
  });

  testWidgets('wrong credentials show an error and do not log in', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: LoginScreen()));
    await tester.enterText(find.widgetWithText(TextField, 'Email'), 'tester.one@gmail.com');
    await tester.enterText(find.widgetWithText(TextField, 'Password'), 'wrong');
    await tester.tap(find.text('Log In'));
    await tester.pumpAndSettle();

    expect(find.text('Incorrect email or password.'), findsOneWidget);
    expect(AuthService.isLoggedIn, isFalse);
  });

  testWidgets('correct test-account credentials log in', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: LoginScreen()));
    await tester.enterText(find.widgetWithText(TextField, 'Email'), 'tester.two@gmail.com');
    await tester.enterText(find.widgetWithText(TextField, 'Password'), 'Nimbus#82Delta');
    await tester.tap(find.text('Log In'));
    await tester.pumpAndSettle();

    expect(AuthService.isLoggedIn, isTrue);
    expect(AuthService.currentEmail.value, 'tester.two@gmail.com');
  });

  testWidgets('no test-account credentials are shown on screen', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: LoginScreen()));
    for (final email in testAccounts.keys) {
      expect(find.textContaining(email), findsNothing);
    }
  });
}
