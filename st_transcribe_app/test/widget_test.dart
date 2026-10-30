import 'package:flutter_test/flutter_test.dart';

import 'package:st_transcribe/main.dart';

void main() {
  testWidgets('Home screen shows Start New Session', (WidgetTester tester) async {
    await tester.pumpWidget(const STTranscribeApp());
    expect(find.text('Start New Session'), findsOneWidget);
    expect(find.text('Recent Transcripts'), findsOneWidget);
  });
}
