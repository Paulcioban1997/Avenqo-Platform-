import 'dart:convert';

import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/token_store.dart';
import 'package:avenqo/features/admin/admin_ai_usage_page.dart';
import 'package:avenqo/i18n/locale_controller.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/pages/billing_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:intl/date_symbol_data_local.dart';

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

ApiClient _api(http.Client client) => ApiClient(
      tokenStore: _TokenStore(),
      httpClient: client,
      baseUrl: 'https://avenqo.test/api/v1',
    );

Future<Widget> _wrap(Widget child, {bool dark = false}) async {
  await initializeDateFormatting('en');
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

BillingData _billingData({String status = 'active', bool enterprise = false}) => BillingData(
      subscription: {
        'plan_code': enterprise ? 'enterprise' : 'professional',
        'status': status,
        'cancel_at_period_end': false,
        'current_period_end': '2026-09-30T00:00:00Z',
      },
      invoices: const [],
      balance: {
        'billing_period': '2026-08',
        'monthly_included': enterprise ? null : 25000,
        'monthly_used': 2500,
        'monthly_remaining': enterprise ? null : 22500,
        'purchased_remaining': 25000,
        'total_remaining': enterprise ? null : 47500,
      },
      packs: const [
        {'code': 'professional_extra', 'credits': 25000, 'price_usd': 25},
      ],
    );

void main() {
  testWidgets('client sees credit balance and opens tenant-derived Stripe checkout', (tester) async {
    Uri? launched;
    Uri? requested;
    Map<String, dynamic>? requestBody;
    final api = _api(MockClient((request) async {
      requested = request.url;
      requestBody = jsonDecode(request.body) as Map<String, dynamic>;
      return http.Response('{"url":"https://checkout.stripe.test/credits"}', 200);
    }));

    await tester.pumpWidget(await _wrap(BillingPage(
      api: api,
      loader: (_) async => _billingData(),
      launcher: (uri) async {
        launched = uri;
        return true;
      },
    )));
    await tester.pumpAndSettle();

    expect(find.text('AI credits'), findsOneWidget);
    expect(find.text('25,000'), findsNWidgets(2));
    expect(find.text('47,500'), findsOneWidget);
    expect(find.textContaining('Next renewal:'), findsOneWidget);
    expect(find.byType(LinearProgressIndicator), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text(r'$25 USD'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text(r'$25 USD'), findsOneWidget);

    await tester.scrollUntilVisible(
      find.text('Purchase').first,
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -80));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Purchase').first);
    await tester.pumpAndSettle();
    expect(requested?.path, '/api/v1/billing/credit-packs/checkout');
    expect(requested.toString(), isNot(contains('company')));
    expect(requestBody, {'pack_code': 'professional_extra'});
    expect(launched, Uri.parse('https://checkout.stripe.test/credits'));
  });

  testWidgets('active customer confirms period-end cancellation', (tester) async {
    Uri? requested;
    final api = _api(MockClient((request) async {
      requested = request.url;
      return http.Response(
        '{"plan_code":"professional","status":"canceling_at_period_end",'
        '"cancel_at_period_end":true,"current_period_end":"2026-09-30T00:00:00Z"}',
        200,
      );
    }));

    await tester.pumpWidget(await _wrap(BillingPage(
      api: api,
      loader: (_) async => _billingData(),
    )));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cancel subscription'));
    await tester.pumpAndSettle();
    expect(find.text('Cancel subscription?'), findsOneWidget);
    await tester.tap(find.text('Schedule cancellation'));
    await tester.pumpAndSettle();

    expect(requested?.path, '/api/v1/billing/cancel');
  });

  testWidgets('inactive Enterprise client sees contractual allowance and disabled packs on mobile dark mode', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(await _wrap(BillingPage(
      api: _api(MockClient((_) async => http.Response('{}', 200))),
      loader: (_) async => _billingData(status: 'inactive', enterprise: true),
    ), dark: true));
    await tester.pumpAndSettle();

    expect(find.text('Contractual / custom'), findsNWidgets(3));
    expect(find.byType(LinearProgressIndicator), findsNothing);
    await tester.scrollUntilVisible(
      find.textContaining('active or trialing subscription'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.textContaining('active or trialing subscription'), findsOneWidget);
    final purchaseButton = tester.widget<FilledButton>(
      find.ancestor(of: find.text('Purchase').first, matching: find.byType(FilledButton)),
    );
    expect(purchaseButton.onPressed, isNull);
    expect(tester.takeException(), isNull);
  });

  testWidgets('platform admin sees reliable company credit fields in desktop table', (tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final companies = [{
      'id': 'company-acme',
      'name': 'Acme Canada',
      'plan_code': 'professional',
      'subscription_status': 'active',
      'monthly_credits': 10000,
      'monthly_credits_remaining': 7500,
      'purchased_credits_remaining': 5000,
      'total_credits_remaining': 12500,
      'ai_requests_current_period': 2500,
    }];

    await tester.pumpWidget(await _wrap(AdminAiUsagePage(
      api: _api(MockClient((_) async => http.Response('[]', 200))),
      loader: (_) async => companies,
    )));
    await tester.pumpAndSettle();

    expect(find.byType(DataTable), findsOneWidget);
    expect(find.text('Acme Canada'), findsOneWidget);
    expect(find.text('12,500'), findsOneWidget);
    expect(find.text('Active'), findsOneWidget);
    await tester.drag(find.byType(SingleChildScrollView), const Offset(-1200, 0));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.receipt_long_outlined));
    await tester.pumpAndSettle();
    expect(find.text('No invoices yet.'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('platform admin company credits remain readable on mobile', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(await _wrap(AdminAiUsagePage(
      api: _api(MockClient((_) async => http.Response('[]', 200))),
      loader: (_) async => [{
        'name': 'Enterprise North',
        'plan_code': 'enterprise',
        'subscription_status': 'trialing',
        'monthly_credits': null,
        'monthly_credits_remaining': null,
        'purchased_credits_remaining': 150000,
        'total_credits_remaining': null,
        'ai_requests_current_period': 720,
      }],
    ), dark: true));
    await tester.pumpAndSettle();

    expect(find.byType(DataTable), findsNothing);
    expect(find.text('Enterprise North'), findsOneWidget);
    expect(find.text('Contractual / custom'), findsNWidgets(3));
    expect(find.text('Trialing'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}