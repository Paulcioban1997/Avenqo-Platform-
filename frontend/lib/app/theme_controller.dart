import 'package:flutter/material.dart';

import 'package:avenqo/core/token_store.dart';

/// Source de vérité unique du thème clair/sombre/système — même esprit que
/// `LocaleController` (persistance best-effort, jamais bloquante, aucune
/// dépendance directe à `FlutterSecureStorage` pour rester testable).
class ThemeController extends ChangeNotifier {
  ThemeController({ThemeMode initialMode = ThemeMode.light, ThemePreferenceStore? store})
      : _mode = initialMode,
        _store = store ?? const SecureThemePreferenceStore();

  final ThemePreferenceStore _store;
  ThemeMode _mode;

  ThemeMode get mode => _mode;

  /// Lit la préférence persistée (best-effort : une erreur ou une absence de
  /// valeur ne bloque jamais le démarrage de l'app, on reste sur [initialMode]).
  Future<void> initialize() async {
    try {
      final stored = await _store.read().timeout(const Duration(seconds: 2));
      final resolved = _decode(stored);
      if (resolved != null) {
        _mode = resolved;
        notifyListeners();
      }
    } catch (_) {
      // Repli silencieux sur le mode initial : jamais de plantage au démarrage.
    }
  }

  Future<void> setMode(ThemeMode mode) async {
    if (_mode == mode) return;
    _mode = mode;
    notifyListeners();
    try {
      await _store.write(_encode(mode)).timeout(const Duration(seconds: 2));
    } catch (_) {
      // La persistance est un confort, pas une exigence de correction fonctionnelle.
    }
  }

  ThemeMode? _decode(String? raw) => switch (raw) {
        'light' => ThemeMode.light,
        'dark' => ThemeMode.dark,
        'system' => ThemeMode.system,
        _ => null,
      };

  String _encode(ThemeMode mode) => switch (mode) {
        ThemeMode.light => 'light',
        ThemeMode.dark => 'dark',
        ThemeMode.system => 'system',
      };
}
