import 'package:flutter/material.dart';

/// Centralized theme-aware semantic tokens for surfaces/text/borders shared
/// by the client app and the Platform Admin Command Center. Brand accent
/// (blue) and semantic status colors (success/warning/danger) are
/// intentionally identical in both themes — only surface/text/border tokens
/// flip between light and dark.
@immutable
class AvenqoColors extends ThemeExtension<AvenqoColors> {
  const AvenqoColors({
    required this.ink,
    required this.muted,
    required this.line,
    required this.canvas,
    required this.surface,
  });

  final Color ink;
  final Color muted;
  final Color line;
  final Color canvas;
  final Color surface;

  static const light = AvenqoColors(
    ink: Color(0xFF080B12),
    muted: Color(0xFF5C6472),
    line: Color(0xFFE4E8ED),
    canvas: Color(0xFFF4F6FA),
    surface: Colors.white,
  );

  static const dark = AvenqoColors(
    ink: Color(0xFFF2F5F9),
    muted: Color(0xFF9AA7B8),
    line: Color(0xFF25313F),
    canvas: Color(0xFF0B0F16),
    surface: Color(0xFF121B29),
  );

  static AvenqoColors of(BuildContext context) =>
      Theme.of(context).extension<AvenqoColors>() ?? light;

  @override
  AvenqoColors copyWith({Color? ink, Color? muted, Color? line, Color? canvas, Color? surface}) {
    return AvenqoColors(
      ink: ink ?? this.ink,
      muted: muted ?? this.muted,
      line: line ?? this.line,
      canvas: canvas ?? this.canvas,
      surface: surface ?? this.surface,
    );
  }

  @override
  AvenqoColors lerp(ThemeExtension<AvenqoColors>? other, double t) {
    if (other is! AvenqoColors) return this;
    return AvenqoColors(
      ink: Color.lerp(ink, other.ink, t)!,
      muted: Color.lerp(muted, other.muted, t)!,
      line: Color.lerp(line, other.line, t)!,
      canvas: Color.lerp(canvas, other.canvas, t)!,
      surface: Color.lerp(surface, other.surface, t)!,
    );
  }
}
