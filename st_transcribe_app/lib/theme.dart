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

  /// ScriptLiv palette (matches the web app tokens): near-black violet canvas,
  /// translucent violet surfaces, one vivid purple. Field names kept from the
  /// earlier blue theme; `primaryBlue` holds the primary purple.
  static const light = AppColors(
    primaryBlue: Color(0xFF8400E6),
    recordRed: Color(0xFFDC2F45),
    header: Color(0xFF140B33),
    bg: Color(0xFFF8F5FF),
    textPrimary: Color(0xFF140B33),
    textSecondary: Color(0xFF4F4580),
    lightBlueBg: Color(0xFFEFE5FF),
    cardBorder: Color(0xFFDDD0F8),
    liveGreen: Color(0xFF12A672),
    idleGrayDot: Color(0xFF8F86BC),
    surface: Colors.white,
    sheetHandle: Color(0xFFDDD0F8),
    neutralChipBg: Color(0xFFF0E8FF),
  );

  static const dark = AppColors(
    primaryBlue: Color(0xFFB574FF),
    recordRed: Color(0xFFFF6B7E),
    header: Color(0xFF05040D),
    bg: Color(0xFF05040D),
    textPrimary: Color(0xFFFFFFFF),
    textSecondary: Color(0xFFC6C0EC),
    lightBlueBg: Color(0xFF1F1450),
    cardBorder: Color(0xFF2A2060),
    liveGreen: Color(0xFF34D399),
    idleGrayDot: Color(0xFF7A72B0),
    surface: Color(0xFF0E0A1F),
    sheetHandle: Color(0xFF2A2060),
    neutralChipBg: Color(0xFF181038),
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
    scaffoldBackgroundColor: Colors.transparent,
    colorScheme: ColorScheme.fromSeed(
      seedColor: colors.primaryBlue,
      brightness: brightness,
      primary: colors.primaryBlue,
      surface: colors.bg,
    ),
    fontFamily: 'PlusJakartaSans',
    appBarTheme: AppBarTheme(
      backgroundColor: Colors.transparent,
      foregroundColor: colors.textPrimary,
      elevation: 0,
      centerTitle: false,
    ),
    cardTheme: CardThemeData(
      color: colors.surface,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: BorderSide(color: colors.cardBorder),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        shape: const StadiumBorder(),
        minimumSize: const Size(0, 48),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        shape: const StadiumBorder(),
        minimumSize: const Size(0, 48),
        side: BorderSide(color: colors.cardBorder),
        foregroundColor: colors.textPrimary,
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: colors.bg.withValues(alpha: 0.7),
      contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(999), borderSide: BorderSide(color: colors.cardBorder)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(999), borderSide: BorderSide(color: colors.cardBorder)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(999), borderSide: BorderSide(color: colors.primaryBlue, width: 1.5)),
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
  colors: [Color(0xFF6701EB), Color(0xFFA810F8)],
);
