import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract interface class TokenStore {
  Future<String?> readAccessToken();
  Future<String?> readRefreshToken();
  Future<void> writeTokens(String accessToken, String refreshToken);
  Future<void> clear();
}

/// Persistance de la langue choisie, m\u00eame abstraction que [TokenStore] :
/// permet d'injecter un double en test au lieu de passer par le vrai canal de
/// plateforme de flutter_secure_storage (voir [SecureLocalePreferenceStore]).
abstract interface class LocalePreferenceStore {
  Future<String?> read();
  Future<void> write(String code);
}

class SecureLocalePreferenceStore implements LocalePreferenceStore {
  const SecureLocalePreferenceStore();

  static const _storage = FlutterSecureStorage();
  static const _localeKey = 'avenqo_locale';

  @override
  Future<String?> read() => _storage.read(key: _localeKey);

  @override
  Future<void> write(String code) => _storage.write(key: _localeKey, value: code);
}

/// Persistance du thème choisi (clair/sombre/système), même abstraction que
/// [LocalePreferenceStore] — permet d'injecter un double en test.
abstract interface class ThemePreferenceStore {
  Future<String?> read();
  Future<void> write(String mode);
}

class SecureThemePreferenceStore implements ThemePreferenceStore {
  const SecureThemePreferenceStore();

  static const _storage = FlutterSecureStorage();
  static const _themeKey = 'avenqo_theme_mode';

  @override
  Future<String?> read() => _storage.read(key: _themeKey);

  @override
  Future<void> write(String mode) => _storage.write(key: _themeKey, value: mode);
}

class SecureTokenStore implements TokenStore {
  const SecureTokenStore();

  static const _storage = FlutterSecureStorage();
  static const _accessKey = 'avenqo_access_token';
  static const _refreshKey = 'avenqo_refresh_token';

  @override
  Future<String?> readAccessToken() => _storage.read(key: _accessKey);

  @override
  Future<String?> readRefreshToken() => _storage.read(key: _refreshKey);

  @override
  Future<void> writeTokens(String accessToken, String refreshToken) async {
    await _storage.write(key: _accessKey, value: accessToken);
    await _storage.write(key: _refreshKey, value: refreshToken);
  }

  @override
  Future<void> clear() async {
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
  }
}
