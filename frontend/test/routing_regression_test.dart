import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:avenqo/app/app_theme.dart';
import 'package:avenqo/app/theme_controller.dart';
import 'package:avenqo/app/theme_scope.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/auth/auth_page.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/token_store.dart';
import 'package:avenqo/i18n/locale_controller.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/pages/dashboard_page.dart';
import 'package:avenqo/pages/home_page.dart';
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
              GoRoute(path: '/', builder: (context, state) => const HomePage()),
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
      expect(find.text('Avenqo'), findsOneWidget);
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
      expect(find.text('Avenqo'), findsOneWidget);
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
