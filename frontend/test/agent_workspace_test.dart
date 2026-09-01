import 'package:avenqo/agents/agent_registry.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/token_store.dart';
import 'package:avenqo/features/admin/admin_agents_page.dart';
import 'package:avenqo/i18n/locale_controller.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/pages/agents_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _LocaleStore implements LocalePreferenceStore {
  @override
  Future<String?> read() async => 'en';
  @override
  Future<void> write(String code) async {}
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
  testWidgets('client catalog opens the existing Retail route only', (tester) async {
    AvenqoAgentDefinition? opened;
    tester.view.physicalSize = const Size(1400, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(await _wrap(AgentsPage(onOpenAgent: (agent) => opened = agent)));
    await tester.pumpAndSettle();

    expect(find.text('Retail Intelligence'), findsOneWidget);
    expect(find.text('Available now'), findsOneWidget);
    expect(find.text('Coming soon'), findsNWidgets(10));
    expect(find.text('Discover'), findsOneWidget);

    await tester.tap(find.text('Discover'));
    expect(opened?.id, 'retail');
    expect(opened?.route, '/dashboard');
    expect(tester.takeException(), isNull);
  });

  testWidgets('client catalog supports mobile dark theme and long card content', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(await _wrap(const AgentsPage(), dark: true));
    await tester.pumpAndSettle();

    expect(find.text('Appointments AI'), findsOneWidget);
    expect(find.text('Workflow Automation'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('admin catalog reports availability without tenant operational data', (tester) async {
    tester.view.physicalSize = const Size(1200, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(await _wrap(const AdminAgentsPage()));
    await tester.pumpAndSettle();

    expect(find.text('Agent Catalog'), findsOneWidget);
    expect(find.text('Available agents'), findsOneWidget);
    expect(find.text('Coming Soon agents'), findsOneWidget);
    expect(find.text('Retail Intelligence'), findsOneWidget);
    expect(find.text('Discover'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}