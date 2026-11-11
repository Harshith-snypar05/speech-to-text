import 'package:flutter/material.dart';

import '../theme.dart';

/// Ambient violet canvas behind every screen. Uses the same Figma-drawn satin wave art as the website
/// (scriptliv_web/public/brand/wave-*.png): hero sheets across the top-right, a lighter set along the bottom,
/// with a soft violet haze. Dark = black and violet, light = white and violet; both kept subtle.
/// Scaffolds are transparent so this shows through.
class WaveBackdrop extends StatelessWidget {
  final Widget child;
  const WaveBackdrop({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final dark = Theme.of(context).brightness == Brightness.dark;
    final suffix = dark ? 'dark' : 'light';
    final opacity = dark ? 0.5 : 0.42; // same as the web --wave-opacity
    final haze = const Color(0xFF6A24B0).withValues(alpha: dark ? 0.16 : 0.03);

    return ColoredBox(
      color: c.bg,
      child: Stack(
        fit: StackFit.expand,
        children: [
          IgnorePointer(
            child: LayoutBuilder(
              builder: (context, box) {
                final w = box.maxWidth;
                // On a tall phone the 16:9 art is shown wider than the screen, anchored top-right / bottom-right,
                // so the sheets read as large soft folds instead of a thin strip.
                final heroW = w * 1.9;
                final footW = w * 1.6;
                return Stack(
                  fit: StackFit.expand,
                  children: [
                    DecoratedBox(
                      decoration: BoxDecoration(
                        gradient: RadialGradient(center: const Alignment(0.25, -0.1), radius: 1.1, colors: [haze, haze.withValues(alpha: 0)]),
                      ),
                    ),
                    Positioned(
                      top: 0,
                      right: -heroW * 0.08,
                      width: heroW,
                      child: Opacity(
                        opacity: opacity,
                        child: ShaderMask(
                          blendMode: BlendMode.dstIn,
                          shaderCallback: (r) => const LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: [Colors.black, Colors.black, Colors.transparent],
                            stops: [0, 0.55, 0.98],
                          ).createShader(r),
                          child: Image.asset('assets/images/waves/wave_hero_$suffix.png', fit: BoxFit.fitWidth, filterQuality: FilterQuality.medium),
                        ),
                      ),
                    ),
                    Positioned(
                      bottom: 0,
                      right: -footW * 0.1,
                      width: footW,
                      child: Opacity(
                        opacity: opacity,
                        child: ShaderMask(
                          blendMode: BlendMode.dstIn,
                          shaderCallback: (r) => const LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: [Colors.transparent, Colors.black, Colors.black],
                            stops: [0, 0.45, 1],
                          ).createShader(r),
                          child: Image.asset('assets/images/waves/wave_footer_$suffix.png', fit: BoxFit.fitWidth, filterQuality: FilterQuality.medium),
                        ),
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
          child,
        ],
      ),
    );
  }
}
