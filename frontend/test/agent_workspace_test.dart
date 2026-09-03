import 'package:avenqo/agents/agent_registry.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/core/token_store.dart';
import 'package:avenqo/features/admin/admin_agents_page.dart';
import 'package:avenqo/features/admin/admin_company_detail_page.dart';
import 'package:avenqo/features/admin/admin_retail_agent_page.dart';
import 'package:avenqo/i18n/locale_controller.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/pages/agents_page.dart';
import 'package:avenqo/pages/customers_page.dart';
import 'package:avenqo/pages/dashboard_page.dart';
import 'package:avenqo/pages/products_page.dart';
import 'package:avenqo/pages/recommendations_page.dart';
import 'package:avenqo/pages/sales_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:avenqo/core/api_client.dart';

class _LocaleStore implements LocalePreferenceStore {
  _LocaleStore([this.code = 'en']);

  final String code;

  @override
  Future<String?> read() async => code;
  @override
  Future<void> write(String code) async {}
}

class _TokenStore implements TokenStore {
  @override
  Future<void> clear() async {}
  @override
  Future<String?> readAccessToken() async => 'access';
  @override
  Future<String?> readRefreshToken() async => 'refresh';
  @override
  Future<void> writeTokens(String accessToken, String refreshToken) async {}
}

