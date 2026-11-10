import 'package:flutter/material.dart';

import '../theme.dart';

/// ScriptLiv official logo (horizontal lockup) and emblem. Dark theme uses a variant with a light "Script".
class ScriptLivLogo extends StatelessWidget {
  final double height;
  const ScriptLivLogo({super.key, this.height = 32});

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    return Image.asset(
      dark ? 'assets/images/sl_logo_dark.png' : 'assets/images/sl_logo_light.png',
      height: height,
      semanticLabel: 'ScriptLiv',
    );
  }
}

class ScriptLivMark extends StatelessWidget {
  final double size;
  const ScriptLivMark({super.key, this.size = 40});
  @override
  Widget build(BuildContext context) =>
      Image.asset('assets/images/sl_emblem.png', height: size, semanticLabel: 'ScriptLiv');
}

/// Primary gradient button used across onboarding / sign in.
class GradientButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final bool busy;
  const GradientButton({super.key, required this.label, required this.onPressed, this.busy = false});

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null && !busy;
    return Opacity(
      opacity: enabled ? 1 : 0.6,
      child: Material(
        color: Colors.transparent,
        child: Ink(
          decoration: BoxDecoration(gradient: brandGradient, borderRadius: BorderRadius.circular(999)),
          child: InkWell(
            borderRadius: BorderRadius.circular(999),
            onTap: enabled ? onPressed : null,
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 16),
              child: Center(
                child: busy
                    ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : Text(label, style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w700)),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
