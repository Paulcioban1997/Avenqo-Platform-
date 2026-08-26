import 'package:flutter/material.dart';
import 'package:flutter_web_plugins/url_strategy.dart';
import 'package:avenqo/app/avenqo_app.dart';
import 'package:avenqo/app/theme_controller.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/token_store.dart';
import 'package:avenqo/i18n/locale_controller.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  usePathUrlStrategy();
  final api = ApiClient(tokenStore: const SecureTokenStore());
  final auth = AuthController(api);
  final locale = LocaleController();
  final theme = ThemeController();
  await Future.wait([auth.initialize(), locale.initialize(), theme.initialize()]);
  runApp(AvenqoApp(auth: auth, locale: locale, theme: theme));
}
