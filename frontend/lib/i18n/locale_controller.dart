import 'dart:convert';
import 'dart:ui' show Locale;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show rootBundle;

import 'package:avenqo/core/token_store.dart';
import 'package:avenqo/i18n/locale_info.dart';
import 'package:avenqo/i18n/translations.dart';

/// Source de vérité unique de la langue courante et de ses traductions.
///
/// Charge assets/i18n/{code}.json à la demande et les met en cache ; les widgets
/// se reconstruisent via [AvenqoLocaleScope] (InheritedNotifier), jamais par
/// prop-drilling manuel à travers toute la page.
class LocaleController extends ChangeNotifier {
  LocaleController({
    String initialCode = defaultLocaleCode,
    LocalePreferenceStore? store,
    this._platformLocale,
  })
      : _code = initialCode,
        _store = store ?? const SecureLocalePreferenceStore();

  final LocalePreferenceStore _store;
  final Locale? _platformLocale;
  String _code;
  List<LocaleInfo> _availableLocales = const [];
  Translations? _translations;
  bool _loading = false;

  final Map<String, Translations> _cache = {};

  String get code => _code;
  List<LocaleInfo> get availableLocales => _availableLocales;
  Translations? get translations => _translations;
  bool get isLoading => _loading;

  Future<void> initialize() async {
    await _loadCatalog();
    final startCode = await _resolveInitialLocale();
    await setLocale(startCode);
  }

  /// Ordre de résolution : préférence persistée > langue détectée du
  /// navigateur (si supportée) > locale par défaut de l'app. La lecture du
  /// stockage est "best effort" (timeout court + catch) : une erreur ne doit
  /// jamais bloquer ou planter le démarrage de l'app.
  Future<String> _resolveInitialLocale() async {
    final persisted = await _readPersistedLocale();
    final persistedMatch = _matchAvailableLocale(persisted);
    if (persistedMatch != null) {
      return persistedMatch;
    }
    final browserLocale = _platformLocale ?? PlatformDispatcher.instance.locale;
    return _matchAvailableLocale(browserLocale.toLanguageTag()) ??
        defaultLocaleCode;
  }

  String? _matchAvailableLocale(String? rawCode) {
    if (rawCode == null || rawCode.trim().isEmpty) {
      return null;
    }
    final normalized = rawCode.trim().replaceAll('_', '-');
    final lower = normalized.toLowerCase();
    final alias = switch (lower) {
      'fr' => 'fr-CA',
      'en' => 'en-US',
      'es' => 'es-LatAm',
      'pt' => 'pt-PT',
      'es-419' || 'es-latam' => 'es-LatAm',
      _ => normalized,
    };
    for (final locale in _availableLocales) {
      if (locale.code.toLowerCase() == alias.toLowerCase()) {
        return locale.code;
      }
    }

    final parts = normalized.split('-');
    final language = parts.first.toLowerCase();
    final region = parts.length > 1 ? parts.last.toUpperCase() : null;
    if (language == 'es' && region != null && _latinAmericanSpanishRegions.contains(region)) {
      final latAm = _availableLocale('es-LatAm');
      if (latAm != null) {
        return latAm;
      }
    }
    return _availableLocale(language) ?? switch (language) {
      'fr' => _availableLocale('fr-CA'),
      'en' => _availableLocale('en-US'),
      'es' => _availableLocale('es-LatAm'),
      'pt' => _availableLocale('pt-PT'),
      _ => null,
    };
  }

  String? _availableLocale(String code) {
    for (final locale in _availableLocales) {
      if (locale.code.toLowerCase() == code.toLowerCase()) {
        return locale.code;
      }
    }
    return null;
  }

  Future<String?> _readPersistedLocale() async {
    try {
      return await _store.read().timeout(const Duration(seconds: 2));
    } catch (_) {
      return null;
    }
  }

  Future<void> _persistLocale(String code) async {
    try {
      await _store.write(code).timeout(const Duration(seconds: 2));
    } catch (_) {
      // Persistance best-effort : une erreur de stockage ne doit pas casser le changement de langue.
    }
  }

  Future<void> _loadCatalog() async {
    try {
      final raw = await rootBundle
          .loadString('assets/i18n/_locales.json')
          .timeout(const Duration(seconds: 5));
      final decoded = jsonDecode(raw) as List<dynamic>;
      _availableLocales = decoded
          .map((e) => LocaleInfo.fromJson(e as Map<String, dynamic>))
          .toList(growable: false);
    } catch (_) {
      // Best-effort : si le catalogue ne charge pas (asset manquant, bundle
      // bloqué), on continue avec une liste vide plutôt que de bloquer
      // indéfiniment le démarrage de l'app.
      _availableLocales = const [];
    }
  }

  Future<void> setLocale(String code) async {
    final resolvedCode = _matchAvailableLocale(code) ?? defaultLocaleCode;
    _loading = true;
    notifyListeners();
    try {
      _translations = await _load(resolvedCode);
      _code = resolvedCode;
      await _persistLocale(resolvedCode);
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<Translations> _load(String code) async {
    final cached = _cache[code];
    if (cached != null) {
      return cached;
    }
    try {
      final raw = await rootBundle
          .loadString('assets/i18n/$code.json')
          .timeout(const Duration(seconds: 5));
      final decoded = jsonDecode(raw) as Map<String, dynamic>;
      final translations = Translations.fromJson(decoded);
      _cache[code] = translations;
      return translations;
    } catch (_) {
      if (code == defaultLocaleCode) {
        rethrow;
      }
      return _load(defaultLocaleCode);
    }
  }

  LocaleInfo? get currentLocaleInfo {
    for (final locale in _availableLocales) {
      if (locale.code == _code) {
        return locale;
      }
    }
    return null;
  }
}

const _latinAmericanSpanishRegions = <String>{
  '419',
  'AR',
  'BO',
  'CL',
  'CO',
  'CR',
  'CU',
  'DO',
  'EC',
  'GT',
  'HN',
  'MX',
  'NI',
  'PA',
  'PE',
  'PR',
  'PY',
  'SV',
  'UY',
  'VE',
};
