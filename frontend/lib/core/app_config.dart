import 'package:flutter/foundation.dart';

class AppConfig {
  const AppConfig._();
  static const publicContactEmail = 'info@avenqo.ca';

  static String get apiBaseUrl {
    const envUrl = String.fromEnvironment('API_BASE_URL');
    if (envUrl.isNotEmpty) return envUrl;
    if (kIsWeb) return '/api/v1';
    return 'http://127.0.0.1:8000/api/v1';
  }
}
