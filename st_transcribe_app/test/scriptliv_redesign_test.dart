import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:st_transcribe/screens/splash_screen.dart';
import 'package:st_transcribe/services/transcription_client.dart';
import 'package:st_transcribe/theme.dart';
import 'package:st_transcribe/widgets/waveform.dart';

Uint8List pcm(List<int> samples) {
  final b = ByteData(samples.length * 2);
  for (var i = 0; i < samples.length; i++) {
    b.setInt16(i * 2, samples[i], Endian.little);
  }
  return b.buffer.asUint8List();
}

void main() {
  group('pcm16Rms (real mic level)', () {
    test('silence is 0', () => expect(pcm16Rms(pcm([0, 0, 0, 0])), 0));
    test('empty is 0', () => expect(pcm16Rms(<int>[]), 0));
    test('full-scale square is ~1', () => expect(pcm16Rms(pcm([32767, -32768, 32767, -32768])), closeTo(1.0, 0.01)));
    test('half amplitude is ~0.5', () => expect(pcm16Rms(pcm([16384, -16384, 16384, -16384])), closeTo(0.5, 0.01)));
  });

  testWidgets('waveform renders flat when inactive and with levels when active', (t) async {
    await t.pumpWidget(MaterialApp(theme: appTheme, home: const Scaffold(body: Waveform(levels: [0.1, 0.2], active: false))));
    expect(find.byType(Waveform), findsOneWidget);
    await t.pumpWidget(MaterialApp(theme: appTheme, home: const Scaffold(body: Waveform(levels: [0.1, 0.2], active: true))));
    expect(find.byType(Waveform), findsOneWidget);
  });

  testWidgets('onboarding: Next then Get Started calls onDone', (t) async {
    var done = false;
    await t.pumpWidget(MaterialApp(theme: appTheme, home: OnboardingScreen(onDone: () => done = true)));
    expect(find.text('Next'), findsOneWidget);
    await t.tap(find.text('Next'));
    await t.pumpAndSettle();
    expect(find.text('Get Started'), findsOneWidget);
    await t.tap(find.text('Get Started'));
    expect(done, isTrue);
  });

  test('theme uses the img_ref palette', () {
    expect(AppColors.light.primaryBlue, const Color(0xFF6A00FF));
    expect(AppColors.light.bg, const Color(0xFFF8F7FF));
    expect(AppColors.light.textPrimary, const Color(0xFF0F172A));
  });
}
