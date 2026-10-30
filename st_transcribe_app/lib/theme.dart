import 'package:flutter/material.dart';

/// Colors sampled directly from the reference design
/// (ST Live Transcription App Showcase.png).
class AppColors {
  static const primaryBlue = Color(0xFF009FFD);
  static const recordRed = Color(0xFFFB2124);
  static const darkHeader = Color(0xFF030A0E);
  static const bgLight = Color(0xFFFBFCFE);
  static const textPrimary = Color(0xFF111319);
  static const textSecondary = Color(0xFF71777F);
  static const lightBlueBg = Color(0xFFE3F0FD);
  static const cardBorder = Color(0xFFE9ECEF);
  static const liveGreen = Color(0xFF34C759);
  static const idleGrayDot = Color(0xFF9CA3AF);
}

final appTheme = ThemeData(
  useMaterial3: true,
  scaffoldBackgroundColor: AppColors.bgLight,
  colorScheme: ColorScheme.fromSeed(
    seedColor: AppColors.primaryBlue,
    primary: AppColors.primaryBlue,
    surface: AppColors.bgLight,
  ),
  fontFamily: 'SF Pro', // falls back to platform default if unavailable
  appBarTheme: const AppBarTheme(
    backgroundColor: AppColors.bgLight,
    foregroundColor: AppColors.textPrimary,
    elevation: 0,
    centerTitle: false,
  ),
);
