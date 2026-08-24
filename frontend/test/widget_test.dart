import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:avenqo/app/destinations.dart';
import 'package:avenqo/app/avenqo_app.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/token_store.dart';
import 'package:avenqo/pages/assistant_page.dart';
import 'package:avenqo/pages/dashboard_page.dart';
import 'package:avenqo/i18n/locale_controller.dart';
import 'package:avenqo/i18n/locale_scope.dart';

class MemoryLocalePreferenceStore implements LocalePreferenceStore {
  MemoryLocalePreferenceStore([this._code]);
  String? _code;
  @override
  Future<String?> read() async => _code;
  @override
  Future<void> write(String code) async => _code = code;
}

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

/// Échoue immédiatement au lieu de tenter une vraie requête réseau en test.
class _UnreachableHttpClient extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) {
    throw Exception('no network in tests');
  }
}

void main() {
  testWidgets('Avenqo affiche l’accueil public', (WidgetTester tester) async {
    final auth = AuthController(
      ApiClient(tokenStore: MemoryTokenStore(), httpClient: _UnreachableHttpClient()),
    );
    final locale = LocaleController(store: MemoryLocalePreferenceStore());
    await auth.initialize();
    await locale.initialize();

    await tester.pumpWidget(AvenqoApp(auth: auth, locale: locale));
    await tester.pumpAndSettle();

    expect(find.text('Avenqo'), findsWidgets);
    expect(find.text('Essayer gratuitement'), findsWidgets);

    // Démonte explicitement l'arbre (GoRouter/refreshListenable inclus) avant
    // la fin du test pour éviter toute fuite d'état vers le test suivant.
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
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
    final auth = AuthController(
      ApiClient(tokenStore: MemoryTokenStore(), httpClient: _UnreachableHttpClient()),
    );
    await auth.initialize();
    final locale = LocaleController(store: MemoryLocalePreferenceStore('fr'));
    await locale.initialize();

    await tester.pumpWidget(
      MaterialApp(
        home: AvenqoLocaleScope(
          controller: locale,
          child: DashboardPage(
            auth: auth,
            // Charge instantanément, sans passer par ApiClient/http : élimine
            // toute opération réseau réelle ou en attente pendant le test.
            loader: (_) async =>
                const DashboardData(hasReadyDataset: false, planCode: null),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Ce mois-ci'), findsNothing);
    expect(find.text('Connecter mes données'), findsOneWidget);
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
