import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:st_transcribe/screens/session_screen.dart';
import 'package:st_transcribe/theme.dart';

void main() {
  Future<void> pumpAt(WidgetTester tester, Size size) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(theme: appTheme, home: const SessionScreen()));
    await tester.pump();
  }

  testWidgets('transcript on top, mic dock at the bottom, nothing draggable', (tester) async {
    await pumpAt(tester, const Size(360, 640));
    expect(find.byType(DraggableScrollableSheet), findsNothing);
    expect(find.text('Transcription'), findsOneWidget);
    expect(find.text('Ready'), findsOneWidget);
    expect(find.text('Tap to start'), findsOneWidget);
    final transcriptY = tester.getTopLeft(find.text('Transcription')).dy;
    final micY = tester.getTopLeft(find.byKey(const Key('mic_button'))).dy;
    expect(transcriptY, lessThan(micY));
    // the mic dock sits at the very bottom of the screen
    expect(tester.getBottomLeft(find.byKey(const Key('mic_button'))).dy, greaterThan(640 * 0.7));
    // pause / end only appear once a session is running
    expect(find.byKey(const Key('pause_resume_button')), findsNothing);
    expect(find.byKey(const Key('end_session_button')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('short phone does not overflow', (tester) async {
    await pumpAt(tester, const Size(360, 560));
    expect(tester.takeException(), isNull);
  });
}
