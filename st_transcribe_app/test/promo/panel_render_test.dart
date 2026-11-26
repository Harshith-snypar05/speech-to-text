// Renders Play Store promo panels to PNG. Not shipped in the app.
// Run: INTER_TTF=<path to Inter variable ttf> flutter test test/promo/panel_render_test.dart
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'panels.dart';

void main() {
  testWidgets('renders promo panels to PNG', (tester) async {
    final interPath = Platform.environment['INTER_TTF'];
    expect(interPath, isNotNull, reason: 'set INTER_TTF to the Inter variable ttf');
    final loader = FontLoader('Inter')
      ..addFont(Future.value(ByteData.sublistView(File(interPath!).readAsBytesSync())));
    await loader.load();

    final logo = File('../assets/branding/exports/horizontal-dark-1600.png');
    late ui.Image logoImage;
    await tester.runAsync(() async {
      final codec = await ui.instantiateImageCodec(logo.readAsBytesSync());
      logoImage = (await codec.getNextFrame()).image;
    });

    tester.view.physicalSize = const Size(1080, 1920);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    final key = GlobalKey();
    await tester.pumpWidget(RepaintBoundary(key: key, child: buildPanel(panelLive(logoImage))));
    await tester.pump();

    await tester.runAsync(() async {
      final boundary = key.currentContext!.findRenderObject() as RenderRepaintBoundary;
      final image = await boundary.toImage(pixelRatio: 1);
      expect(image.width, 1080);
      expect(image.height, 1920);
      final bytes = (await image.toByteData(format: ui.ImageByteFormat.png))!;
      final out = File('../docs/play_store_assets/panels/01-live.png');
      out.parent.createSync(recursive: true);
      out.writeAsBytesSync(bytes.buffer.asUint8List());
    });
  });
}
