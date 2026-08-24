import 'package:flutter/material.dart';
import 'package:avenqo/app/avenqo_colors.dart';

class AppTheme {
  const AppTheme._();

  static ThemeData get light {
    const blue = Color(0xFF087CF0);
    const canvas = Color(0xFFF4F6FA);
    final colors = ColorScheme.fromSeed(
      seedColor: blue,
      primary: blue,
      secondary: blue,
      surface: Colors.white,
    );
    return ThemeData(
      useMaterial3: true,
      colorScheme: colors,
      scaffoldBackgroundColor: canvas,
      fontFamily: 'Aptos',
      textTheme: const TextTheme(
        headlineMedium: TextStyle(fontWeight: FontWeight.w700, color: Color(0xFF080B12)),
        titleLarge: TextStyle(fontWeight: FontWeight.w700, color: Color(0xFF080B12)),
      ),
      cardTheme: const CardThemeData(
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(8)),
          side: BorderSide(color: Color(0xFFE4E8ED)),
        ),
      ),
      inputDecorationTheme: const InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.all(Radius.circular(6)),
        ),
      ),
      navigationRailTheme: const NavigationRailThemeData(
        backgroundColor: Colors.white,
        indicatorShape: RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(6)),
        ),
      ),
      extensions: const [AvenqoColors.light],
    );
  }

  static ThemeData get dark {
    const blue = Color(0xFF3FA0F5);
    const surface = Color(0xFF121B29);
    const canvas = Color(0xFF0B0F16);
    final colors = ColorScheme.fromSeed(
      seedColor: blue,
      brightness: Brightness.dark,
      primary: blue,
      secondary: blue,
      surface: surface,
    );
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: colors,
      scaffoldBackgroundColor: canvas,
      fontFamily: 'Aptos',
      appBarTheme: const AppBarTheme(backgroundColor: surface, foregroundColor: Colors.white),
      textTheme: const TextTheme(
        headlineMedium: TextStyle(fontWeight: FontWeight.w700, color: Colors.white),
        titleLarge: TextStyle(fontWeight: FontWeight.w700, color: Colors.white),
      ),
      cardTheme: const CardThemeData(
        elevation: 0,
        margin: EdgeInsets.zero,
        color: surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(8)),
          side: BorderSide(color: Color(0xFF262F38)),
        ),
      ),
      inputDecorationTheme: const InputDecorationTheme(
        filled: true,
        fillColor: surface,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.all(Radius.circular(6)),
        ),
      ),
      navigationRailTheme: const NavigationRailThemeData(
        backgroundColor: surface,
        indicatorShape: RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(6)),
        ),
      ),
      extensions: const [AvenqoColors.dark],
    );
  }
}
