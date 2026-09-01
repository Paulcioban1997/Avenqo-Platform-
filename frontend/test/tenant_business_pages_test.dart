import 'dart:async';

import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/token_store.dart';
import 'package:avenqo/i18n/locale_controller.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/pages/customers_page.dart';
import 'package:avenqo/pages/products_page.dart';
import 'package:avenqo/pages/recommendations_page.dart';
import 'package:avenqo/pages/sales_page.dart';
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
  _LocaleStore([this.code = 'en']);
  final String code;
  @override
  Future<String?> read() async => code;
  @override
  Future<void> write(String code) async {}
}

ApiClient _api() => ApiClient(
  tokenStore: _Tokens(),
  httpClient: MockClient((_) async => http.Response('{}', 200)),
  baseUrl: 'https://avenqo.test/api/v1',
);

Future<Widget> _wrap(Widget child, {bool dark = false, String localeCode = 'en'}) async {
  final locale = LocaleController(store: _LocaleStore(localeCode));
  await locale.initialize();
  return AvenqoLocaleScope(
    controller: locale,
    child: MaterialApp(
      theme: ThemeData(
        brightness: dark ? Brightness.dark : Brightness.light,
        extensions: [dark ? AvenqoColors.dark : AvenqoColors.light],
      ),
      home: Scaffold(body: child),
    ),
  );
}

Map<String, dynamic> _sales({String status = 'ready', bool available = true}) =>
    {
      'status': status,
      'available': available,
      'currency': 'CAD',
      'capabilities': ['revenue'],
      'summary': available
          ? {
              'revenue': 175.0,
              'orders': 3,
              'average_order_value': 58.33,
              'revenue_change_percent': 25.0,
              'orders_change_percent': null,
            }
          : null,
      'trend': {
        'granularity': 'day',
        'points': available
            ? [
                {'period': '2026-08-20', 'revenue': 100.0, 'orders': 1},
                {'period': '2026-08-28', 'revenue': 75.0, 'orders': 2},
              ]
            : [],
      },
      'strongest_period': available
          ? {'period': '2026-08-20', 'revenue': 100.0, 'orders': 1}
          : null,
      'weakest_period': available
          ? {'period': '2026-08-28', 'revenue': 75.0, 'orders': 2}
          : null,
      'forecast': available
          ? {'forecasted_total': 170.0, 'points': [], 'granularity': 'week'}
          : null,
    };

Map<String, dynamic> _customers({
  String status = 'ready',
  bool available = true,
  int page = 1,
}) => {
  'status': status,
  'available': available,
  'currency': 'EUR',
  'capabilities': ['customers'],
  'summary': available
      ? {
          'total_customers': 3,
          'active_customers': 2,
          'new_customers': 1,
          'repeat_customers': 1,
          'purchase_frequency': 1.33,
          'average_customer_value': 75.0,
        }
      : null,
  'segments': available
      ? [
          {'label': 'loyal', 'count': 1},
        ]
      : [],
  'risks': available
      ? [
          {'label': 'churn_prediction', 'count': 1},
        ]
      : [],
  'items': available
      ? [
          {
            'customer_id': page == 1 ? 'C1' : 'C2',
            'orders': 2,
            'total_value': 125.0,
            'last_purchase': '2026-08-28T00:00:00',
            'segment': 'loyal',
            'risk': 'churn_prediction',
          },
        ]
      : [],
  'pagination': {'page': page, 'page_size': 1, 'total': 2, 'pages': 2},
};

Map<String, dynamic> _products({
  String status = 'ready',
  bool available = true,
  int page = 1,
}) => {
  'status': status,
  'available': available,
  'currency': 'CAD',
  'capabilities': ['products', 'revenue'],
  'summary': available
      ? {
          'total_products': 2,
          'active_products': 1,
          'products_with_activity': 2,
          'revenue': 400.0,
          'units': 8.0,
          'average_selling_price': 50.0,
          'top_product_revenue_share': 62.5,
          'out_of_stock_products': 1,
        }
      : null,
  'categories': available
      ? [
          {'category': 'Drinks', 'product_count': 2, 'revenue': 400.0, 'units': 8.0, 'revenue_share': 100.0},
        ]
      : [],
  'trend': {'granularity': 'day', 'points': []},
  'items': available
      ? [
          {
            'product_id': page == 1 ? 'P1' : 'P2',
            'name': page == 1 ? 'Coffee' : 'Tea',
            'category': 'Drinks',
            'revenue': 250.0,
            'quantity': 3.0,
            'average_price': 83.33,
            'last_activity': '2026-08-28T00:00:00',
            'performance': 'weak',
          },
        ]
      : [],
  'pagination': {'page': page, 'page_size': 1, 'total': 2, 'pages': 2},
};

