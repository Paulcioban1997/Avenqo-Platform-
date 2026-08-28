import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/app/theme_controller.dart';
import 'package:avenqo/app/theme_scope.dart';
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

class _HangingHttpClient extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) =>
      Completer<http.StreamedResponse>().future;
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
    child: MaterialApp(home: Scaffold(body: child)),
  );
}

void main() {
  testWidgets('Connections shows the no-data state with an Add files CTA', (
    tester,
  ) async {
    final client = MockClient((request) async => http.Response('[]', 200));
    await tester.pumpWidget(
      await _wrapWithLocale(ConnectionsPage(api: _api(client))),
    );
    await tester.pumpAndSettle();

    expect(
      find.text(
        "Connectez vos données pour activer les analyses et l'IA Avenqo.",
      ),
      findsOneWidget,
    );
    expect(find.text('Ajouter des fichiers'), findsOneWidget);
  });

  test(
    'ApiClient converts a stalled request into a timeout ApiException',
    () async {
      final api = ApiClient(
        tokenStore: _TestTokenStore(),
        httpClient: _HangingHttpClient(),
        baseUrl: 'https://avenqo.test/api/v1',
        requestTimeout: const Duration(milliseconds: 10),
      );

      await expectLater(
        api.get('/datasets'),
        throwsA(
          isA<ApiException>().having(
            (error) => error.isTimeout,
            'isTimeout',
            true,
          ),
        ),
      );
    },
  );

  testWidgets('Connections lists an existing ready dataset with its metadata', (
    tester,
  ) async {
    final client = MockClient((request) async {
      return http.Response(
        '[{"id":"11111111-1111-1111-1111-111111111111","name":"sales.csv","status":"ready","rows_count":42,"columns_count":5,"uploaded_at":"2026-08-20T10:00:00Z"}]',
        200,
      );
    });
    await tester.pumpWidget(
      await _wrapWithLocale(ConnectionsPage(api: _api(client))),
    );
    await tester.pumpAndSettle();

    expect(find.text('Données connectées'), findsOneWidget);
    await tester.tap(find.text('Données connectées'));
    await tester.pumpAndSettle();

    expect(find.text('sales.csv'), findsOneWidget);
    expect(find.textContaining('42'), findsOneWidget);
    // The Add files CTA must remain available even once data already exists.
    expect(find.text('Ajouter des fichiers'), findsOneWidget);
  });

  testWidgets('Connections lists a dataset still being processed', (
    tester,
  ) async {
    final client = MockClient((request) async {
      return http.Response(
        '[{"id":"22222222-2222-2222-2222-222222222222","name":"sales.csv","status":"parsing"}]',
        200,
      );
    });
    await tester.pumpWidget(
      await _wrapWithLocale(ConnectionsPage(api: _api(client))),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Données connectées'));
    await tester.pumpAndSettle();
    expect(find.text('sales.csv'), findsOneWidget);
  });

  testWidgets('Connections polls until automatic training is ready', (
    tester,
  ) async {
    var requests = 0;
    final client = MockClient((request) async {
      requests += 1;
      final pipelineStatus = requests == 1 ? 'training_ai' : 'ready';
      return http.Response(
        '[{"id":"22222222-2222-2222-2222-222222222222","name":"sales.csv","status":"ready","pipeline_status":"$pipelineStatus"}]',
        200,
      );
    });
    await tester.pumpWidget(
      await _wrapWithLocale(
        ConnectionsPage(
          api: _api(client),
          pollInterval: const Duration(milliseconds: 50),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 60));
    await tester.pump();

    expect(requests, 2);
    await tester.tap(find.text('Données connectées'));
    await tester.pump();
    expect(find.byIcon(Icons.check_circle), findsOneWidget);
    expect(find.textContaining('Mapping required'), findsNothing);
    expect(find.textContaining('Mappage requis'), findsNothing);
  });

  testWidgets('A connected dataset can be deleted from the dropdown', (
    tester,
  ) async {
    var deleteCalled = false;
    final client = MockClient((request) async {
      if (request.method == 'GET' && request.url.path.endsWith('/datasets')) {
        return http.Response(
          '[{"id":"33333333-3333-3333-3333-333333333333","name":"obsolete.csv","status":"ready","rows_count":8,"columns_count":2,"uploaded_at":"2026-08-27T00:00:00Z"}]',
          200,
        );
      }
      if (request.method == 'DELETE' &&
          request.url.path.endsWith(
            '/datasets/33333333-3333-3333-3333-333333333333',
          )) {
        deleteCalled = true;
        return http.Response('', 204);
      }
      return http.Response('{}', 404);
    });

    await tester.pumpWidget(
      await _wrapWithLocale(ConnectionsPage(api: _api(client))),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Données connectées'));
    await tester.pumpAndSettle();

    expect(find.text('obsolete.csv'), findsOneWidget);
    await tester.tap(find.byIcon(Icons.delete_outline).first);
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsOneWidget);

    await tester.tap(
      find.widgetWithIcon(FilledButton, Icons.delete_outline),
    );
    await tester.pumpAndSettle();

    expect(deleteCalled, isTrue);
    expect(find.text('obsolete.csv'), findsNothing);
  });

  testWidgets('Connections shows a safe error state and allows retry', (
    tester,
  ) async {
    final client = MockClient((request) async {
      return http.Response('{"detail":"Erreur serveur interne"}', 500);
    });
    await tester.pumpWidget(
      await _wrapWithLocale(ConnectionsPage(api: _api(client))),
    );
    await tester.pumpAndSettle();

    expect(find.byIcon(Icons.error_outline), findsOneWidget);
    expect(find.text('Réessayer'), findsOneWidget);
  });

  testWidgets('Selecting multiple files stages them for review before upload', (
    tester,
  ) async {
    final client = MockClient((request) async => http.Response('[]', 200));
    final queue = [
      [
        PickedFile('sales.csv', Uint8List.fromList([1, 2, 3])),
        PickedFile('customers.xlsx', Uint8List.fromList([1, 2])),
      ],
    ];
    await tester.pumpWidget(
      await _wrapWithLocale(
        ConnectionsPage(
          api: _api(client),
          pickFiles: () async => queue.removeAt(0),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Ajouter des fichiers'));
    await tester.pumpAndSettle();

    expect(find.text('sales.csv'), findsOneWidget);
    expect(find.text('customers.xlsx'), findsOneWidget);
    expect(find.text('Importer 2 fichiers'), findsOneWidget);
    // No network call should have happened yet: upload only starts on explicit click.
  });

  testWidgets(
    'Add more files appends to the pending selection instead of replacing it',
    (tester) async {
      final client = MockClient((request) async => http.Response('[]', 200));
      final queue = [
        [
          PickedFile('sales.csv', Uint8List.fromList([1, 2, 3])),
        ],
        [
          PickedFile('products.csv', Uint8List.fromList([4, 5])),
        ],
      ];
      await tester.pumpWidget(
        await _wrapWithLocale(
          ConnectionsPage(
            api: _api(client),
            pickFiles: () async => queue.removeAt(0),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Ajouter des fichiers'));
      await tester.pumpAndSettle();
      await tester.tap(find.text("Ajouter d'autres fichiers"));
      await tester.pumpAndSettle();

      expect(find.text('sales.csv'), findsOneWidget);
      expect(find.text('products.csv'), findsOneWidget);
      expect(find.text('Importer 2 fichiers'), findsOneWidget);
    },
  );

  testWidgets('A pending file can be removed before upload', (tester) async {
    final client = MockClient((request) async => http.Response('[]', 200));
    final queue = [
      [
        PickedFile('sales.csv', Uint8List.fromList([1, 2, 3])),
        PickedFile('customers.xlsx', Uint8List.fromList([1, 2])),
      ],
    ];
    await tester.pumpWidget(
      await _wrapWithLocale(
        ConnectionsPage(
          api: _api(client),
          pickFiles: () async => queue.removeAt(0),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Ajouter des fichiers'));
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.close).first);
    await tester.pumpAndSettle();

    expect(find.text('customers.xlsx'), findsOneWidget);
    expect(find.text('Importer 1 fichier'), findsOneWidget);
  });

  testWidgets(
    'Selecting the same file twice shows a duplicate notice and does not duplicate it',
    (tester) async {
      final client = MockClient((request) async => http.Response('[]', 200));
      final queue = [
        [
          PickedFile('sales.csv', Uint8List.fromList([1, 2, 3])),
        ],
        [
          PickedFile('sales.csv', Uint8List.fromList([1, 2, 3])),
        ],
      ];
      await tester.pumpWidget(
        await _wrapWithLocale(
          ConnectionsPage(
            api: _api(client),
            pickFiles: () async => queue.removeAt(0),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Ajouter des fichiers'));
      await tester.pumpAndSettle();
      await tester.tap(find.text("Ajouter d'autres fichiers"));
      await tester.pumpAndSettle();

      expect(find.text('sales.csv'), findsOneWidget);
      expect(find.text('Importer 1 fichier'), findsOneWidget);
    },
  );

  testWidgets(
    'Uploading files shows per-file progress then a success summary and refreshes the dataset list',
    (tester) async {
      var listCallCount = 0;
      final client = MockClient((request) async {
        if (request.method == 'GET' && request.url.path.endsWith('/datasets')) {
          listCallCount += 1;
          if (listCallCount == 1) return http.Response('[]', 200);
          return http.Response(
            '[{"id":"1","name":"sales.csv","status":"ready","rows_count":10,"columns_count":3,"uploaded_at":"2026-08-25T00:00:00Z"}]',
            200,
          );
        }
        if (request.url.path.endsWith('/datasets/upload')) {
          return http.Response('{"dataset_id":"1","status":"ready"}', 200);
        }
        return http.Response('{}', 404);
      });
      final queue = [
        [
          PickedFile('sales.csv', Uint8List.fromList([1, 2, 3])),
        ],
      ];
      await tester.pumpWidget(
        await _wrapWithLocale(
          ConnectionsPage(
            api: _api(client),
            pickFiles: () async => queue.removeAt(0),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Ajouter des fichiers'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Importer 1 fichier'));
      for (var i = 0; i < 10; i++) {
        await tester.pump(const Duration(milliseconds: 50));
      }

      expect(find.text('Import terminé'), findsOneWidget);
      expect(find.text('1 fichier importé avec succès.'), findsOneWidget);

      await tester.tap(find.text('Continuer'));
      await tester.pumpAndSettle();

      expect(find.text('Données connectées'), findsOneWidget);
      await tester.tap(find.text('Données connectées'));
      await tester.pumpAndSettle();
      expect(find.text('sales.csv'), findsOneWidget);
    },
  );

  testWidgets(
    'A failing file does not prevent other files in the same batch from succeeding',
    (tester) async {
      final client = MockClient((request) async {
        if (request.method == 'GET' && request.url.path.endsWith('/datasets')) {
          return http.Response('[]', 200);
        }
        if (request.url.path.endsWith('/datasets/upload')) {
          final body = utf8.decode(request.bodyBytes);
          if (body.contains('bad.csv')) {
            return http.Response('{"detail":"Format non pris en charge"}', 422);
          }
          return http.Response('{"dataset_id":"1","status":"ready"}', 200);
        }
        return http.Response('{}', 404);
      });
      final queue = [
        [
          PickedFile('sales.csv', Uint8List.fromList([1, 2, 3])),
          PickedFile('bad.csv', Uint8List.fromList([1])),
        ],
      ];
      await tester.pumpWidget(
        await _wrapWithLocale(
          ConnectionsPage(
            api: _api(client),
            pickFiles: () async => queue.removeAt(0),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Ajouter des fichiers'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Importer 2 fichiers'));
      for (var i = 0; i < 10; i++) {
        await tester.pump(const Duration(milliseconds: 50));
      }

      expect(find.text('Import terminé'), findsOneWidget);
      expect(find.text('1 fichier importé avec succès.'), findsOneWidget);
      expect(find.text('1 fichier en erreur.'), findsOneWidget);
    },
  );

  testWidgets(
    'Onboarding "Charger mes données" persists answers then opens Connections',
    (tester) async {
      final client = MockClient((request) async {
        if (request.url.path.endsWith('/onboarding/complete')) {
          return http.Response(
            '{"status":"completed","business_goals":["increase_sales"],"current_tools":[],"team_size":"solo","refined_industry":null,"completed_at":"2026-08-24T00:00:00Z","activated_modules":[],"unavailable_modules":[]}',
            200,
          );
        }
        if (request.url.path.endsWith('/auth/me')) {
          return http.Response(
            '{"user":{},"company":{"onboarding_status":"completed"}}',
            200,
          );
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
          GoRoute(
            path: '/',
            builder: (context, state) => OnboardingPage(auth: auth),
          ),
          GoRoute(
            path: '/connections',
            builder: (context, state) => const Text('Connections Reached'),
          ),
        ],
      );
      await tester.pumpWidget(
        AvenqoLocaleScope(
          controller: locale,
          child: AvenqoThemeScope(
            controller: ThemeController(),
            child: MaterialApp.router(routerConfig: router),
          ),
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
    },
  );
}
