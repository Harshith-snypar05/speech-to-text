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
      bottomNavigationBar: Container(
        padding: EdgeInsets.only(bottom: MediaQuery.of(context).padding.bottom, top: 8),
        height: 64 + MediaQuery.of(context).padding.bottom,
        decoration: BoxDecoration(
          color: AppColors.of(context).surface,
          borderRadius: const BorderRadius.only(topLeft: Radius.circular(28), topRight: Radius.circular(28)),
          border: Border(top: BorderSide(color: AppColors.of(context).cardBorder)),
          boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.08), blurRadius: 16, offset: const Offset(0, -4))],
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          children: [
            _NavIcon(icon: Icons.home_outlined, selected: _tab == 0, onTap: () => setState(() => _tab = 0)),
            _RecordButton(onTap: _record),
            _NavIcon(icon: Icons.description_outlined, selected: _tab == 1, onTap: () => setState(() => _tab = 1)),
          ],
        ),
      ),
    );
  }
}

/// Single flush icon inside the one-piece floating nav bar (iOS tab-bar style -- no separate boxes).
class _NavIcon extends StatelessWidget {
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;
  const _NavIcon({required this.icon, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return InkWell(
      customBorder: const CircleBorder(),
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Icon(icon, color: selected ? c.primaryBlue : c.textSecondary, size: 24),
      ),
    );
  }
}

/// The centre record action, inline with the other two icons (not floating/overlapping).
class _RecordButton extends StatelessWidget {
  final VoidCallback onTap;
  const _RecordButton({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Start recording',
      button: true,
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          width: 44,
          height: 44,
          decoration: BoxDecoration(
            gradient: centerActionGradient,
            shape: BoxShape.circle,
            boxShadow: [BoxShadow(color: const Color(0xFFE0239C).withValues(alpha: 0.4), blurRadius: 12, spreadRadius: 1)],
          ),
          child: const Icon(Icons.mic, color: Colors.white, size: 22),
        ),
      ),
    );
  }
}

/// Logo on the left with Settings directly beside it, so it is always one tap away.
class _Header extends StatelessWidget {
  final VoidCallback onSettings;
  const _Header({required this.onSettings});

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return Material(
      color: c.bg,
      child: SafeArea(
        bottom: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 12, 4),
          child: Row(
            children: [
              const ScriptLivLogo(height: 32),
              const SizedBox(width: 6),
              Container(width: 1, height: 20, color: c.cardBorder),
              const SizedBox(width: 2),
              Semantics(
                label: 'Settings',
                button: true,
                child: IconButton(
                  tooltip: 'Settings',
                  onPressed: onSettings,
                  icon: Icon(Icons.settings_outlined, color: c.textSecondary),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
