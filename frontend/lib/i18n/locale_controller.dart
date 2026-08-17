import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show rootBundle;

import 'package:avenqo/i18n/locale_info.dart';
import 'package:avenqo/i18n/translations.dart';

/// Source de vérité unique de la langue courante et de ses traductions.
///
/// Charge assets/i18n/{code}.json à la demande et les met en cache ; les widgets
/// se reconstruisent via [AvenqoLocaleScope] (InheritedNotifier), jamais par
/// prop-drilling manuel à travers toute la page.
class LocaleController extends ChangeNotifier {
  LocaleController({String initialCode = defaultLocaleCode}) : _code = initialCode;

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
    await setLocale(_code);
  }

  Future<void> _loadCatalog() async {
    final raw = await rootBundle.loadString('assets/i18n/_locales.json');
    final decoded = jsonDecode(raw) as List<dynamic>;
    _availableLocales = decoded
        .map((e) => LocaleInfo.fromJson(e as Map<String, dynamic>))
        .toList(growable: false);
  }

  Future<void> setLocale(String code) async {
    _loading = true;
    notifyListeners();
    try {
      _translations = await _load(code);
      _code = code;
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
      final raw = await rootBundle.loadString('assets/i18n/$code.json');
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
