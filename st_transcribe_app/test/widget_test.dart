import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:st_transcribe/main.dart';
import 'package:st_transcribe/services/auth_service.dart';

void main() {
  testWidgets('Home shows greeting and start card once logged in', (WidgetTester tester) async {
    SharedPreferences.setMockInitialValues({'onboarding_done_v1': true});
    AuthService.currentEmail.value = 'ann.lee@example.com';
    await tester.pumpWidget(const STTranscribeApp());
    await tester.pump(const Duration(seconds: 2)); // splash
    await tester.pump();
    expect(find.text('Hello, Ann Lee'), findsOneWidget);
    expect(find.text('Start recording'), findsWidgets);
  });
}
