/// Visual language.
///
/// Colour carries meaning here and is used sparingly. Green is reserved for a
/// MEASURED edge - not for a bullish direction - so the interface never lets a
/// rising market look like a verified opportunity. Direction is rendered in a
/// neutral accent; only evidence gets green.
library;
import 'package:flutter/material.dart';

class AppColors {
  static const background = Color(0xFF0E1116);
  static const surface = Color(0xFF161B22);
  static const surfaceAlt = Color(0xFF1C2430);
  static const border = Color(0xFF2A3441);
  static const text = Color(0xFFE6EDF3);
  static const textMuted = Color(0xFF8B949E);

  static const accent = Color(0xFF58A6FF);   // neutral: direction, structure
  static const measured = Color(0xFF3FB950); // reserved: measured edge only
  static const warn = Color(0xFFD29922);     // no edge / unstable
  static const bad = Color(0xFFF85149);      // negative edge / failure
}

class AppTheme {
  static ThemeData get dark {
    final base = ThemeData.dark(useMaterial3: true);
    return base.copyWith(
      scaffoldBackgroundColor: AppColors.background,
      colorScheme: base.colorScheme.copyWith(
        primary: AppColors.accent,
        surface: AppColors.surface,
        error: AppColors.bad,
      ),
      cardTheme: CardThemeData(
        color: AppColors.surface,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(10),
          side: const BorderSide(color: AppColors.border),
        ),
        margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: AppColors.background,
        elevation: 0,
        centerTitle: false,
      ),
      textTheme: base.textTheme.apply(
        bodyColor: AppColors.text,
        displayColor: AppColors.text,
      ),
      dividerColor: AppColors.border,
    );
  }
}
