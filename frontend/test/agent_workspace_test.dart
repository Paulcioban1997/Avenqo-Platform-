import 'package:avenqo/agents/agent_registry.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/core/token_store.dart';
import 'package:avenqo/features/admin/admin_agents_page.dart';
import 'package:avenqo/features/admin/admin_retail_agent_page.dart';
import 'package:avenqo/i18n/locale_controller.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/pages/agents_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:avenqo/core/api_client.dart';

class _LocaleStore implements LocalePreferenceStore {
  @override
  Future<String?> read() async => 'en';
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

void main() {
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
      expect(tester.takeException(), isNull);
    },
  );
}
