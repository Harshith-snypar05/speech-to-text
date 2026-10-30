import 'package:flutter/material.dart';

/// The ST compass/crosshair brand mark.
class StLogo extends StatelessWidget {
  final double size;
  const StLogo({super.key, this.size = 40});

  @override
  Widget build(BuildContext context) {
    return Image.asset(
      'assets/images/st_logo.png',
      width: size,
      height: size,
    );
  }
}
