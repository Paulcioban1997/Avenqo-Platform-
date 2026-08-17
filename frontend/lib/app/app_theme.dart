import 'package:flutter/material.dart';

class AppTheme {
  const AppTheme._();

  static ThemeData get light {
    const navy = Color(0xFF16324F);
    const teal = Color(0xFF007C83);
    const canvas = Color(0xFFF4F7F8);
    final colors = ColorScheme.fromSeed(
      seedColor: teal,
      primary: navy,
      secondary: teal,
      surface: Colors.white,
    );
    return ThemeData(
      useMaterial3: true,
      colorScheme: colors,
      scaffoldBackgroundColor: canvas,
      fontFamily: 'Aptos',
      textTheme: const TextTheme(
        headlineMedium: TextStyle(fontWeight: FontWeight.w700, color: Color(0xFF16324F)),
        titleLarge: TextStyle(fontWeight: FontWeight.w700, color: Color(0xFF16324F)),
      ),
      cardTheme: const CardThemeData(
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(8)),
          side: BorderSide(color: Color(0xFFDDE5E8)),
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
    );
  }
}
