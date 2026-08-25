import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/token_store.dart';
import 'package:avenqo/i18n/locale_controller.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/pages/connections_page.dart';
import 'package:avenqo/pages/onboarding_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class _TestTokenStore implements TokenStore {
  @override
  Future<void> clear() async {}
  @override
  Future<String?> readAccessToken() async => null;
  @override
  Future<String?> readRefreshToken() async => null;
  @override
  Future<void> writeTokens(String accessToken, String refreshToken) async {}
}

class _MemoryLocalePreferenceStore implements LocalePreferenceStore {
  @override
  Future<String?> read() async => null;
  @override
  Future<void> write(String code) async {}
}

ApiClient _api(http.Client client) => ApiClient(
      tokenStore: _TestTokenStore(),
      httpClient: client,
      baseUrl: 'https://avenqo.test/api/v1',
    );

Future<Widget> _wrapWithLocale(Widget child) async {
  final locale = LocaleController(store: _MemoryLocalePreferenceStore());
  await locale.initialize();
  await locale.setLocale('fr');
  return AvenqoLocaleScope(
    controller: locale,
    child: MaterialApp(home: child),
  );
}

void main() {
  testWidgets('Connections shows the no-data state with an import CTA', (tester) async {
    final client = MockClient((request) async => http.Response('[]', 200));
    await tester.pumpWidget(await _wrapWithLocale(ConnectionsPage(api: _api(client))));
    await tester.pumpAndSettle();

    expect(
      find.text("Connectez vos données pour activer les analyses et l'IA Avenqo."),
      findsOneWidget,
    );
    expect(find.text('Importer un fichier'), findsOneWidget);
  });

  testWidgets('Connections shows the ready state with dataset metadata', (tester) async {
    final client = MockClient((request) async {
      return http.Response(
        '[{"id":"11111111-1111-1111-1111-111111111111","name":"sales.csv","status":"ready","rows_count":42,"columns_count":5,"uploaded_at":"2026-08-20T10:00:00Z"}]',
        200,
      );
    });
    await tester.pumpWidget(await _wrapWithLocale(ConnectionsPage(api: _api(client))));
    await tester.pumpAndSettle();

    expect(find.text('Données prêtes'), findsOneWidget);
    expect(find.text('sales.csv'), findsOneWidget);
    expect(find.text('42'), findsOneWidget);
    expect(find.text('Aller au tableau de bord'), findsOneWidget);
  });

  testWidgets('Connections shows the processing state while a dataset is parsing', (tester) async {
    final client = MockClient((request) async {
      return http.Response(
        '[{"id":"22222222-2222-2222-2222-222222222222","name":"sales.csv","status":"parsing"}]',
        200,
      );
    });
    await tester.pumpWidget(await _wrapWithLocale(ConnectionsPage(api: _api(client))));
    await tester.pump();
    await tester.pump();

    expect(find.text('Analyse de la structure de vos données…'), findsOneWidget);
  });

  testWidgets('Connections shows a safe error state and allows retry', (tester) async {
    final client = MockClient((request) async {
      return http.Response('{"detail":"Erreur serveur interne"}', 500);
    });
    await tester.pumpWidget(await _wrapWithLocale(ConnectionsPage(api: _api(client))));
    await tester.pumpAndSettle();

    expect(find.byIcon(Icons.error_outline), findsOneWidget);
    expect(find.text('Réessayer'), findsOneWidget);
  });

  testWidgets('Onboarding "Charger mes données" persists answers then opens Connections', (tester) async {
    final client = MockClient((request) async {
      if (request.url.path.endsWith('/onboarding/complete')) {
        return http.Response('{"status":"completed","business_goals":["increase_sales"],"current_tools":[],"team_size":"solo","refined_industry":null,"completed_at":"2026-08-24T00:00:00Z","activated_modules":[],"unavailable_modules":[]}', 200);
      }
      if (request.url.path.endsWith('/auth/me')) {
        return http.Response('{"user":{},"company":{"onboarding_status":"completed"}}', 200);
      }
      return http.Response('{}', 404);
    });
    final auth = AuthController(_api(client));
    final locale = LocaleController(store: _MemoryLocalePreferenceStore());
    await locale.initialize();
    await locale.setLocale('fr');

    final router = GoRouter(
      initialLocation: '/',
      routes: [
        GoRoute(path: '/', builder: (context, state) => OnboardingPage(auth: auth)),
        GoRoute(path: '/connections', builder: (context, state) => const Text('Connections Reached')),
      ],
    );
    await tester.pumpWidget(
      AvenqoLocaleScope(
        controller: locale,
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Augmenter les ventes').hitTestable());
    await tester.pump();
    await tester.ensureVisible(find.text('Juste moi'));
    await tester.tap(find.text('Juste moi'));
    await tester.pump();

    await tester.tap(find.text('Charger mes données'));
    await tester.pumpAndSettle();

    expect(find.text('Connections Reached'), findsOneWidget);
  });
}
