import 'dart:convert';
import 'dart:io';

import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/token_store.dart';
import 'package:avenqo/features/connectors/connector_hub.dart';
import 'package:avenqo/i18n/locale_controller.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/i18n/translations.dart';
import 'package:avenqo/pages/connections_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class _TokenStore implements TokenStore {
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
  Future<String?> read() async => null;
  @override
  Future<void> write(String code) async {}
}

List<Map<String, dynamic>> _catalog() => [
  for (var index = 0; index < 30; index++)
    {
      'provider': switch (index) {
        0 => 'shopify',
        1 => 'amazon-seller-central',
        2 => 'ebay',
        3 => 'etsy',
        4 => 'tiktok-shop',
        5 => 'square',
        29 => 'woocommerce',
        _ => 'provider-$index',
      },
      'display_name': switch (index) {
        0 => 'Shopify',
        1 => 'Amazon Seller Central / SP-API',
        2 => 'eBay',
        3 => 'Etsy',
        4 => 'TikTok Shop',
        5 => 'Square',
        29 => 'WooCommerce',
        _ => 'Provider $index',
      },
      'category': switch (index) {
        >= 1 && <= 4 => 'marketplace',
        5 => 'pos',
        _ => 'ecommerce',
      },
      'implementation_status': switch (index) {
        0 => 'AVAILABLE',
        29 => 'BETA',
        >= 1 && <= 5 => 'CONFIGURATION_REQUIRED',
        _ => 'COMING_SOON',
      },
      'configured': index == 0 || index == 29,
      'priority': index <= 5 ? 'P0' : 'P2',
      'auth_method': index == 5 ? 'OAUTH2' : 'PARTNER_AUTHORIZATION',
      'capabilities': index == 5
          ? ['orders', 'locations', 'payments']
          : ['orders', 'products', 'inventory'],
    },
];

Map<String, dynamic> _connection({String status = 'READY'}) => {
  'id': '11111111-1111-1111-1111-111111111111',
  'provider': 'shopify',
  'external_account_id': 'shop.myshopify.com',
  'display_name': 'Shop',
  'status': status,
  'connection_status': status == 'DISCONNECTED' ? 'DISCONNECTED' : 'CONNECTED',
  'sync_status': status,
  'capabilities': <String>[],
  'records_processed': 42,
};

Future<Widget> _app(
  http.Client client, {
  ConnectorUrlLauncher? openConnectorUrl,
}) async {
  final locale = LocaleController(store: _LocaleStore());
  await locale.initialize();
  await locale.setLocale('fr');
  final api = ApiClient(
    tokenStore: _TokenStore(),
    httpClient: client,
    baseUrl: 'https://avenqo.test/api/v1',
  );
  return AvenqoLocaleScope(
    controller: locale,
    child: MaterialApp(
      home: Scaffold(
        body: ConnectionsPage(
          api: api,
          openConnectorUrl: openConnectorUrl ?? (uri) async => true,
        ),
      ),
    ),
  );
}