Future<Widget> _wrap(
  Widget child, {
  bool dark = false,
  String localeCode = 'en',
}) async {
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

Future<(Widget, GoRouter)> _adminRetailRouter(
  ApiClient api, {
  String initialLocation = '/admin/agents/retail',
}) async {
  final locale = LocaleController(store: _LocaleStore());
  await locale.initialize();
  final auth = AuthController(api);
  final router = GoRouter(
    initialLocation: initialLocation,
    routes: [
      GoRoute(
        path: '/admin/agents/retail',
        builder: (context, state) => Scaffold(
          body: AdminRetailAgentPage(
            api: api,
            auth: auth,
            selectedCompanyId: state.uri.queryParameters['company'],
          ),
        ),
      ),
      GoRoute(
        path: '/admin/agents',
        builder: (_, _) => const Scaffold(body: Text('Admin agents')),
      ),
    ],
  );
  return (
    AvenqoLocaleScope(
      controller: locale,
      child: MaterialApp.router(
        theme: ThemeData(extensions: [AvenqoColors.light]),
        routerConfig: router,
      ),
    ),
    router,
  );
}

void main() {
  testWidgets('admin company detail displays module entitlement summary', (
    tester,
  ) async {
    final api = ApiClient(
      tokenStore: _TokenStore(),
      httpClient: MockClient((_) async => http.Response('''{
        "name":"Example Inc.",
        "country":"CA",
        "joined_at":"2026-01-01T00:00:00Z",
        "plan_code":"professional",
        "subscription_status":"active",
        "active_module_count":1,
        "module_limit":2,
        "remaining_module_slots":1,
        "active_modules":["Retail Intelligence"]
      }''', 200)),
      baseUrl: 'https://avenqo.test/api/v1',
    );
    await api.initialize();

    await tester.pumpWidget(await _wrap(
      AdminCompanyDetailPage(api: api, companyId: 'company-1'),
    ));
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.text('Agent Catalog'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Agent Catalog'), findsOneWidget);
    expect(find.text('1 / 2 (1)'), findsOneWidget);
    expect(find.text('Retail Intelligence'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('client catalog uses backend entitlement states and toggles modules', (
    tester,
  ) async {
    Uri? actionUri;
    final response = '''{
      "company_id":"00000000-0000-0000-0000-000000000001",
      "plan_code":"demo",
      "active_modules":["retail"],
      "module_limit":2,
      "remaining_module_slots":1,
      "modules":[
        {"key":"retail","state":"active"},
        {"key":"crm","state":"coming_soon"}
      ]
    }''';
    final api = ApiClient(
      tokenStore: _TokenStore(),
      httpClient: MockClient((request) async {
        if (request.method == 'POST') actionUri = request.url;
        return http.Response(response, 200);
      }),
      baseUrl: 'https://avenqo.test/api/v1',
    );
    await api.initialize();

    await tester.pumpWidget(await _wrap(AgentsPage(api: api)));
    await tester.pumpAndSettle();

    expect(find.text('1 / 2'), findsOneWidget);
    expect(find.text('Active'), findsOneWidget);
    expect(find.text('Discover'), findsOneWidget);
    expect(find.byType(Switch), findsNWidgets(2));
    expect(tester.widget<Switch>(find.byType(Switch).at(1)).onChanged, isNull);

    await tester.tap(find.byType(Switch).first);
    await tester.pumpAndSettle();
    expect(actionUri?.path, '/api/v1/modules/retail/deactivate');
    expect(actionUri.toString(), isNot(contains('company')));
    expect(tester.takeException(), isNull);
  });

  testWidgets('client catalog opens the existing Retail route only', (
    tester,
  ) async {
    AvenqoAgentDefinition? opened;
    tester.view.physicalSize = const Size(1400, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      await _wrap(AgentsPage(onOpenAgent: (agent) => opened = agent)),
    );
    await tester.pumpAndSettle();

    expect(find.text('Retail Intelligence'), findsOneWidget);
    expect(find.text('Available now'), findsOneWidget);
    expect(find.text('Coming soon'), findsNWidgets(10));
    expect(find.text('Discover'), findsOneWidget);

    await tester.tap(find.text('Discover'));
    expect(opened?.id, 'retail');
    expect(opened?.route, '/retail');
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'client catalog supports mobile dark theme and long card content',
    (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(await _wrap(const AgentsPage(), dark: true));
      await tester.pumpAndSettle();

      expect(find.text('Appointments AI'), findsOneWidget);
      expect(find.text('Workflow Automation'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('admin catalog exposes only the available Retail action', (
    tester,
  ) async {
    AvenqoAgentDefinition? opened;
    tester.view.physicalSize = const Size(1200, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      await _wrap(AdminAgentsPage(onOpenAgent: (agent) => opened = agent)),
    );
    await tester.pumpAndSettle();

    expect(find.text('Agent Catalog'), findsOneWidget);
    expect(find.text('Available agents'), findsOneWidget);
    expect(find.text('Coming Soon agents'), findsOneWidget);
    expect(find.text('Retail Intelligence'), findsOneWidget);
    expect(find.text('Discover'), findsOneWidget);
    await tester.tap(find.text('Discover'));
    expect(opened?.id, 'retail');
    expect(tester.takeException(), isNull);
  });

  testWidgets('admin Retail selection calls only the admin company directory', (
    tester,
  ) async {
    final requestedPaths = <String>[];
    final api = ApiClient(
      tokenStore: _TokenStore(),
      baseUrl: 'https://avenqo.test/api/v1',
      httpClient: MockClient((request) async {
        requestedPaths.add(request.url.path);
        return http.Response(
          '[{"id":"company-1","name":"North Shop","plan_code":"pro"}]',
          200,
        );
      }),
    );
    await api.initialize();

    await tester.pumpWidget(await _wrap(AdminRetailAgentPage(api: api)));
    await tester.pumpAndSettle();

    expect(find.text('North Shop'), findsOneWidget);
    expect(requestedPaths, ['/api/v1/admin/companies']);
    expect(
      requestedPaths.where(
        (path) => RegExp(
          r'/(sales|customers|products|recommendations)',
        ).hasMatch(path),
      ),
      isEmpty,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('admin company directory request carries the access token', (
    tester,
  ) async {
    String? authorization;
    final api = ApiClient(
      tokenStore: _TokenStore(),
      baseUrl: 'https://avenqo.test/api/v1',
      httpClient: MockClient((request) async {
        authorization = request.headers['authorization'];
        return http.Response('[]', 200);
      }),
    );
    await api.initialize();

    await tester.pumpWidget(await _wrap(AdminRetailAgentPage(api: api)));
    await tester.pumpAndSettle();

    expect(authorization, 'Bearer access');
    expect(find.text('No companies available.'), findsOneWidget);
  });

  for (final scenario in [
    (
      status: 403,
      message: 'You are not authorized to access the company directory.',
    ),
    (
      status: 503,
      message:
          'The company directory is temporarily unavailable. Try again later.',
    ),
  ]) {
    testWidgets(
      'admin company directory shows the ${scenario.status} flow message',
      (tester) async {
        final api = ApiClient(
          tokenStore: _TokenStore(),
          baseUrl: 'https://avenqo.test/api/v1',
          httpClient: MockClient(
            (_) async =>
                http.Response('{"detail":"request failed"}', scenario.status),
          ),
        );
        await api.initialize();

        await tester.pumpWidget(await _wrap(AdminRetailAgentPage(api: api)));
        await tester.pumpAndSettle();

        expect(find.text(scenario.message), findsOneWidget);
        expect(tester.takeException(), isNull);
      },
    );
  }

  testWidgets(
    'selected admin tenant is validated before its Retail data loads',
    (tester) async {
      tester.view.physicalSize = const Size(1400, 1000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final requests = <String>[];
      final api = ApiClient(
        tokenStore: _TokenStore(),
        baseUrl: 'https://avenqo.test/api/v1',
        httpClient: MockClient((request) async {
          requests.add('${request.method} ${request.url.path}');
          if (request.method == 'POST') {
            return http.Response(
              '{"company_id":"company-1","company_name":"North Shop"}',
              200,
            );
          }
          return http.Response('{}', 200);
        }),
      );
      await api.initialize();

      await tester.pumpWidget(
        await _wrap(
          AdminRetailAgentPage(
            api: api,
            auth: AuthController(api),
            selectedCompanyId: 'company-1',
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        requests.first,
        'POST /api/v1/admin/companies/company-1/retail/context',
      );
      expect(
        requests[1],
        'GET /api/v1/admin/companies/company-1/retail/dashboard',
      );
      expect(find.text('Admin view — Company: North Shop'), findsOneWidget);
      expect(find.text('Switch company'), findsOneWidget);
      expect(find.text('Exit tenant view'), findsOneWidget);

      await tester.tap(find.text('Sales').last);
      await tester.pumpAndSettle();
      expect(
        requests.last,
        'GET /api/v1/admin/companies/company-1/retail/sales/summary',
      );
      expect(
        requests.where((request) => request.contains('/sales/summary')),
        hasLength(1),
      );
      expect(tester.widget<SalesPage>(find.byType(SalesPage)).readOnly, isTrue);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('French admin Retail banner names the selected company', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1400, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final api = ApiClient(
      tokenStore: _TokenStore(),
      baseUrl: 'https://avenqo.test/api/v1',
      httpClient: MockClient((request) async {
        if (request.method == 'POST') {
          return http.Response(
            '{"company_id":"11111111-1111-4111-8111-111111111111",'
            '"company_name":"Boutique Nord"}',
            200,
          );
        }
        return http.Response('{}', 200);
      }),
    );
    await api.initialize();

    await tester.pumpWidget(
      await _wrap(
        AdminRetailAgentPage(
          api: api,
          auth: AuthController(api),
          selectedCompanyId: '11111111-1111-4111-8111-111111111111',
        ),
        localeCode: 'fr-CA',
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.text('Vue administrateur — Société : Boutique Nord'),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('deleted admin company context is cleared back to selector', (
    tester,
  ) async {
    const deletedId = '11111111-1111-4111-8111-111111111111';
    final requests = <String>[];
    final api = ApiClient(
      tokenStore: _TokenStore(),
      baseUrl: 'https://avenqo.test/api/v1',
      httpClient: MockClient((request) async {
        requests.add('${request.method} ${request.url.path}');
        if (request.method == 'POST') {
          return http.Response('{"detail":"Company not found"}', 404);
        }
        return http.Response(
          '[{"id":"22222222-2222-4222-8222-222222222222","name":"South Shop","plan_code":"pro"}]',
          200,
        );
      }),
    );
    await api.initialize();
    final (app, router) = await _adminRetailRouter(
      api,
      initialLocation: '/admin/agents/retail?company=$deletedId',
    );

    await tester.pumpWidget(app);
    await tester.pumpAndSettle();

    expect(requests.first, contains('/companies/$deletedId/retail/context'));
    expect(requests.last, 'GET /api/v1/admin/companies');
    expect(find.text('South Shop'), findsOneWidget);
    expect(
      find.text('The tenant context could not be validated.'),
      findsNothing,
    );
    expect(router.routeInformationProvider.value.uri.queryParameters, isEmpty);
    expect(tester.takeException(), isNull);
  });

  testWidgets('switching companies clears old data and opens the new context', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1400, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    const northId = '11111111-1111-4111-8111-111111111111';
    const southId = '22222222-2222-4222-8222-222222222222';
    final requests = <String>[];
    final api = ApiClient(
      tokenStore: _TokenStore(),
      baseUrl: 'https://avenqo.test/api/v1',
      httpClient: MockClient((request) async {
        requests.add('${request.method} ${request.url.path}');
        if (request.url.path.endsWith('/context/exit')) {
          return http.Response('{"detail":"audit unavailable"}', 500);
        }
        if (request.method == 'POST') {
          final id = request.url.path.contains(southId) ? southId : northId;
          final name = id == southId ? 'South Shop' : 'North Shop';
          return http.Response(
            '{"company_id":"$id","company_name":"$name"}',
            200,
          );
        }
        if (request.url.path.endsWith('/admin/companies')) {
          return http.Response(
            '[{"id":"$southId","name":"South Shop","plan_code":"pro"}]',
            200,
          );
        }
        return http.Response('{}', 200);
      }),
    );
    await api.initialize();
    final (app, _) = await _adminRetailRouter(
      api,
      initialLocation: '/admin/agents/retail?company=$northId',
    );

    await tester.pumpWidget(app);
    await tester.pumpAndSettle();
    expect(
      tester.widget<DashboardPage>(find.byType(DashboardPage)).readOnly,
      isTrue,
    );

    await tester.tap(find.text('Switch company'));
    await tester.pumpAndSettle();
    expect(find.text('South Shop'), findsOneWidget);

    await tester.tap(find.text('South Shop'));
    await tester.pumpAndSettle();
    expect(find.text('Admin view — Company: South Shop'), findsOneWidget);
    final southContextIndex = requests.indexWhere(
      (request) =>
          request == 'POST /api/v1/admin/companies/$southId/retail/context',
    );
    expect(southContextIndex, greaterThanOrEqualTo(0));
    expect(
      requests
          .skip(southContextIndex)
          .where(
            (request) =>
                request.contains('/companies/$northId/retail/') &&
                !request.endsWith('/context/exit'),
          ),
      isEmpty,
    );

    await tester.tap(find.text('Customers').last);
    await tester.pumpAndSettle();
    expect(
      tester.widget<CustomersPage>(find.byType(CustomersPage)).readOnly,
      isTrue,
    );
    await tester.tap(find.text('Products').last);
    await tester.pumpAndSettle();
    expect(
      tester.widget<ProductsPage>(find.byType(ProductsPage)).readOnly,
      isTrue,
    );
    await tester.tap(find.text('Recommendations').last);
    await tester.pumpAndSettle();
    expect(find.byType(RecommendationsPage), findsOneWidget);
    expect(
      requests.last,
      'GET /api/v1/admin/companies/$southId/retail/recommendations',
    );
    expect(tester.takeException(), isNull);
  });
}
