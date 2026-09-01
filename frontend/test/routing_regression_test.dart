import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:avenqo/app/app_theme.dart';
import 'package:avenqo/app/theme_controller.dart';
import 'package:avenqo/app/theme_scope.dart';
import 'package:avenqo/agents/agent_registry.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/auth/auth_page.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/token_store.dart';
import 'package:avenqo/i18n/locale_controller.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/pages/dashboard_page.dart';
import 'package:avenqo/pages/home_page.dart';
import 'package:avenqo/pages/pricing_page.dart';
import 'package:avenqo/widgets/admin_shell.dart';
import 'package:avenqo/widgets/app_shell.dart';
import 'package:avenqo/widgets/language_selector.dart';
import 'package:avenqo/widgets/theme_toggle_button.dart';

/// Tests de régression pour le routing Flutter Web en production.
/// Garantit que les URLs directes comme /login, /register, /dashboard, /admin
/// affichent les bonnes pages et non la landing page.

class _MemoryLocalePreferenceStore implements LocalePreferenceStore {
  String? _code;
  @override
  Future<String?> read() async => _code;
  @override
  Future<void> write(String code) async => _code = code;
}

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

class _MemoryThemePreferenceStore implements ThemePreferenceStore {
  String? mode;

  @override
  Future<String?> read() async => mode;

  @override
  Future<void> write(String mode) async => this.mode = mode;
}

final ThemeController _sharedTestTheme = ThemeController(
  store: _MemoryThemePreferenceStore(),
);
final LocaleController _sharedTestLocale = LocaleController(
  store: _MemoryLocalePreferenceStore(),
);

void _expectOfficialAuthBrand({required double size}) {
  final logo = find.byKey(const ValueKey('official-avenqo-logo'));
  expect(logo, findsOneWidget);
  final image = logo.evaluate().single.widget as Image;
  expect(
    (image.image as AssetImage).assetName,
    'assets/brand/avenqo-official.png',
  );
  expect(image.width, size);
  expect(image.height, size);
  expect(find.byIcon(Icons.change_history), findsNothing);
  expect(find.text('Avenqo'), findsOneWidget);
}

Widget _wrapWithProviders(Widget child) {
  return AvenqoThemeScope(
    controller: _sharedTestTheme,
    child: AvenqoLocaleScope(controller: _sharedTestLocale, child: child),
  );
}

