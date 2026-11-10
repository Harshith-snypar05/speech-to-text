import 'package:flutter/material.dart';

/// App-specific palette, exposed as a ThemeExtension so screens can read
/// AppColors.of(context) and get the right light/dark values automatically
/// through MaterialApp's theme/darkTheme/themeMode -- same mechanism as any
/// other Theme.of(context) lookup, just for colors this design needs that
/// aren't part of Flutter's standard ColorScheme.
class AppColors extends ThemeExtension<AppColors> {
  final Color primaryBlue;
  final Color recordRed;
  final Color header;
  final Color bg;
  final Color textPrimary;
  final Color textSecondary;
  final Color lightBlueBg;
  final Color cardBorder;
  final Color liveGreen;
  final Color idleGrayDot;
  final Color surface;
  final Color sheetHandle;
  final Color neutralChipBg;

  const AppColors({
    required this.primaryBlue,
    required this.recordRed,
    required this.header,
    required this.bg,
    required this.textPrimary,
    required this.textSecondary,
    required this.lightBlueBg,
    required this.cardBorder,
    required this.liveGreen,
    required this.idleGrayDot,
    required this.surface,
    required this.sheetHandle,
    required this.neutralChipBg,
  });

  /// ScriptLiv palette from the img_ref design: primary #6A00FF, secondary #A855F7,
  /// accent #E9D5FF, background #F8F7FF, text #0F172A. (Field names kept from the
  /// previous blue theme; `primaryBlue` now holds the primary purple.)
  static const light = AppColors(
    primaryBlue: Color(0xFF6A00FF),
    recordRed: Color(0xFFE5383B),
    header: Color(0xFF0F172A),
    bg: Color(0xFFF8F7FF),
    textPrimary: Color(0xFF0F172A),
    textSecondary: Color(0xFF64748B),
    lightBlueBg: Color(0xFFE9D5FF),
    cardBorder: Color(0xFFE4DDF5),
    liveGreen: Color(0xFF34C759),
    idleGrayDot: Color(0xFF9CA3AF),
    surface: Colors.white,
    sheetHandle: Color(0xFFE9ECEF),
    neutralChipBg: Color(0xFFF3F4F6),
  );

  static const dark = AppColors(
    primaryBlue: Color(0xFFA855F7),
    recordRed: Color(0xFFFF6B6F),
    header: Color(0xFF0B0A1A),
    bg: Color(0xFF0B0A14),
    textPrimary: Color(0xFFF2F3F5),
    textSecondary: Color(0xFF9AA0A6),
    lightBlueBg: Color(0xFF2A1A4D),
    cardBorder: Color(0xFF24272C),
    liveGreen: Color(0xFF34C759),
    idleGrayDot: Color(0xFF6B7076),
    surface: Color(0xFF15131F),
    sheetHandle: Color(0xFF2C2F34),
    neutralChipBg: Color(0xFF1E2126),
  );

  static AppColors of(BuildContext context) => Theme.of(context).extension<AppColors>() ?? light;

  @override
  AppColors copyWith({
    Color? primaryBlue,
    Color? recordRed,
    Color? header,
    Color? bg,
    Color? textPrimary,
    Color? textSecondary,
    Color? lightBlueBg,
    Color? cardBorder,
    Color? liveGreen,
    Color? idleGrayDot,
    Color? surface,
    Color? sheetHandle,
    Color? neutralChipBg,
  }) {
    return AppColors(
      primaryBlue: primaryBlue ?? this.primaryBlue,
      recordRed: recordRed ?? this.recordRed,
      header: header ?? this.header,
      bg: bg ?? this.bg,
      textPrimary: textPrimary ?? this.textPrimary,
      textSecondary: textSecondary ?? this.textSecondary,
      lightBlueBg: lightBlueBg ?? this.lightBlueBg,
      cardBorder: cardBorder ?? this.cardBorder,
      liveGreen: liveGreen ?? this.liveGreen,
      idleGrayDot: idleGrayDot ?? this.idleGrayDot,
      surface: surface ?? this.surface,
      sheetHandle: sheetHandle ?? this.sheetHandle,
      neutralChipBg: neutralChipBg ?? this.neutralChipBg,
    );
  }

  @override
  AppColors lerp(ThemeExtension<AppColors>? other, double t) {
    if (other is! AppColors) return this;
    return AppColors(
      primaryBlue: Color.lerp(primaryBlue, other.primaryBlue, t)!,
      recordRed: Color.lerp(recordRed, other.recordRed, t)!,
      header: Color.lerp(header, other.header, t)!,
      bg: Color.lerp(bg, other.bg, t)!,
      textPrimary: Color.lerp(textPrimary, other.textPrimary, t)!,
      textSecondary: Color.lerp(textSecondary, other.textSecondary, t)!,
      lightBlueBg: Color.lerp(lightBlueBg, other.lightBlueBg, t)!,
      cardBorder: Color.lerp(cardBorder, other.cardBorder, t)!,
      liveGreen: Color.lerp(liveGreen, other.liveGreen, t)!,
      idleGrayDot: Color.lerp(idleGrayDot, other.idleGrayDot, t)!,
      surface: Color.lerp(surface, other.surface, t)!,
      sheetHandle: Color.lerp(sheetHandle, other.sheetHandle, t)!,
      neutralChipBg: Color.lerp(neutralChipBg, other.neutralChipBg, t)!,
    );
  }
}

ThemeData _themeFor(AppColors colors, Brightness brightness) {
  return ThemeData(
    useMaterial3: true,
    brightness: brightness,
    scaffoldBackgroundColor: colors.bg,
    colorScheme: ColorScheme.fromSeed(
      seedColor: colors.primaryBlue,
      brightness: brightness,
      primary: colors.primaryBlue,
      surface: colors.bg,
    ),
    fontFamily: null, // platform default (Roboto on Android, SF on iOS)
    appBarTheme: AppBarTheme(
      backgroundColor: colors.bg,
      foregroundColor: colors.textPrimary,
      elevation: 0,
      centerTitle: false,
    ),
    extensions: [colors],
  );
}

final appTheme = _themeFor(AppColors.light, Brightness.light);
final appDarkTheme = _themeFor(AppColors.dark, Brightness.dark);

/// Brand gradient used for primary actions and the recording button.
const brandGradient = LinearGradient(
  begin: Alignment.topLeft,
  end: Alignment.bottomRight,
  colors: [Color(0xFF6A00FF), Color(0xFFA855F7)],
);
