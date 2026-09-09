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
        6 => 'bigcommerce',
        7 => 'adobe-commerce',
        8 => 'wix-ecommerce',
        9 => 'squarespace-commerce',
        10 => 'prestashop',
        11 => 'ecwid',
        12 => 'shopware',
        13 => 'salesforce-commerce-cloud',
        14 => 'commercetools',
        15 => 'vtex',
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
        6 => 'BigCommerce',
        7 => 'Adobe Commerce / Magento',
        8 => 'Wix eCommerce',
        9 => 'Squarespace Commerce',
        10 => 'PrestaShop',
        11 => 'Ecwid',
        12 => 'Shopware',
        13 => 'Salesforce Commerce Cloud',
        14 => 'commercetools',
        15 => 'VTEX',
        29 => 'WooCommerce',
        _ => 'Provider $index',
      },
      'category': switch (index) {
        >= 1 && <= 4 => 'marketplace',
        5 => 'pos',
        >= 16 && <= 28 => 'marketplace',
        _ => 'ecommerce',
      },
      'implementation_status': switch (index) {
        0 => 'AVAILABLE',
        29 => 'BETA',
        >= 1 && <= 5 => 'CONFIGURATION_REQUIRED',
        _ => 'COMING_SOON',
      },
      'customer_status': index == 0 ? 'AVAILABLE' : 'COMING_SOON',
      'internal_test_available': false,
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
  LocaleController? localeController,
}) async {
  final locale = localeController ?? LocaleController(store: _LocaleStore());
  if (localeController == null) {
    await locale.initialize();
    await locale.setLocale('fr');
  }
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
    expect(
      find.byKey(const ValueKey('add-ecommerce-connector')),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('provider-shopify')), findsNothing);
    expect(find.byKey(const ValueKey('provider-woocommerce')), findsNothing);

    await tester.tap(find.byKey(const ValueKey('add-ecommerce-connector')));
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('ecommerce-provider-search')),
      findsOneWidget,
    );
    expect(find.text('Shopify'), findsOneWidget);
    expect(find.text('WooCommerce'), findsOneWidget);
    expect(find.text('VTEX'), findsOneWidget);
    expect(find.text('Disponible'), findsOneWidget);
    expect(find.text('Bientôt disponible'), findsNWidgets(11));
    for (final provider in const [
      'shopify',
      'woocommerce',
      'bigcommerce',
      'adobe-commerce',
      'wix-ecommerce',
      'squarespace-commerce',
      'prestashop',
      'ecwid',
      'shopware',
      'salesforce-commerce-cloud',
      'commercetools',
      'vtex',
    ]) {
      expect(find.byKey(ValueKey('brand-icon-$provider')), findsOneWidget);
    }
    for (final asset in const [
      'assets/brands/magento.svg',
      'assets/brands/ecwid.svg',
      'assets/brands/salesforce.svg',
      'assets/brands/commercetools.svg',
    ]) {
      expect(File(asset).existsSync(), isTrue, reason: '$asset must exist');
    }
    await tester.tap(find.byKey(const ValueKey('select-shopify')));
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('ecommerce-provider-search')),
      findsNothing,
    );
    expect(find.byKey(const ValueKey('provider-shopify')), findsOneWidget);
    expect(find.text('Disponible'), findsOneWidget);

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

  testWidgets('unfinished WooCommerce is coming soon and cannot connect', (
    tester,
  ) async {
    _useDesktopViewport(tester);
    var authorizationRequested = false;
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
        authorizationRequested = true;
      }
      return http.Response('{}', 200);
    });
    await tester.pumpWidget(
      await _app(
        client,
        openConnectorUrl: (uri) async => true,
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('add-ecommerce-connector')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('ecommerce-provider-search')),
      'WooCommerce',
    );
    await tester.pumpAndSettle();
    expect(find.text('Shopify'), findsNothing);
    await tester.tap(find.byKey(const ValueKey('select-woocommerce')));
    await tester.pumpAndSettle();

    final connectWoo = find.byKey(const ValueKey('connect-woocommerce'));
    expect(connectWoo, findsOneWidget);
    expect(find.text('Beta'), findsNothing);
    expect(find.text('Bientôt disponible'), findsNWidgets(2));
    expect(find.byKey(const ValueKey('test-woocommerce')), findsNothing);
    expect(tester.widget<FilledButton>(connectWoo).onPressed, isNull);
    await tester.tap(connectWoo);
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('woocommerce-store-url')), findsNothing);
    expect(authorizationRequested, isFalse);
  });

  testWidgets('internal WooCommerce test CTA reuses authorization flow', (
    tester,
  ) async {
    _useDesktopViewport(tester);
    final catalog = _catalog();
    catalog.last['internal_test_available'] = true;
    final client = MockClient((request) async {
      if (request.url.path.endsWith('/connectors')) {
        return http.Response(jsonEncode(catalog), 200);
      }
      if (request.url.path.endsWith('/connectors/connections') ||
          request.url.path.endsWith('/datasets')) {
        return http.Response('[]', 200);
      }
      return http.Response('{}', 200);
    });

    await tester.pumpWidget(await _app(client));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('add-ecommerce-connector')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('select-woocommerce')));
    await tester.pumpAndSettle();

    expect(find.text('Bientôt disponible'), findsOneWidget);
    expect(find.text('Tester le connecteur'), findsOneWidget);
    expect(find.byKey(const ValueKey('connect-woocommerce')), findsNothing);
    final testWoo = find.byKey(const ValueKey('test-woocommerce'));
    expect(tester.widget<OutlinedButton>(testWoo).onPressed, isNotNull);
    await tester.tap(testWoo);
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('woocommerce-store-url')), findsOneWidget);
  });

  testWidgets('coming-soon provider has a disabled CTA and selection cancels', (
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
    await tester.tap(find.byKey(const ValueKey('add-ecommerce-connector')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('ecommerce-provider-search')),
      'BigCommerce',
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('select-bigcommerce')));
    await tester.pumpAndSettle();

    expect(find.text('BigCommerce'), findsOneWidget);
    expect(find.text('Commandes'), findsOneWidget);
    expect(find.text('Bientôt disponible'), findsNWidgets(2));
    final disabled = tester.widget<FilledButton>(
      find.byKey(const ValueKey('connect-bigcommerce')),
    );
    expect(disabled.onPressed, isNull);
    await tester.tap(find.byKey(const ValueKey('cancel-provider-selection')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('provider-bigcommerce')), findsNothing);
  });

  testWidgets('provider becomes actionable only when customer status is available', (
    tester,
  ) async {
    _useDesktopViewport(tester);
    final catalog = _catalog();
    catalog.last['customer_status'] = 'AVAILABLE';
    final client = MockClient((request) async {
      if (request.url.path.endsWith('/connectors')) {
        return http.Response(jsonEncode(catalog), 200);
      }
      if (request.url.path.endsWith('/connectors/connections') ||
          request.url.path.endsWith('/datasets')) {
        return http.Response('[]', 200);
      }
      return http.Response('{}', 200);
    });

    await tester.pumpWidget(await _app(client));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('add-ecommerce-connector')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('select-woocommerce')));
    await tester.pumpAndSettle();

    final connectWoo = find.byKey(const ValueKey('connect-woocommerce'));
    expect(tester.widget<FilledButton>(connectWoo).onPressed, isNotNull);
    expect(find.text('Disponible'), findsOneWidget);
    await tester.tap(connectWoo);
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('woocommerce-store-url')), findsOneWidget);
  });

  testWidgets('global locale switching immediately updates connector status', (
    tester,
  ) async {
    _useDesktopViewport(tester);
    final locale = LocaleController(store: _LocaleStore());
    await locale.initialize();
    await locale.setLocale('fr-CA');
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

    await tester.pumpWidget(
      await _app(client, localeController: locale),
    );
    await tester.pumpAndSettle();
    expect(find.text('Connecter une boutique en ligne'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('add-ecommerce-connector')));
    await tester.pumpAndSettle();
    expect(find.text('Disponible'), findsOneWidget);
    expect(find.text('Bientôt disponible'), findsNWidgets(11));
    await tester.tap(find.byKey(const ValueKey('select-woocommerce')));
    await tester.pumpAndSettle();
    expect(find.text('Bientôt disponible'), findsNWidgets(2));

    await locale.setLocale('en-US');
    await tester.pumpAndSettle();
    expect(find.text('Connect an online store'), findsOneWidget);
    expect(find.text('Coming soon'), findsNWidgets(2));
  });

  test('Connector Hub source exposes no internal Beta status or hardcoded copy', () {
    final source = File(
      'lib/features/connectors/connector_hub.dart',
    ).readAsStringSync();
    expect(source, isNot(contains("'BETA'")));
    expect(source, isNot(contains("text('beta')")));
    expect(source, isNot(contains('Synchronization failed')));
    expect(source, isNot(contains('Storage unavailable')));
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
    expect(find.text('La synchronisation a échoué'), findsOneWidget);
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
      final connectorCopy =
          (json['company'] as Map<String, dynamic>)['connectorHub']
              as Map<String, dynamic>;
      for (final key in const [
        'commerceSources',
        'addOnlineStore',
        'providerSearchHint',
        'providerDescription',
        'connectToAvenqo',
        'testConnector',
        'connectedStores',
        'available',
        'comingSoon',
        'connect',
        'connectAnother',
        'cancel',
        'close',
        'search',
        'connection',
        'connected',
        'ready',
        'reauthorizationRequired',
        'syncing',
        'lastSync',
        'disconnect',
        'reconnect',
        'syncFailed',
        'storageUnavailable',
        'capabilities',
        'capabilityOrders',
        'capabilityCustomers',
        'capabilityProducts',
        'capabilityInventory',
      ]) {
        expect(
          connectorCopy[key]?.toString().trim(),
          isNotEmpty,
          reason: '$locale must explicitly localize $key',
        );
      }
      expect(
        connectorCopy.containsKey('beta'),
        isFalse,
        reason: '$locale must not expose an internal beta label',
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

  test('fr-CA and en-US expose approved customer-facing connector copy', () {
    Map<String, dynamic> hub(String locale) {
      final json =
          jsonDecode(File('assets/i18n/$locale.json').readAsStringSync())
              as Map<String, dynamic>;
      return (json['company'] as Map<String, dynamic>)['connectorHub']
          as Map<String, dynamic>;
    }

    final french = hub('fr-CA');
    expect(french['addOnlineStore'], 'Connecter une boutique en ligne');
    expect(french['providerSearchHint'], 'Rechercher une plateforme...');
    expect(french['available'], 'Disponible');
    expect(french['comingSoon'], 'Bientôt disponible');
    expect(french['connectToAvenqo'], 'Connecter à Avenqo');
    expect(french['connectedStores'], 'Boutiques connectées');
    expect(french['connected'], 'Connecté');
    expect(french['ready'], 'Prêt');
    expect(french['reauthorizationRequired'], 'Nouvelle autorisation requise');

    final english = hub('en-US');
    expect(english['addOnlineStore'], 'Connect an online store');
    expect(english['providerSearchHint'], 'Search for a platform...');
    expect(english['available'], 'Available');
    expect(english['comingSoon'], 'Coming soon');
    expect(english['connectToAvenqo'], 'Connect to Avenqo');
    expect(english['connectedStores'], 'Connected stores');
  });

  testWidgets('fr-CA connector actions fit light and dark responsive layouts', (
    tester,
  ) async {
    final json =
        jsonDecode(File('assets/i18n/fr-CA.json').readAsStringSync())
            as Map<String, dynamic>;
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

        expect(
          find.byKey(const ValueKey('add-ecommerce-connector')),
          findsOneWidget,
        );
        expect(find.byKey(const ValueKey('connect-shopify')), findsNothing);
        await tester.tap(find.byKey(const ValueKey('add-ecommerce-connector')));
        await tester.pumpAndSettle();
        await tester.tap(find.byKey(const ValueKey('select-woocommerce')));
        await tester.pumpAndSettle();
        expect(
          find.byKey(const ValueKey('provider-woocommerce')),
          findsOneWidget,
        );
        await tester.tap(
          find.byKey(const ValueKey('cancel-provider-selection')),
        );
        await tester.pumpAndSettle();
        expect(
          find.byKey(const ValueKey('provider-woocommerce')),
          findsNothing,
        );
        expect(
          tester.takeException(),
          isNull,
          reason: '$brightness at ${size.width} px',
        );
      }
    }
  });
}
