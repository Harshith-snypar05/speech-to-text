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
    final c = AppColors.of(context);
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
      floatingActionButtonLocation: FloatingActionButtonLocation.centerDocked,
      floatingActionButton: Semantics(
        label: 'Start recording',
        button: true,
        child: GestureDetector(
          onTap: _record,
          child: Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              gradient: brandGradient,
              shape: BoxShape.circle,
              boxShadow: [BoxShadow(color: c.primaryBlue.withValues(alpha: 0.35), blurRadius: 16, offset: const Offset(0, 6))],
            ),
            child: const Icon(Icons.mic, color: Colors.white, size: 30),
          ),
        ),
      ),
      bottomNavigationBar: BottomAppBar(
        color: c.surface,
        shape: const CircularNotchedRectangle(),
        notchMargin: 8,
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Expanded(child: _NavItem(icon: Icons.home_outlined, label: 'Home', selected: _tab == 0, onTap: () => setState(() => _tab = 0))),
            const SizedBox(width: 88), // space for the centre button
            Expanded(child: _NavItem(icon: Icons.description_outlined, label: 'Transcripts', selected: _tab == 1, onTap: () => setState(() => _tab = 1))),
          ],
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool selected;
  final VoidCallback onTap;
  const _NavItem({required this.icon, required this.label, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final color = selected ? c.primaryBlue : c.textSecondary;
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, color: color),
          Text(label, style: TextStyle(fontSize: 11, color: color, fontWeight: selected ? FontWeight.w700 : FontWeight.w500)),
        ]),
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
