import 'package:flutter/material.dart';

import '../theme.dart';
import 'history_screen.dart';
import 'home_screen.dart';
import '../widgets/brand.dart';
import 'settings_screen.dart';

/// Top header (logo + Settings beside it) and bottom navigation: Home / Transcripts with a centre microphone button that opens
/// the recording screen (matches the img_ref storyboard). Tabs are kept alive.
class AppShell extends StatefulWidget {
  const AppShell({super.key});
  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int _tab = 0;
  int _refresh = 0; // bumped after a recording so Home/History reload

  Future<void> _record() async {
    await Navigator.of(context).pushNamed('/session');
    if (mounted) setState(() => _refresh++);
  }

  void _openSettings() => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const SettingsScreen()));

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBody: true, // content scrolls behind the floating nav; no solid strip behind it
      body: Column(
        children: [
          _Header(onSettings: _openSettings),
          Expanded(
            child: MediaQuery.removePadding(
              context: context,
              removeTop: true,
              child: IndexedStack(
                index: _tab,
                children: [
                  HomeScreen(key: ValueKey('home$_refresh'), onStartRecording: _record, onSeeAll: () => setState(() => _tab = 1)),
                  HistoryScreen(key: ValueKey('hist$_refresh')),
                ],
              ),
            ),
          ),
        ],
      ),
      bottomNavigationBar: _NotchNavBar(
        tab: _tab,
        onTab: (i) => setState(() => _tab = i),
        onRecord: _record,
      ),
    );
  }
}

/// Floating pill nav: labelled tabs (the active one sits in a soft highlight pill) around a curved notch that cradles the
/// round microphone button, which overhangs the bar.
class _NotchNavBar extends StatelessWidget {
  final int tab;
  final ValueChanged<int> onTab;
  final VoidCallback onRecord;
  const _NotchNavBar({required this.tab, required this.onTab, required this.onRecord});

  static const double _barHeight = 66;
  static const double _micSize = 60;
  static const double _overhang = _micSize / 2;
  static const double _notchGap = 92; // width of the middle slot between the two tabs

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final bottom = MediaQuery.of(context).padding.bottom;
    return Container(
      color: Colors.transparent,
      padding: EdgeInsets.fromLTRB(16, 0, 16, bottom + 10),
      height: _overhang + _barHeight + bottom + 10,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            height: _barHeight,
            child: CustomPaint(
              painter: _NotchPainter(color: c.surface, border: c.cardBorder),
              child: Row(
                children: [
                  Expanded(child: _NavTab(icon: Icons.home_outlined, activeIcon: Icons.home_rounded, label: 'Home', selected: tab == 0, onTap: () => onTab(0))),
                  const SizedBox(width: _notchGap),
                  Expanded(child: _NavTab(icon: Icons.description_outlined, activeIcon: Icons.description_rounded, label: 'Transcripts', selected: tab == 1, onTap: () => onTab(1))),
                ],
              ),
            ),
          ),
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: Center(child: _RecordButton(size: _micSize, onTap: onRecord)),
          ),
        ],
      ),
    );
  }
}

class _NavTab extends StatelessWidget {
  final IconData icon;
  final IconData activeIcon;
  final String label;
  final bool selected;
  final VoidCallback onTap;
  const _NavTab({required this.icon, required this.activeIcon, required this.label, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final color = selected ? c.primaryBlue : c.textSecondary;
    return Semantics(
      label: label,
      button: true,
      selected: selected,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Center(
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 180),
            curve: Curves.easeOut,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 7),
            decoration: BoxDecoration(
              color: selected ? c.primaryBlue.withValues(alpha: 0.13) : Colors.transparent,
              borderRadius: BorderRadius.circular(22),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(selected ? activeIcon : icon, color: color, size: 23),
                const SizedBox(height: 2),
                Text(label, maxLines: 1, style: TextStyle(fontSize: 11, fontWeight: selected ? FontWeight.w800 : FontWeight.w600, color: color)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Rounded bar with a smooth semicircular-ish dip in the top centre.
class _NotchPainter extends CustomPainter {
  final Color color;
  final Color border;
  const _NotchPainter({required this.color, required this.border});

  static const double _radius = 33;
  static const double _halfWidth = 40; // half-width of the dip
  static const double _depth = 34;

  Path _path(Size size) {
    final w = size.width;
    final h = size.height;
    final cx = w / 2;
    const r = _radius;
    return Path()
      ..moveTo(r, 0)
      ..lineTo(cx - _halfWidth - 16, 0)
      ..cubicTo(cx - _halfWidth + 4, 0, cx - _halfWidth + 6, _depth, cx, _depth)
      ..cubicTo(cx + _halfWidth - 6, _depth, cx + _halfWidth - 4, 0, cx + _halfWidth + 16, 0)
      ..lineTo(w - r, 0)
      ..arcToPoint(Offset(w, r), radius: const Radius.circular(r))
      ..lineTo(w, h - r)
      ..arcToPoint(Offset(w - r, h), radius: const Radius.circular(r))
      ..lineTo(r, h)
      ..arcToPoint(Offset(0, h - r), radius: const Radius.circular(r))
      ..lineTo(0, r)
      ..arcToPoint(const Offset(r, 0), radius: const Radius.circular(r))
      ..close();
  }

  @override
  void paint(Canvas canvas, Size size) {
    final path = _path(size);
    canvas.drawShadow(path, Colors.black.withValues(alpha: 0.35), 10, false);
    canvas.drawPath(path, Paint()..color = color);
    canvas.drawPath(
      path,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 0.8
        ..color = border,
    );
  }

  @override
  bool shouldRepaint(_NotchPainter old) => old.color != color || old.border != border;
}

/// The centre record action: a round gradient button resting in the notch.
class _RecordButton extends StatelessWidget {
  final double size;
  final VoidCallback onTap;
  const _RecordButton({required this.size, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Start recording',
      button: true,
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            gradient: centerActionGradient,
            shape: BoxShape.circle,
            boxShadow: [BoxShadow(color: const Color(0xFFE0239C).withValues(alpha: 0.4), blurRadius: 14, spreadRadius: 1, offset: const Offset(0, 4))],
          ),
          child: const Icon(Icons.mic, color: Colors.white, size: 28),
        ),
      ),
    );
  }
}

/// Logo on the left, Settings in the top-right corner, so it is always one tap away.
class _Header extends StatelessWidget {
  final VoidCallback onSettings;
  const _Header({required this.onSettings});

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return Material(
      color: Colors.transparent,
      child: SafeArea(
        bottom: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 4, 4),
          child: Row(
            children: [
              const ScriptLivLogo(height: 32),
              const Spacer(),
              Semantics(
                label: 'Settings',
                button: true,
                child: IconButton(
                  tooltip: 'Settings',
                  onPressed: onSettings,
                  padding: const EdgeInsets.all(8),
                  constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
                  icon: Icon(Icons.settings_outlined, color: c.textSecondary, size: 26),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
