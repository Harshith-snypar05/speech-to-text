import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../theme.dart';
import '../widgets/brand.dart';
import 'auth_gate.dart';

const _kOnboarded = 'onboarding_done_v1';

/// Splash -> (first launch only) two onboarding pages -> AuthGate.
class AppFlow extends StatefulWidget {
  const AppFlow({super.key});
  @override
  State<AppFlow> createState() => _AppFlowState();
}

enum _Stage { splash, onboarding, app }

class _AppFlowState extends State<AppFlow> {
  _Stage _stage = _Stage.splash;

  @override
  void initState() {
    super.initState();
    _boot();
  }

  Future<void> _boot() async {
    bool done = false;
    try {
      done = (await SharedPreferences.getInstance()).getBool(_kOnboarded) ?? false;
    } catch (_) {}
    await Future<void>.delayed(const Duration(milliseconds: 1100));
    if (mounted) setState(() => _stage = done ? _Stage.app : _Stage.onboarding);
  }

  Future<void> _finish() async {
    try {
      await (await SharedPreferences.getInstance()).setBool(_kOnboarded, true);
    } catch (_) {}
    if (mounted) setState(() => _stage = _Stage.app);
  }

  @override
  Widget build(BuildContext context) {
    switch (_stage) {
      case _Stage.splash:
        return const SplashScreen();
      case _Stage.onboarding:
        return OnboardingScreen(onDone: _finish);
      case _Stage.app:
        return const AuthGate();
    }
  }
}

class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});
  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const ScriptLivLogo(height: 64),
            const SizedBox(height: 14),
            Text('Real-time speech to text', style: TextStyle(color: c.textSecondary, fontSize: 15)),
          ],
        ),
      ),
    );
  }
}

class OnboardingScreen extends StatefulWidget {
  final VoidCallback onDone;
  const OnboardingScreen({super.key, required this.onDone});
  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final _pc = PageController();
  int _page = 0;

  static const _pages = [
    (Icons.mic_none_rounded, 'Speak, we transcribe', 'Tap the microphone and your words appear as you speak, in real time.'),
    (Icons.lock_outline_rounded, 'Yours to keep', 'Sessions are saved to your account. Audio is stored encrypted, and you see only your own data.'),
  ];

  @override
  void dispose() {
    _pc.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            children: [
              Align(alignment: Alignment.centerRight, child: TextButton(onPressed: widget.onDone, child: const Text('Skip'))),
              Expanded(
                child: PageView(
                  controller: _pc,
                  onPageChanged: (i) => setState(() => _page = i),
                  children: [
                    for (final p in _pages)
                      Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Container(
                            width: 140,
                            height: 140,
                            decoration: BoxDecoration(color: c.lightBlueBg, shape: BoxShape.circle),
                            child: Icon(p.$1, size: 64, color: c.primaryBlue),
                          ),
                          const SizedBox(height: 32),
                          Text(p.$2, textAlign: TextAlign.center, style: TextStyle(fontSize: 26, fontWeight: FontWeight.w800, color: c.textPrimary)),
                          const SizedBox(height: 12),
                          Text(p.$3, textAlign: TextAlign.center, style: TextStyle(fontSize: 15, height: 1.5, color: c.textSecondary)),
                        ],
                      ),
                  ],
                ),
              ),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  for (var i = 0; i < _pages.length; i++)
                    AnimatedContainer(
                      duration: const Duration(milliseconds: 200),
                      margin: const EdgeInsets.all(4),
                      width: i == _page ? 22 : 8,
                      height: 8,
                      decoration: BoxDecoration(color: i == _page ? c.primaryBlue : c.cardBorder, borderRadius: BorderRadius.circular(4)),
                    ),
                ],
              ),
              const SizedBox(height: 20),
              GradientButton(
                label: _page == _pages.length - 1 ? 'Get Started' : 'Next',
                onPressed: () => _page == _pages.length - 1
                    ? widget.onDone()
                    : _pc.nextPage(duration: const Duration(milliseconds: 250), curve: Curves.easeOut),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