Future<void> _pumpApp(
  WidgetTester tester, {
  required String initialRoute,
  required AuthController auth,
}) async {
  await tester.pumpWidget(
    _wrapWithProviders(
      ListenableBuilder(
        listenable: _sharedTestTheme,
        builder: (context, _) => MaterialApp.router(
          routerConfig: GoRouter(
            initialLocation: initialRoute,
            redirect: (context, state) {
              // Reproduit la logique du redirect réel
              if (!auth.initialized) {
                return null;
              }
              final path = state.uri.path;
              final publicPaths = {
                '/',
                '/pricing',
                '/login',
                '/register',
                '/forgot-password',
                '/verify-email',
                '/reset-password',
              };
              final isPublic = publicPaths.contains(path);
              final isAdminPath =
                  path == '/admin' || path.startsWith('/admin/');
              if (!auth.isAuthenticated && !isPublic) {
                return '/login';
              }
              if (isAdminPath && !auth.isPlatformAdmin) {
                return '/dashboard';
              }
              if (auth.isAuthenticated && path == '/login') {
                return auth.isPlatformAdmin ? '/admin' : '/dashboard';
              }
              return null;
            },
            routes: [
              GoRoute(
                path: '/',
                builder: (context, state) => HomePage(
                  initialSection: state.uri.queryParameters['section'],
                ),
              ),
              GoRoute(
                path: '/pricing',
                builder: (context, state) => PricingPage(api: auth.api),
              ),
              GoRoute(
                path: '/login',
                builder: (context, state) =>
                    AuthPage(auth: auth, mode: AuthMode.login),
              ),
              GoRoute(
                path: '/register',
                builder: (context, state) =>
                    AuthPage(auth: auth, mode: AuthMode.register),
              ),
              GoRoute(
                path: '/dashboard',
                builder: (context, state) => DashboardPage(auth: auth),
              ),
            ],
          ),
          theme: AppTheme.light,
          darkTheme: AppTheme.dark,
          themeMode: _sharedTestTheme.mode,
          themeAnimationDuration: Duration.zero,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle(const Duration(seconds: 1));
}

void main() {
  group('Routing Regression Tests — Flutter Web SPA', () {
    late AuthController unauthenticatedAuth;
    late AuthController authenticatedAuth;

    setUpAll(() async {
      await _sharedTestLocale.initialize();

      // Unauthenticated auth (no token)
      unauthenticatedAuth = AuthController(
        ApiClient(
          tokenStore: _MemoryTokenStore(),
          httpClient: MockClient((request) async {
            return http.Response('{"user": null}', 401);
          }),
          baseUrl: 'https://avenqo.test/api/v1',
        ),
      );
      await unauthenticatedAuth.initialize();

      // Authenticated auth (has token)
      final authenticatedClient = MockClient((request) async {
        return http.Response(
          '{"access_token":"a","refresh_token":"r",'
          '"user":{"id":"1","company_id":"2","first_name":"Test","last_name":"User",'
          '"email":"user@example.com","role":"owner","permissions":[],"is_active":true,'
          '"is_platform_admin":false,"email_verified_at":null},'
          '"company":{"id":"2","name":"Test Company"}}',
          200,
        );
      });
      authenticatedAuth = AuthController(
        ApiClient(
          tokenStore: _MemoryTokenStore(),
          httpClient: authenticatedClient,
          baseUrl: 'https://avenqo.test/api/v1',
        ),
      );
      await authenticatedAuth.initialize();
      // Simulate login
      await authenticatedAuth.login('user@example.com', 'password');
    });

    testWidgets('Direct URL /login affiche AuthPage (pas HomePage)', (
      WidgetTester tester,
    ) async {
      await _pumpApp(tester, initialRoute: '/login', auth: unauthenticatedAuth);

      expect(find.byType(AuthPage), findsOneWidget);
      expect(find.byType(HomePage), findsNothing);
    });

    testWidgets('pricing reste complet et localisé sans réponse API', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(1440, 1200);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await _pumpApp(
        tester,
        initialRoute: '/pricing',
        auth: unauthenticatedAuth,
      );

      final pricing = AvenqoLocaleScope.translationsOf(
        tester.element(find.byType(PricingPage)),
      ).pricing;
      expect(find.text(pricing.title), findsOneWidget);
      for (final plan in pricing.plans) {
        expect(find.text(plan.title), findsOneWidget);
        expect(find.text(plan.action), findsWidgets);
      }
      expect(find.byType(ThemeToggleButton), findsOneWidget);
      expect(find.byType(LanguageSelector), findsOneWidget);
      expect(find.text('Plans Avenqo'), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('pricing mobile ne déborde pas', (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await _pumpApp(
        tester,
        initialRoute: '/pricing',
        auth: unauthenticatedAuth,
      );

      final translations = AvenqoLocaleScope.translationsOf(
        tester.element(find.byType(PricingPage)),
      );
      expect(find.byType(PricingPage), findsOneWidget);
      expect(find.text(translations.nav.features), findsOneWidget);
      expect(find.text(translations.nav.modules), findsOneWidget);
      expect(find.text(translations.nav.pricing), findsOneWidget);
      expect(find.byType(ThemeToggleButton), findsOneWidget);
      expect(find.byType(LanguageSelector), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('login desktop has one auth header and no app shell', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(1440, 1000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await _sharedTestTheme.setMode(ThemeMode.light);

      await _pumpApp(tester, initialRoute: '/login', auth: unauthenticatedAuth);

      expect(find.byType(ThemeToggleButton), findsOneWidget);
      expect(find.byType(LanguageSelector), findsOneWidget);
      _expectOfficialAuthBrand(size: 42);
      expect(find.byType(AppShell), findsNothing);
      expect(find.byType(AdminShell), findsNothing);
      expect(
        Theme.of(tester.element(find.byType(AuthPage))).brightness,
        Brightness.light,
      );
      expect(tester.takeException(), isNull);
    });

    testWidgets('login mobile keeps one header and supports dark mode', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(() => _sharedTestTheme.setMode(ThemeMode.light));
      await _sharedTestTheme.setMode(ThemeMode.dark);

      await _pumpApp(tester, initialRoute: '/login', auth: unauthenticatedAuth);

      expect(find.byType(ThemeToggleButton), findsOneWidget);
      expect(find.byType(LanguageSelector), findsOneWidget);
      _expectOfficialAuthBrand(size: 36);
      expect(find.byType(AppShell), findsNothing);
      expect(find.byType(AdminShell), findsNothing);
      expect(
        Theme.of(tester.element(find.byType(AuthPage))).brightness,
        Brightness.dark,
      );
      expect(tester.takeException(), isNull);
    });

    testWidgets('Direct URL /register affiche AuthPage (pas HomePage)', (
      WidgetTester tester,
    ) async {
      await _pumpApp(
        tester,
        initialRoute: '/register',
        auth: unauthenticatedAuth,
      );

      expect(find.byType(AuthPage), findsOneWidget);
      expect(find.byType(HomePage), findsNothing);
      _expectOfficialAuthBrand(size: 42);
    });

    testWidgets('registration shows all modules and caps Demo at two', (
      WidgetTester tester,
    ) async {
      tester.view.physicalSize = const Size(1200, 1000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await _pumpApp(
        tester,
        initialRoute: '/register',
        auth: unauthenticatedAuth,
      );

      final fields = find.byType(TextFormField);
      await tester.enterText(fields.at(0), 'Avenqo Test');
      await tester.enterText(fields.at(2), '11-50');
      await tester.enterText(fields.at(5), 'billing@avenqo.test');
      final continueButton = find.byType(FilledButton);
      await tester.ensureVisible(continueButton);
      await tester.tap(continueButton);
      await tester.pumpAndSettle();
      await tester.tap(continueButton);
      await tester.pumpAndSettle();

      for (final module in avenqoAgentRegistry) {
        expect(
          find.byKey(ValueKey('signup-module-${module.id}')),
          findsOneWidget,
        );
        final context = tester.element(find.byType(AuthPage));
        final strings = AvenqoLocaleScope.translationsOf(context).agents;
        expect(find.text(strings.value(module.nameKey)), findsOneWidget);
        expect(find.text(strings.value(module.descriptionKey)), findsOneWidget);
      }

      for (final module in avenqoAgentRegistry.take(3)) {
        final card = find.byKey(ValueKey('signup-module-${module.id}'));
        await tester.ensureVisible(card);
        await tester.tap(card);
        await tester.pump();
      }
      expect(find.text('2 / 2'), findsOneWidget);
      expect(find.byIcon(Icons.check_circle), findsNWidgets(2));

      var backButton = find.byType(TextButton).first;
      await tester.ensureVisible(backButton);
      await tester.tap(backButton);
      await tester.pumpAndSettle();
      await tester.tap(find.byType(ListTile).at(1));
      await tester.pump();
      await tester.tap(find.byType(FilledButton));
      await tester.pumpAndSettle();
      for (final module in avenqoAgentRegistry.skip(2).take(7)) {
        final card = find.byKey(ValueKey('signup-module-${module.id}'));
        await tester.ensureVisible(card);
        await tester.tap(card);
        await tester.pump();
      }
      expect(find.text('8 / 8'), findsOneWidget);
      expect(find.byIcon(Icons.check_circle), findsNWidgets(8));

      backButton = find.byType(TextButton).first;
      await tester.ensureVisible(backButton);
      await tester.tap(backButton);
      await tester.pumpAndSettle();
      await tester.tap(find.byType(ListTile).at(2));
      await tester.pump();
      await tester.tap(find.byType(FilledButton));
      await tester.pumpAndSettle();
      for (final module in avenqoAgentRegistry.skip(8)) {
        final card = find.byKey(ValueKey('signup-module-${module.id}'));
        await tester.ensureVisible(card);
        await tester.tap(card);
        await tester.pump();
      }
      expect(find.text('11 / 11'), findsOneWidget);
      expect(find.byIcon(Icons.check_circle), findsNWidgets(11));
      expect(tester.takeException(), isNull);
    });

    testWidgets('Direct URL /dashboard sans session redirige vers /login', (
      WidgetTester tester,
    ) async {
      await _pumpApp(
        tester,
        initialRoute: '/dashboard',
        auth: unauthenticatedAuth,
      );

      // GoRouter redirect doit envoyer vers /login
      expect(find.byType(AuthPage), findsOneWidget);
      expect(find.byType(DashboardPage), findsNothing);
    });

    testWidgets('Landing page / affiche HomePage', (WidgetTester tester) async {
      await _pumpApp(tester, initialRoute: '/', auth: unauthenticatedAuth);

      expect(find.byType(HomePage), findsOneWidget);
      expect(find.byType(AuthPage), findsNothing);
    });

    testWidgets('Utilisateur authentifié sur /login redirige vers /dashboard', (
      WidgetTester tester,
    ) async {
      await _pumpApp(tester, initialRoute: '/login', auth: authenticatedAuth);

      // Redirect doit envoyer vers /dashboard
      expect(find.byType(DashboardPage), findsOneWidget);
      expect(find.byType(AuthPage), findsNothing);
    });
  });
}
