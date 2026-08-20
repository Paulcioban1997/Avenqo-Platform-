import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';
import 'package:avenqo/app/destinations.dart';
import 'package:avenqo/app/avenqo_app.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/token_store.dart';
import 'package:avenqo/pages/assistant_page.dart';
import 'package:avenqo/pages/dashboard_page.dart';
import 'package:avenqo/i18n/locale_controller.dart';

class MemoryTokenStore implements TokenStore {
  String? accessToken;
  String? refreshToken;

  @override
  Future<void> clear() async {
    accessToken = null;
    refreshToken = null;
  }

  @override
  Future<String?> readAccessToken() async => accessToken;

  @override
  Future<String?> readRefreshToken() async => refreshToken;

  @override
  Future<void> writeTokens(String accessToken, String refreshToken) async {
    this.accessToken = accessToken;
    this.refreshToken = refreshToken;
  }
}

void main() {
  testWidgets('Avenqo affiche l’accueil public', (WidgetTester tester) async {
    final auth = AuthController(ApiClient(tokenStore: MemoryTokenStore()));
    final locale = LocaleController();
    await auth.initialize();
    await locale.initialize();

    await tester.pumpWidget(AvenqoApp(auth: auth, locale: locale));
    await tester.pumpAndSettle();

    expect(find.text('Avenqo'), findsWidgets);
    expect(find.text('Essayer gratuitement'), findsWidgets);
  });

  test('la navigation client utilise uniquement le langage métier', () {
    final content = appDestinations
        .map((destination) => '${destination.label} ${destination.description}')
        .join(' ')
        .toLowerCase();
    const forbidden = [
      'dataset',
      'gridsearch',
      'pipeline',
      'accuracy',
      'roc auc',
      'confusion matrix',
      'feature importance',
      'shap',
      'notebook',
      'sklearn',
      'ai engine',
      'artefact',
    ];

    expect(appDestinations.map((item) => item.label), containsAll([
      'Vue d’ensemble',
      'AI Assistant',
      'Ventes',
      'Clients',
      'Produits',
      'Rapports',
    ]));
    for (final word in forbidden) {
      expect(content, isNot(contains(word)));
    }
  });

  testWidgets('le dirigeant voit une vue métier', (tester) async {
    tester.view.physicalSize = const Size(1400, 1000);
    addTearDown(tester.view.resetPhysicalSize);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetDevicePixelRatio);
    final auth = AuthController(ApiClient(tokenStore: MemoryTokenStore()));
    await auth.initialize();

    await tester.pumpWidget(MaterialApp(home: DashboardPage(auth: auth)));
    expect(find.text('Ce mois-ci'), findsOneWidget);
    expect(find.text('Chiffre d’affaires'), findsOneWidget);
    expect(find.text('Connecter mes ventes'), findsOneWidget);
    expect(find.textContaining('AI Engine'), findsNothing);
  });

  testWidgets('le dirigeant peut interroger son assistant', (tester) async {
    tester.view.physicalSize = const Size(1400, 1000);
    addTearDown(tester.view.resetPhysicalSize);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetDevicePixelRatio);
    final auth = AuthController(ApiClient(tokenStore: MemoryTokenStore()));
    await auth.initialize();

    await tester.pumpWidget(MaterialApp(home: Scaffold(body: AssistantPage(api: auth.api))));
    expect(find.text('Ask Avenqo about your business'), findsOneWidget);
    expect(find.text('How are my sales performing?'), findsOneWidget);
  });
}