void _useDesktopViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(1280, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

void main() {
  testWidgets('Connector Hub exposes truthful provider readiness', (
    tester,
  ) async {
    _useDesktopViewport(tester);
    Uri? launched;
    final client = MockClient((request) async {
      if (request.method == 'GET' && request.url.path.endsWith('/connectors')) {
        return http.Response(jsonEncode(_catalog()), 200);
      }
      if (request.method == 'GET' &&
          request.url.path.endsWith('/connectors/connections')) {
        return http.Response('[]', 200);
      }
      if (request.method == 'GET' && request.url.path.endsWith('/datasets')) {
        return http.Response('[]', 200);
      }
      if (request.method == 'POST' &&
          request.url.path.endsWith('/connectors/shopify/authorize')) {
        return http.Response(
          '{"authorization_url":"https://shop.myshopify.com/admin/oauth/authorize"}',
          200,
        );
      }
      return http.Response('{}', 200);
    });
    await tester.pumpWidget(
      await _app(
        client,
        openConnectorUrl: (uri) async {
          launched = uri;
          return true;
        },
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Centre de connecteurs Retail'), findsOneWidget);
    expect(find.text('Shopify'), findsOneWidget);
    expect(find.text('Bientôt disponible'), findsNWidgets(23));
    expect(find.text('Beta'), findsOneWidget);
    expect(find.text('Configuration required'), findsNWidgets(5));

    final connectShopify = find.byKey(const ValueKey('connect-shopify'));
    await tester.ensureVisible(connectShopify);
    await tester.pumpAndSettle();
    await tester.tap(connectShopify);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('shopify-domain')),
      'shop.myshopify.com',
    );
    await tester.tap(find.byKey(const ValueKey('authorize-shopify')));
    await tester.pumpAndSettle();

    expect(launched?.host, 'shop.myshopify.com');
  });

  testWidgets('configured WooCommerce beta opens standard authorization', (
    tester,
  ) async {
    _useDesktopViewport(tester);
    Uri? launched;
    final client = MockClient((request) async {
      if (request.method == 'GET' && request.url.path.endsWith('/connectors')) {
        return http.Response(jsonEncode(_catalog()), 200);
      }
      if (request.method == 'GET' &&
          (request.url.path.endsWith('/connectors/connections') ||
              request.url.path.endsWith('/datasets'))) {
        return http.Response('[]', 200);
      }
      if (request.method == 'POST' &&
          request.url.path.endsWith('/connectors/woocommerce/authorize')) {
        final payload = jsonDecode(request.body) as Map<String, dynamic>;
        expect(payload['store_url'], 'https://shop.example.com');
        return http.Response(
          '{"authorization_url":"https://shop.example.com/wc-auth/v1/authorize"}',
          200,
        );
      }
      return http.Response('{}', 200);
    });
    await tester.pumpWidget(
      await _app(
        client,
        openConnectorUrl: (uri) async {
          launched = uri;
          return true;
        },
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('connector-search')),
      'WooCommerce',
    );
    await tester.pumpAndSettle();

    final connectWoo = find.byKey(const ValueKey('connect-woocommerce'));
    expect(connectWoo, findsOneWidget);
    await tester.tap(connectWoo);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('woocommerce-store-url')),
      'https://shop.example.com',
    );
    await tester.tap(find.byKey(const ValueKey('authorize-woocommerce')));
    await tester.pumpAndSettle();

    expect(launched?.path, '/wc-auth/v1/authorize');
  });

  testWidgets('search and metadata filters never enable planned providers', (
    tester,
  ) async {
    _useDesktopViewport(tester);
    final client = MockClient((request) async {
      if (request.url.path.endsWith('/connectors')) {
        return http.Response(jsonEncode(_catalog()), 200);
      }
      if (request.url.path.endsWith('/connectors/connections') ||
          request.url.path.endsWith('/datasets')) {
        return http.Response('[]', 200);
      }
      return http.Response('{}', 200);
    });

    await tester.pumpWidget(await _app(client));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('connector-search')),
      'Amazon',
    );
    await tester.pumpAndSettle();

    expect(find.text('Amazon Seller Central / SP-API'), findsOneWidget);
    expect(find.text('orders'), findsOneWidget);
    expect(find.byKey(const ValueKey('connect-shopify')), findsNothing);

    await tester.enterText(find.byKey(const ValueKey('connector-search')), '');
    await tester.tap(find.byKey(const ValueKey('connector-category-filter')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('POS').last);
    await tester.pumpAndSettle();

    expect(find.text('Square'), findsOneWidget);
    expect(find.text('Shopify'), findsNothing);

    await tester.tap(find.byKey(const ValueKey('connector-status-filter')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Configuration required').last);
    await tester.pumpAndSettle();

    expect(find.text('Square'), findsOneWidget);
    expect(find.byKey(const ValueKey('connect-shopify')), findsNothing);
  });

  testWidgets('a connected Shopify store can start a sync', (tester) async {
    _useDesktopViewport(tester);
    var syncCalled = false;
    final client = MockClient((request) async {
      if (request.method == 'GET' && request.url.path.endsWith('/connectors')) {
        return http.Response(jsonEncode(_catalog()), 200);
      }
      if (request.method == 'GET' &&
          request.url.path.endsWith('/connectors/connections')) {
        return http.Response(jsonEncode([_connection()]), 200);
      }
      if (request.method == 'GET' && request.url.path.endsWith('/datasets')) {
        return http.Response('[]', 200);
      }
      if (request.method == 'POST' && request.url.path.endsWith('/sync')) {
        syncCalled = true;
        return http.Response(
          '{"connection_id":"11111111-1111-1111-1111-111111111111","status":"SYNCING"}',
          202,
        );
      }
      return http.Response('{}', 200);
    });

    await tester.pumpWidget(await _app(client));
    await tester.pumpAndSettle();
    final sync = find.byTooltip('Synchroniser maintenant');
    await tester.ensureVisible(sync);
    await tester.pumpAndSettle();
    await tester.tap(sync);
    await tester.pump();

    expect(syncCalled, isTrue);
    expect(find.text('Synchronisation'), findsOneWidget);
  });

  testWidgets('failed synchronization remains connected and offers retry', (
    tester,
  ) async {
    _useDesktopViewport(tester);
    final client = MockClient((request) async {
      if (request.url.path.endsWith('/connectors/connections')) {
        return http.Response(jsonEncode([_connection(status: 'ERROR')]), 200);
      }
      if (request.url.path.endsWith('/connectors')) {
        return http.Response(jsonEncode(_catalog()), 200);
      }
      if (request.url.path.endsWith('/datasets')) {
        return http.Response('[]', 200);
      }
      return http.Response('{}', 200);
    });

    await tester.pumpWidget(await _app(client));
    await tester.pumpAndSettle();

    expect(find.text('Connexion: Connecté'), findsOneWidget);
    expect(find.text('Synchronisation échouée'), findsOneWidget);
    expect(find.byTooltip('Synchroniser maintenant'), findsOneWidget);
  });

  testWidgets('a connected Shopify store can be disconnected', (tester) async {
    _useDesktopViewport(tester);
    var disconnectCalled = false;
    final client = MockClient((request) async {
      if (request.method == 'GET' && request.url.path.endsWith('/connectors')) {
        return http.Response(jsonEncode(_catalog()), 200);
      }
      if (request.method == 'GET' &&
          request.url.path.endsWith('/connectors/connections')) {
        return http.Response(jsonEncode([_connection()]), 200);
      }
      if (request.method == 'GET' && request.url.path.endsWith('/datasets')) {
        return http.Response('[]', 200);
      }
      if (request.method == 'POST' &&
          request.url.path.endsWith('/disconnect')) {
        disconnectCalled = true;
        return http.Response(
          jsonEncode(_connection(status: 'DISCONNECTED')),
          200,
        );
      }
      return http.Response('{}', 200);
    });

    await tester.pumpWidget(await _app(client));
    await tester.pumpAndSettle();
    final disconnect = find.byTooltip('Déconnecter');
    await tester.ensureVisible(disconnect);
    await tester.pumpAndSettle();
    await tester.tap(disconnect);
    await tester.pumpAndSettle();
    expect(find.text('Déconnecter cette boutique ?'), findsOneWidget);
    await tester.tap(find.widgetWithIcon(FilledButton, Icons.link_off));
    await tester.pumpAndSettle();

    expect(disconnectCalled, isTrue);
    expect(find.text('Déconnecté'), findsOneWidget);
  });

  testWidgets('connector API failure leaves file imports usable', (
    tester,
  ) async {
    final client = MockClient((request) async {
      if (request.method == 'GET' && request.url.path.contains('/connectors')) {
        return http.Response('{"detail":"offline"}', 503);
      }
      if (request.method == 'GET' && request.url.path.endsWith('/datasets')) {
        return http.Response('[]', 200);
      }
      return http.Response('{}', 200);
    });

    await tester.pumpWidget(await _app(client));
    await tester.pumpAndSettle();

    expect(find.text('Ajouter des fichiers'), findsOneWidget);
    expect(
      find.text('Le catalogue de connecteurs est temporairement indisponible.'),
      findsOneWidget,
    );
  });

  testWidgets('Connector Hub fits a mobile viewport in all 50 locales', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final localeFiles = Directory('assets/i18n')
        .listSync()
        .whereType<File>()
        .where(
          (file) =>
              file.path.endsWith('.json') &&
              !file.path.endsWith('_locales.json'),
        )
        .toList(growable: false);
    expect(localeFiles, hasLength(50));

    for (final file in localeFiles) {
      final locale = file.uri.pathSegments.last.replaceFirst('.json', '');
      final json = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
      final strings = CompanyStrings.fromJson(
        json['company'] as Map<String, dynamic>,
      );
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: ConnectorHub(
                key: ValueKey(locale),
                catalog: _catalog().take(2).toList(growable: false),
                connections: [_connection()],
                busyConnectionIds: const <String>{},
                authorizingProvider: null,
                catalogUnavailable: false,
                onConnect: (_) {},
                onSync: (_) async {},
                onDisconnect: (_) async {},
                onRefresh: () {},
                t: strings,
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      expect(
        tester.takeException(),
        isNull,
        reason: 'Connector Hub overflow or layout error in $locale',
      );
    }
  });

  testWidgets('fr-CA connector actions fit light and dark responsive layouts', (
    tester,
  ) async {
    final json = jsonDecode(
      File('assets/i18n/fr-CA.json').readAsStringSync(),
    ) as Map<String, dynamic>;
    final strings = CompanyStrings.fromJson(
      json['company'] as Map<String, dynamic>,
    );
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    tester.view.devicePixelRatio = 1;

    for (final brightness in Brightness.values) {
      for (final size in const [Size(390, 844), Size(1280, 900)]) {
        tester.view.physicalSize = size;
        await tester.pumpWidget(
          MaterialApp(
            theme: ThemeData(brightness: brightness),
            home: Scaffold(
              body: SingleChildScrollView(
                padding: const EdgeInsets.all(16),
                child: ConnectorHub(
                  catalog: _catalog(),
                  connections: const [],
                  busyConnectionIds: const <String>{},
                  authorizingProvider: null,
                  catalogUnavailable: false,
                  onConnect: (_) {},
                  onSync: (_) async {},
                  onDisconnect: (_) async {},
                  onRefresh: () {},
                  t: strings,
                ),
              ),
            ),
          ),
        );
        await tester.pump();

        expect(find.byKey(const ValueKey('connect-shopify')), findsOneWidget);
        expect(
          find.byKey(const ValueKey('connect-woocommerce')),
          findsOneWidget,
        );
        expect(find.text('Beta'), findsOneWidget);
        expect(
          tester.takeException(),
          isNull,
          reason: '$brightness at ${size.width} px',
        );
      }
    }
  });
}
