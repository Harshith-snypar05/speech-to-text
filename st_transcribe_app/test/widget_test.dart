import 'package:flutter_test/flutter_test.dart';

import 'package:st_transcribe/main.dart';
import 'package:st_transcribe/services/auth_service.dart';

void main() {
  testWidgets('Home screen shows Start New Session once logged in', (WidgetTester tester) async {
    AuthService.currentEmail.value = 'tester.one@gmail.com';
    await tester.pumpWidget(const STTranscribeApp());
    expect(find.text('Start New Session'), findsOneWidget);
    expect(find.text('Recent Transcripts'), findsOneWidget);
  });
}
