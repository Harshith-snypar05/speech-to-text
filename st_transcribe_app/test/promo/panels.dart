// Promo panel layouts for the Play Store listing (1080x1920). Test-only helper.
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

const _primary = Color(0xFF6A00FF);
const _secondary = Color(0xFFA855F7);
const _accent = Color(0xFFE9D5FF);
const _bg = Color(0xFFF8F7FF);
const _text = Color(0xFF0F172A);

class PanelSpec {
  const PanelSpec({
    required this.headline,
    required this.highlight,
    required this.support,
    required this.logo,
    required this.phoneContent,
  });

  final String headline;
  final String highlight;
  final String support;
  final ui.Image logo;
  final Widget phoneContent;
}

TextStyle _t(double size, FontWeight w,
        {Color color = _text, double? lh, double? ls, double opacity = 1}) =>
    TextStyle(
      fontFamily: 'Inter',
      fontSize: size,
      fontVariations: [FontVariation('wght', w.value.toDouble())],
      color: color.withValues(alpha: opacity),
      height: lh == null ? null : lh / size,
      letterSpacing: ls,
      decoration: TextDecoration.none,
    );

Widget buildPanel(PanelSpec s) {
  const barHeights = [90, 150, 230, 330, 440, 520, 440, 330, 420, 520, 600, 520, 420, 300, 200, 130, 80];
  final hi = s.headline.indexOf(s.highlight);
  return Directionality(
    textDirection: TextDirection.ltr,
    child: SizedBox(
      width: 1080,
      height: 1920,
      child: Stack(clipBehavior: Clip.hardEdge, children: [
        const Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [Color(0xFF1B0B33), Color(0xFF2B0F52)],
              ),
            ),
          ),
        ),
        Positioned(
          left: -10,
          top: 900,
          width: 1100,
          height: 1100,
          child: ImageFiltered(
            imageFilter: ui.ImageFilter.blur(sigmaX: 110, sigmaY: 110),
            child: DecoratedBox(
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: _primary.withValues(alpha: 0.28 * 2.2),
              ),
            ),
          ),
        ),
        Positioned(
          left: (1080 - 862) / 2,
          top: 880,
          width: 862,
          height: 600,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              for (final h in barHeights)
                Container(
                  width: 30,
                  height: h.toDouble(),
                  decoration: BoxDecoration(
                    color: _secondary.withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(15),
                  ),
                ),
            ],
          ),
        ),
        Positioned(
          left: 84,
          top: 81,
          width: 340,
          height: 110,
          child: RawImage(image: s.logo, fit: BoxFit.contain, alignment: Alignment.centerLeft),
        ),
        Positioned(
          left: 80,
          top: 250,
          width: 920,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text.rich(
              TextSpan(children: [
                TextSpan(text: s.headline.substring(0, hi)),
                TextSpan(text: s.highlight, style: const TextStyle(color: _secondary)),
                TextSpan(text: s.headline.substring(hi + s.highlight.length)),
              ]),
              style: _t(96, FontWeight.w700, color: _bg, lh: 102, ls: -1.5),
            ),
            const SizedBox(height: 28),
            Text(s.support, style: _t(44, FontWeight.w400, color: _accent, lh: 60, opacity: 0.92)),
          ]),
        ),
        Positioned(
          left: 210,
          top: 820,
          width: 660,
          height: 1200,
          child: Container(
            decoration: BoxDecoration(
              color: const Color(0xFF0F0A1E),
              borderRadius: BorderRadius.circular(84),
              border: Border.all(color: _secondary.withValues(alpha: 0.55), width: 4),
              boxShadow: [
                BoxShadow(color: _primary.withValues(alpha: 0.5), blurRadius: 140),
              ],
            ),
            padding: const EdgeInsets.all(20),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(66),
              child: Container(color: _bg, child: s.phoneContent),
            ),
          ),
        ),
      ]),
    ),
  );
}

/// Outline microphone on a 24-unit grid, scaled to the paint size.
class _MicPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final k = size.width / 24;
    final p = Paint()
      ..color = Colors.white
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2 * k
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    canvas.drawRRect(RRect.fromRectAndRadius(Rect.fromLTRB(9 * k, 2 * k, 15 * k, 15 * k), Radius.circular(3 * k)), p);
    canvas.drawArc(Rect.fromLTRB(5 * k, 5 * k, 19 * k, 19 * k), 0, 3.14159265, false, p);
    canvas.drawLine(Offset(12 * k, 19 * k), Offset(12 * k, 22 * k), p);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

Widget _bars(List<double> hs) => Row(mainAxisSize: MainAxisSize.min, children: [
      for (var i = 0; i < hs.length; i++) ...[
        if (i > 0) const SizedBox(width: 14),
        Container(
          width: 14,
          height: hs[i],
          decoration: BoxDecoration(color: _secondary, borderRadius: BorderRadius.circular(7)),
        ),
      ],
    ]);

PanelSpec panelLive(ui.Image logo) => PanelSpec(
      headline: 'Words appear as you speak',
      highlight: 'appear',
      support: 'Live transcription, instantly.',
      logo: logo,
      phoneContent: Stack(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(36, 48, 36, 36),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
              Text('Live session', style: _t(38, FontWeight.w600)),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 8),
                decoration: BoxDecoration(
                  color: _primary.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(100),
                ),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  Container(
                    width: 14,
                    height: 14,
                    decoration: const BoxDecoration(color: Color(0xFFEF4444), shape: BoxShape.circle),
                  ),
                  const SizedBox(width: 10),
                  Text('LIVE', style: _t(24, FontWeight.w700, color: _primary, ls: 1)),
                ]),
              ),
            ]),
            const SizedBox(height: 24),
            Text('Team review  ·  00:12:48', style: _t(26, FontWeight.w400, color: const Color(0xFF64748B))),
            const SizedBox(height: 24),
            Text('Good morning everyone, thanks for joining today’s review.',
                style: _t(36, FontWeight.w500, lh: 52, opacity: 0.45)),
            const SizedBox(height: 22),
            Text('Let’s start with the numbers from last quarter.',
                style: _t(36, FontWeight.w500, lh: 52, opacity: 0.7)),
            const SizedBox(height: 22),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(28),
              decoration: BoxDecoration(
                color: _primary.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(28),
                border: Border.all(color: _primary.withValues(alpha: 0.25), width: 2),
              ),
              child: Text('Revenue grew by twelve percent across all regions',
                  style: _t(36, FontWeight.w600, lh: 52)),
            ),
          ]),
        ),
        Positioned(
          left: 36,
          top: 850,
          width: 548,
          height: 190,
          child: Row(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.center, children: [
            _bars(const [30, 54, 80, 54, 94]),
            const SizedBox(width: 14),
            Container(
              width: 128,
              height: 128,
              decoration: BoxDecoration(
                color: _primary,
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(color: _primary.withValues(alpha: 0.45), blurRadius: 36, offset: const Offset(0, 12)),
                ],
              ),
              child: Center(child: CustomPaint(size: const Size(56, 56), painter: _MicPainter())),
            ),
            const SizedBox(width: 14),
            _bars(const [94, 54, 80, 54, 30]),
          ]),
        ),
      ]),
    );
