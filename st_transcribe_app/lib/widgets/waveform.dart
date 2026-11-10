import 'package:flutter/material.dart';

import '../theme.dart';

/// Bar waveform driven ONLY by real microphone levels (0..1). When inactive it draws flat dots;
/// it never animates on its own.
class Waveform extends StatelessWidget {
  final List<double> levels;
  final bool active;
  final double height;
  const Waveform({super.key, required this.levels, required this.active, this.height = 72});

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return SizedBox(
      height: height,
      width: double.infinity,
      child: CustomPaint(painter: _WavePainter(levels, active, c.primaryBlue, c.cardBorder)),
    );
  }
}

class _WavePainter extends CustomPainter {
  final List<double> levels;
  final bool active;
  final Color on, off;
  _WavePainter(this.levels, this.active, this.on, this.off);

  @override
  void paint(Canvas canvas, Size size) {
    const bar = 4.0, gap = 4.0;
    final n = (size.width / (bar + gap)).floor();
    final paint = Paint()..strokeCap = StrokeCap.round..strokeWidth = bar;
    final mid = size.height / 2;
    for (var i = 0; i < n; i++) {
      final idx = levels.length - n + i;
      final raw = (active && idx >= 0) ? levels[idx] : 0.0;
      // x4 gain so ordinary speech (low RMS) is visible; still a monotonic function of the real RMS.
      final h = (raw <= 0 ? bar : (bar + (size.height - bar) * (raw * 4).clamp(0.0, 1.0))).toDouble();
      paint.color = active && raw > 0 ? on : off;
      final x = i * (bar + gap) + bar / 2;
      canvas.drawLine(Offset(x, mid - h / 2), Offset(x, mid + h / 2), paint);
    }
  }

  @override
  bool shouldRepaint(_WavePainter o) => o.levels.length != levels.length || o.active != active ||
      (levels.isNotEmpty && o.levels.isNotEmpty && o.levels.last != levels.last);
}