Map<String, dynamic> _recommendations({String status = 'ready', bool empty = false}) => {
  'status': status,
  'currency': 'CAD',
  'generated_at': '2026-08-28T00:00:00Z',
  'recommendations': empty
      ? []
      : [
          {
            'id': 'product_decline:P1',
            'type': 'product_decline',
            'title': 'product_decline',
            'explanation': 'product_revenue_changed',
            'priority': 'high',
            'source_capability': 'products',
            'evidence': {
              'product_id': 'P1',
              'product_name': 'Coffee',
              'current': 50.0,
              'comparison': 200.0,
              'change_percent': -75.0,
            },
            'affected_entity': 'P1',
            'confidence': 1.0,
            'estimated_impact': null,
            'suggested_action': 'review_product_performance',
            'action_route': '/products',
            'generated_at': '2026-08-28T00:00:00Z',
            'source_model_version': null,
            'lifecycle': 'active',
          },
        ],
};

void main() {
  testWidgets('Sales loads real KPIs, CAD trend and forecast in dark mode', (
    tester,
  ) async {
    final completer = Completer<Map<String, dynamic>>();
    await tester.pumpWidget(
      await _wrap(
        SalesPage(api: _api(), loader: (_) => completer.future),
        dark: true,
      ),
    );
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    completer.complete(_sales());
    await tester.pumpAndSettle();
    expect(find.textContaining('175'), findsOneWidget);
    expect(find.text('+25.0%'), findsOneWidget);
    expect(find.text('Revenue trend'), findsOneWidget);
    expect(find.text('Validated sales forecast'), findsOneWidget);
  });

  testWidgets('Sales reloads on period change', (tester) async {
    final periods = <String>[];
    await tester.pumpWidget(
      await _wrap(
        SalesPage(
          api: _api(),
          loader: (period) async {
            periods.add(period);
            return _sales();
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byType(DropdownButton<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Last 90 days').last);
    await tester.pumpAndSettle();
    expect(periods, ['last_30_days', 'last_90_days']);
  });

  testWidgets('Sales shows processing and unavailable states', (tester) async {
    await tester.pumpWidget(
      await _wrap(
        SalesPage(
          key: const ValueKey('processing'),
          api: _api(),
          loader: (_) async => _sales(status: 'processing', available: false),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('Analyzing'), findsOneWidget);
    await tester.pumpWidget(
      await _wrap(
        SalesPage(
          key: const ValueKey('unavailable'),
          api: _api(),
          loader: (_) async => _sales(available: false),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('unavailable'), findsOneWidget);
    expect(find.text('Connect my tools'), findsOneWidget);
  });

  testWidgets('Sales error is generic and retry succeeds', (tester) async {
    var calls = 0;
    await tester.pumpWidget(
      await _wrap(
        SalesPage(
          api: _api(),
          loader: (_) async {
            calls += 1;
            if (calls == 1) throw StateError('private');
            return _sales();
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('private'), findsNothing);
    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();
    expect(calls, 2);
    expect(find.text('Revenue trend'), findsOneWidget);
  });

  testWidgets('Customers renders summary, table, segment and risk', (
    tester,
  ) async {
    await tester.pumpWidget(
      await _wrap(
        CustomersPage(api: _api(), loader: (_, _) async => _customers()),
        dark: true,
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Total customers'), findsOneWidget);
    expect(find.text('C1'), findsOneWidget);
    expect(find.textContaining('Segment: loyal'), findsOneWidget);
    expect(find.textContaining('Risk: churn_prediction'), findsOneWidget);
  });

  testWidgets('Customers sends search and pagination to loader', (
    tester,
  ) async {
    final calls = <(int, String)>[];
    await tester.pumpWidget(
      await _wrap(
        CustomersPage(
          api: _api(),
          loader: (page, search) async {
            calls.add((page, search));
            return _customers(page: page);
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'C2');
    await tester.pump(const Duration(milliseconds: 301));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byIcon(Icons.chevron_right));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.chevron_right));
    await tester.pumpAndSettle();
    expect(calls, [(1, ''), (1, 'C2'), (2, 'C2')]);
    expect(
      find.descendant(of: find.byType(DataTable), matching: find.text('C2')),
      findsOneWidget,
    );
  });

  testWidgets('Customers shows processing, unavailable and retry states', (
    tester,
  ) async {
    var calls = 0;
    await tester.pumpWidget(
      await _wrap(
        CustomersPage(
          api: _api(),
          loader: (_, _) async {
            calls += 1;
            if (calls == 1) throw StateError('private');
            return _customers(status: 'processing', available: false);
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Analyzing'), findsOneWidget);

    await tester.pumpWidget(
      await _wrap(
        CustomersPage(
          key: const ValueKey('unavailable'),
          api: _api(),
          loader: (_, _) async => _customers(available: false),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('unavailable'), findsOneWidget);
  });

  testWidgets('Account identity change clears tenant page results and search', (
    tester,
  ) async {
    await tester.pumpWidget(
      await _wrap(
        CustomersPage(
          key: const ValueKey('customers-company-a'),
          api: _api(),
          loader: (_, _) async => _customers(),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'C1');
    expect(find.text('C1'), findsWidgets);

    await tester.pumpWidget(
      await _wrap(
        CustomersPage(
          key: const ValueKey('customers-company-b'),
          api: _api(),
          loader: (_, search) async {
            expect(search, isEmpty);
            return _customers(page: 2);
          },
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.widgetWithText(TextField, 'C1'), findsNothing);
    expect(
      find.descendant(of: find.byType(DataTable), matching: find.text('C2')),
      findsOneWidget,
    );
  });

  testWidgets('Products loads supported KPIs and partial data in French dark mode', (tester) async {
    final completer = Completer<Map<String, dynamic>>();
    await tester.pumpWidget(
      await _wrap(
        ProductsPage(api: _api(), loader: (_, _, _, _, _) => completer.future),
        dark: true,
        localeCode: 'fr',
      ),
    );
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    completer.complete(_products(status: 'partial_ready'));
    await tester.pumpAndSettle();
    expect(find.text('Produits au total'), findsOneWidget);
    expect(find.textContaining('encore en traitement'), findsOneWidget);
    expect(find.text('Coffee'), findsOneWidget);
    expect(find.textContaining('400'), findsOneWidget);
  });

  testWidgets('Products sends search, filter, sort and pagination to loader', (tester) async {
    final calls = <(int, String, String?, String?, String)>[];
    await tester.pumpWidget(
      await _wrap(
        ProductsPage(
          api: _api(),
          loader: (page, search, category, performance, sort) async {
            calls.add((page, search, category, performance, sort));
            return _products(page: page);
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Tea');
    await tester.pump(const Duration(milliseconds: 301));
    await tester.pumpAndSettle();
    final weakSegment = find.descendant(
      of: find.byType(SegmentedButton<String?>),
      matching: find.text('Weak'),
    );
    await tester.drag(find.byType(ListView), const Offset(0, -300));
    await tester.pumpAndSettle();
    await tester.tap(weakSegment);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byIcon(Icons.chevron_right));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.chevron_right));
    await tester.pumpAndSettle();
    expect(calls.last, (2, 'Tea', null, 'weak', 'revenue'));
    expect(
      find.descendant(of: find.byType(DataTable), matching: find.text('Tea')),
      findsOneWidget,
    );
  });

  testWidgets('Products opens tenant detail and handles unavailable and retry states', (tester) async {
    var calls = 0;
    await tester.pumpWidget(
      await _wrap(
        ProductsPage(
          api: _api(),
          loader: (_, _, _, _, _) async {
            calls += 1;
            if (calls == 1) throw StateError('private');
            return _products();
          },
          detailLoader: (id) async => {..._products()['items'][0], 'currency': 'CAD'},
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('private'), findsNothing);
    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Coffee'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Coffee'));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsOneWidget);
    await tester.tap(find.byIcon(Icons.close));
    await tester.pumpAndSettle();

    await tester.pumpWidget(
      await _wrap(ProductsPage(key: const ValueKey('none'), api: _api(), loader: (_, _, _, _, _) async => _products(available: false))),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('unavailable'), findsOneWidget);
  });

  testWidgets('Recommendations localizes priority, evidence and routed action', (tester) async {
    String? route;
    await tester.pumpWidget(
      await _wrap(
        RecommendationsPage(
          api: _api(),
          loader: () async => _recommendations(status: 'partial_ready'),
          onNavigate: (value) => route = value,
        ),
        dark: true,
        localeCode: 'fr',
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Les revenus de ce produit diminuent'), findsOneWidget);
    expect(find.textContaining('Coffee : 50.0 contre 200.0'), findsOneWidget);
    expect(find.textContaining('Priorité: high'), findsOneWidget);
    await tester.tap(find.byIcon(Icons.arrow_forward));
    expect(route, '/products');
  });

  testWidgets('Recommendations shows processing, empty and retry states', (tester) async {
    var calls = 0;
    await tester.pumpWidget(
      await _wrap(
        RecommendationsPage(
          api: _api(),
          loader: () async {
            calls += 1;
            if (calls == 1) throw StateError('private');
            return _recommendations(status: 'processing', empty: true);
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Analyzing'), findsOneWidget);

    await tester.pumpWidget(
      await _wrap(RecommendationsPage(key: const ValueKey('empty'), api: _api(), loader: () async => _recommendations(empty: true))),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('No evidence-backed'), findsOneWidget);
  });
}
