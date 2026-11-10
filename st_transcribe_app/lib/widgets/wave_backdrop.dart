import 'package:flutter/material.dart';

import '../theme.dart';

/// Ambient violet canvas behind every screen: base colour, soft purple glows and
/// two blurred swoosh shapes (the reference landing-page backdrop). Scaffolds are
/// transparent so this shows through.
class WaveBackdrop extends StatelessWidget {
  final Widget child;
  const WaveBackdrop({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final dark = Theme.of(context).brightness == Brightness.dark;
    return ColoredBox(
      color: c.bg,
      child: Stack(
        fit: StackFit.expand,
        children: [
          IgnorePointer(child: CustomPaint(painter: _WavePainter(dark: dark))),
          child,
        ],
      ),
    );
  }
}

class _WavePainter extends CustomPainter {
  final bool dark;
  _WavePainter({required this.dark});

  @override
  void paint(Canvas canvas, Size size) {
    final a = dark ? 1.0 : 0.35;
    void glow(Offset center, double radius, Color color) {
      final paint = Paint()
        ..shader = RadialGradient(colors: [color, color.withValues(alpha: 0)])
            .createShader(Rect.fromCircle(center: center, radius: radius));
      canvas.drawCircle(center, radius, paint);
    }

    glow(Offset(size.width * 0.95, 0), size.width * 0.9, const Color(0xFF8F05F4).withValues(alpha: 0.26 * a));
    glow(Offset(0, size.height), size.width * 0.9, const Color(0xFF6701EB).withValues(alpha: 0.28 * a));

    Path swoosh(double w, double h) => Path()
      ..moveTo(w, 0)
      ..cubicTo(w * 1.02, h * 0.4, w * 0.8, h * 0.62, w * 0.5, h * 0.52)
      ..cubicTo(w * 0.28, h * 0.45, w * 0.12, h * 0.2, w * 0.05, 0)
      ..close();

    final blur = MaskFilter.blur(BlurStyle.normal, size.width * 0.05);
    canvas.save();
    canvas.translate(size.width * 0.1, -size.height * 0.05);
    canvas.drawPath(
      swoosh(size.width, size.height * 0.45),
      Paint()
        ..maskFilter = blur
        ..color = const Color(0xFF8F05F4).withValues(alpha: 0.3 * a),
    );
    canvas.restore();
    canvas.save();
    canvas.translate(-size.width * 0.45, size.height * 0.62);
    canvas.drawPath(
      swoosh(size.width * 1.2, size.height * 0.4),
      Paint()
        ..maskFilter = blur
        ..color = const Color(0xFF2A0F8A).withValues(alpha: 0.38 * a),
    );
    canvas.restore();
  }

  @override
  bool shouldRepaint(_WavePainter old) => old.dark != dark;
}
