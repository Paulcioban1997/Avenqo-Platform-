import 'dart:async';

import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/token_store.dart';
import 'package:avenqo/i18n/locale_controller.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/pages/dashboard_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/testing.dart';
import 'package:http/http.dart' as http;


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
  Future<String?> read() async => 'en';
  @override
  Future<void> write(String code) async {}
}


AuthController _auth() => AuthController(
      ApiClient(
        tokenStore: _TokenStore(),
        httpClient: MockClient((_) async => http.Response('{}', 200)),
        baseUrl: 'https://avenqo.test/api/v1',
      ),
    );


Future<Widget> _wrap(Widget child, {bool dark = false}) async {
  final locale = LocaleController(store: _LocaleStore());
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


const _empty = DashboardData(
  status: 'no_data',
  planCode: 'professional',
  currency: 'CAD',
  kpis: [],
  priorities: [],
  connections: {'total': 0},
  recentActivity: [],
);


void main() {
  testWidgets('shows loading then premium no-data state', (tester) async {
    final completer = Completer<DashboardData>();
    await tester.pumpWidget(
      await _wrap(DashboardPage(auth: _auth(), loader: (_) => completer.future)),
    );
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    completer.complete(_empty);
    await tester.pumpAndSettle();
    expect(find.text('Connect data'), findsOneWidget);
    expect(find.text('Revenue'), findsNothing);
  });

  testWidgets('shows the real processing state without claiming training', (tester) async {
    const processing = DashboardData(
      status: 'processing',
      planCode: 'demo',
      currency: 'USD',
      kpis: [],
      priorities: [],
      connections: {'total': 1, 'analyzing': 1},
      recentActivity: [],
    );
    await tester.pumpWidget(
      await _wrap(DashboardPage(auth: _auth(), loader: (_) async => processing)),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('Analyzing'), findsWidgets);
    expect(find.textContaining('Training AI'), findsNothing);
  });

  testWidgets('renders partial-ready KPIs, currency, priority and activity in dark mode', (tester) async {
    const ready = DashboardData(
      status: 'partial_ready',
      planCode: 'professional',
      currency: 'CAD',
      kpis: [
        {'key': 'revenue', 'value': 150.0, 'currency': 'CAD', 'change_percent': 25.0, 'available': true},
        {'key': 'orders', 'value': 2, 'available': true},
        {'key': 'customers', 'value': 2, 'available': true},
        {'key': 'average_order_value', 'value': null, 'available': false},
      ],
      priorities: [
        {'title': 'revenue_growth', 'source_capability': 'revenue'},
      ],
      connections: {'total': 2, 'ready': 1, 'training_ai': 1},
      recentActivity: [
        {'kind': 'dataset_imported', 'title': 'sales.csv', 'occurred_at': '2026-08-28T00:00:00Z'},
      ],
    );
    await tester.pumpWidget(
      await _wrap(DashboardPage(auth: _auth(), loader: (_) async => ready), dark: true),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('150'), findsOneWidget);
    expect(find.text('+25.0%'), findsOneWidget);
    expect(find.text('2'), findsNWidgets(2));
    expect(find.text('—'), findsWidgets);
    await tester.scrollUntilVisible(
      find.text('Build on recent revenue growth'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Build on recent revenue growth'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.textContaining('sales.csv'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.textContaining('sales.csv'), findsOneWidget);
    expect(find.textContaining('Training AI'), findsOneWidget);
  });

  testWidgets('shows a retryable error and retries the loader', (tester) async {
    var calls = 0;
    Future<DashboardData> loader(AuthController _) async {
      calls += 1;
      if (calls == 1) throw StateError('internal detail');
      return _empty;
    }

    await tester.pumpWidget(
      await _wrap(DashboardPage(auth: _auth(), loader: loader)),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('internal detail'), findsNothing);
    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();
    expect(calls, 2);
    expect(find.text('Connect data'), findsOneWidget);
  });
}