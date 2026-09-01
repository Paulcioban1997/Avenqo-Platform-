import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:avenqo/app/theme_controller.dart';
import 'package:avenqo/app/theme_scope.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/token_store.dart';
import 'package:avenqo/i18n/locale_controller.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/widgets/app_shell.dart';
import 'package:avenqo/widgets/admin_shell.dart';

/// Tests isolés (widgets seuls, sans GoRouter/app complète) pour éviter le
/// blocage constaté en pumpant AvenqoApp en entier avec un vrai routeur.
class _MemoryLocalePreferenceStore implements LocalePreferenceStore {
  String? _code;
  @override
  Future<String?> read() async => _code;
  @override
  Future<void> write(String code) async => _code = code;
}

/// Enveloppe de test partagée : jamais de vrai FlutterSecureStorage dans un
/// widget test (cause un blocage réel, voir mémoire de dépot).
Widget wrapWithLocale(Widget child, {LocaleController? controller}) {
  return AvenqoThemeScope(
    controller: _sharedTestTheme,
    child: AvenqoLocaleScope(controller: controller ?? _sharedTestLocale, child: child),
  );
}

final LocaleController _sharedTestLocale = LocaleController(store: _MemoryLocalePreferenceStore());
final ThemeController _sharedTestTheme = ThemeController();

class _MemoryTokenStore implements TokenStore {
  @override
  Future<void> clear() async {}
  @override
  Future<String?> readAccessToken() async => null;
  @override
  Future<String?> readRefreshToken() async => null;
  @override
  Future<void> writeTokens(String accessToken, String refreshToken) async {}
}

Future<AuthController> _loggedInAuth({required bool isPlatformAdmin}) async {
  final client = MockClient((request) async {
    return http.Response(
      '{"access_token":"a","refresh_token":"r",'
      '"user":{"id":"1","company_id":"2","first_name":"Dana","last_name":"Owner",'
      '"email":"user@example.com","role":"owner","permissions":[],"is_active":true,'
      '"is_platform_admin":$isPlatformAdmin,"email_verified_at":null},'
      '"company":{"id":"2","name":"Acme"}}',
      200,
    );
  });
  final auth = AuthController(ApiClient(
    tokenStore: _MemoryTokenStore(),
    httpClient: client,
    baseUrl: 'https://avenqo.test/api/v1',
  ));
  await auth.initialize();
  await auth.login('user@example.com', 'password');
  return auth;
}

void main() {
  setUpAll(() async {
    await _sharedTestLocale.initialize();
  });

  testWidgets('un client normal ne voit pas l\'entrée Avenqo Admin', (tester) async {
    tester.view.physicalSize = const Size(1400, 1000);
    addTearDown(tester.view.resetPhysicalSize);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetDevicePixelRatio);
    final auth = await _loggedInAuth(isPlatformAdmin: false);
    expect(auth.isPlatformAdmin, isFalse);

    await tester.pumpWidget(MaterialApp(
      home: wrapWithLocale(AppShell(auth: auth, currentPath: '/dashboard', child: const SizedBox())),
    ));
    await tester.pump();

    expect(find.text('Avenqo Admin'), findsNothing);
    expect(find.text('Agents'), findsOneWidget);
  });

  testWidgets('un platform_admin voit l\'entrée Avenqo Admin dans sa navigation', (tester) async {
    tester.view.physicalSize = const Size(1400, 1000);
    addTearDown(tester.view.resetPhysicalSize);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetDevicePixelRatio);
    final auth = await _loggedInAuth(isPlatformAdmin: true);
    expect(auth.isPlatformAdmin, isTrue);

    await tester.pumpWidget(MaterialApp(
      home: wrapWithLocale(AppShell(auth: auth, currentPath: '/dashboard', child: const SizedBox())),
    ));
    await tester.pump();

    await tester.scrollUntilVisible(
      find.text('Avenqo Admin'),
      250,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Avenqo Admin'), findsOneWidget);
  });

  testWidgets('AdminShell affiche une interface clairement distincte (badge PLATFORM)', (tester) async {
    tester.view.physicalSize = const Size(1400, 1000);
    addTearDown(tester.view.resetPhysicalSize);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetDevicePixelRatio);
    final auth = await _loggedInAuth(isPlatformAdmin: true);

    await tester.pumpWidget(MaterialApp(
      home: wrapWithLocale(AdminShell(auth: auth, currentPath: '/admin', child: const SizedBox())),
    ));
    await tester.pump();

    expect(find.text('Avenqo Command Center'), findsOneWidget);
    expect(find.textContaining('PLATFORM'), findsOneWidget);
    expect(find.text('Agents'), findsOneWidget);
  });
}
