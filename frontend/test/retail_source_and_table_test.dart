import 'dart:convert';

import 'package:avenqo/agents/retail_agent_shell.dart';
import 'package:avenqo/agents/retail_source_controller.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/token_store.dart';
import 'package:avenqo/i18n/locale_controller.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/pages/sales_page.dart';
import 'package:avenqo/widgets/avenqo_data_table.dart';
import 'package:data_table_2/data_table_2.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class _Tokens implements TokenStore {
  @override
  Future<void> clear() async {}
  @override
  Future<String?> readAccessToken() async => null;
  @override
  Future<String?> readRefreshToken() async => null;
  @override
  Future<void> writeTokens(String accessToken, String refreshToken) async {}
}

class _LocaleStore implements LocalePreferenceStore {
  @override
  Future<String?> read() async => 'fr';
  @override
  Future<void> write(String code) async {}
}

ApiClient _api(MockClient client) => ApiClient(
  tokenStore: _Tokens(),
  httpClient: client,
  baseUrl: 'https://avenqo.test/api/v1',
);

Future<Widget> _wrap(Widget child) async {
  final locale = LocaleController(store: _LocaleStore());
  await locale.initialize();
  return AvenqoLocaleScope(
    controller: locale,
    child: MaterialApp(
      locale: const Locale('fr'),
      theme: ThemeData(extensions: const [AvenqoColors.light]),
      home: Scaffold(body: child),
    ),
  );
}

Map<String, dynamic> _source({
  required String id,
  required String name,
  required bool active,
  String type = 'connector',
}) => {
  'source_type': type,
  'source_id': id,
  'dataset_id': type == 'connector' ? 'dataset-$id' : id,
  'connection_id': type == 'connector' ? id : null,
  'display_name': name,
  'provider': type == 'connector' ? 'shopify' : null,
  'status': 'READY',
  'last_synchronized_at': '2026-09-08T17:30:00Z',
  'active': active,
};

void main() {
  test(
    'Retail source controller switches and persists the canonical source',
    () async {
      final requests = <http.Request>[];
      final client = MockClient((request) async {
        requests.add(request);
        if (request.method == 'GET') {
          return http.Response(
            jsonEncode([
              _source(
                id: 'shopify',
                name: 'avenqo-retail-test.myshopify.com',
                active: true,
              ),
              _source(
                id: 'dataset',
                name: 'Superstore',
                active: false,
                type: 'dataset',
              ),
            ]),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        expect(request.method, 'PUT');
        expect(jsonDecode(request.body), {
          'source_type': 'dataset',
          'source_id': 'dataset',
        });
        return http.Response(
          jsonEncode(
            _source(
              id: 'dataset',
              name: 'Superstore',
              active: true,
              type: 'dataset',
            ),
          ),
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      final controller = RetailSourceController(_api(client));

      await controller.load();
      expect(
        controller.active?.displayName,
        'avenqo-retail-test.myshopify.com',
      );
      await controller.select(controller.sources.last);

      expect(controller.active?.displayName, 'Superstore');
      expect(requests.map((request) => request.method), ['GET', 'PUT']);
      controller.dispose();
    },
  );

  testWidgets('Retail shell renders active Shopify provenance', (tester) async {
    final client = MockClient(
      (request) async => http.Response(
        jsonEncode([
          _source(
            id: 'shopify',
            name: 'avenqo-retail-test.myshopify.com',
            active: true,
          ),
        ]),
        200,
        headers: {'content-type': 'application/json'},
      ),
    );

    await tester.pumpWidget(
      await _wrap(
        RetailAgentShell(
          api: _api(client),
          currentPath: '/retail',
          child: const SizedBox(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('retail-source-selector')), findsOneWidget);
    expect(
      find.textContaining(RegExp(r'^(Source active|Active source)$')),
      findsOneWidget,
    );
    expect(find.byIcon(Icons.shopping_bag_outlined), findsOneWidget);
  });

  testWidgets(
    'Avenqo table owns visible horizontal scrolling without overflow',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              width: 360,
              child: AvenqoDataTable(
                semanticLabel: 'Wide retail table',
                minWidth: 1200,
                columns: [
                  for (var index = 0; index < 8; index++)
                    DataColumn(label: Text('Column $index')),
                ],
                rows: [
                  DataRow(
                    cells: [
                      for (var index = 0; index < 8; index++)
                        DataCell(Text('Value $index')),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final table = tester.widget<DataTable2>(find.byType(DataTable2));
      expect(table.isHorizontalScrollBarVisible, isTrue);
      expect(table.horizontalScrollController, isNotNull);
      await tester.drag(find.byType(DataTable2), const Offset(-250, 0));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('Active Shopify source shows a truthful sales empty state', (
    tester,
  ) async {
    final client = MockClient(
      (request) async => http.Response(
        jsonEncode([
          _source(
            id: 'shopify',
            name: 'avenqo-retail-test.myshopify.com',
            active: true,
          ),
        ]),
        200,
        headers: {'content-type': 'application/json'},
      ),
    );
    final controller = RetailSourceController(_api(client));
    await controller.load();

    await tester.pumpWidget(
      await _wrap(
        RetailSourceScope(
          controller: controller,
          child: SalesPage(
            api: _api(client),
            loader: (_) async => {
              'status': 'no_data',
              'available': false,
              'currency': 'CAD',
              'capabilities': <String>[],
              'summary': null,
              'trend': {'granularity': 'month', 'points': <dynamic>[]},
              'strongest_period': null,
              'weakest_period': null,
              'forecast': null,
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('Shopify orders'), findsOneWidget);
    expect(find.textContaining('unexpected'), findsNothing);
    controller.dispose();
  });
}
