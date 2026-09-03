import 'dart:convert';

import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/token_store.dart';
import 'package:avenqo/features/ai_chat/central_ai_controller.dart';
import 'package:avenqo/i18n/locale_controller.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/widgets/floating_central_ai.dart';
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
  Future<String?> read() async => 'en';
  @override
  Future<void> write(String code) async {}
}

void main() {
  testWidgets('floating launcher reuses Central AI state and forwards only page context', (tester) async {
    Map<String, dynamic>? sentBody;
    final client = MockClient((request) async {
      if (request.method == 'GET') return http.Response('[]', 200);
      if (request.url.path.endsWith('/conversations')) {
        return http.Response(
          '{"id":"chat-1","title":"Sales","created_at":"2026-09-03T12:00:00Z","updated_at":"2026-09-03T12:00:00Z"}',
          201,
        );
      }
      sentBody = jsonDecode(request.body) as Map<String, dynamic>;
      return http.Response(
        '{"selected_agent":"retail","status":"success","answer":"Retail answer","remaining_ai_credits":9,"agent_availability":"available","conversation_id":"chat-1"}',
        200,
      );
    });
    final api = ApiClient(
      tokenStore: _TokenStore(),
      httpClient: client,
      baseUrl: 'https://avenqo.test/api/v1',
    );
    final centralAI = CentralAIController(api);
    addTearDown(centralAI.dispose);
    final locale = LocaleController(store: _LocaleStore());
    await locale.initialize();

    await tester.pumpWidget(
      AvenqoLocaleScope(
        controller: locale,
        child: MaterialApp(
          home: Scaffold(
            body: FloatingCentralAI(
              api: api,
              controller: centralAI,
              currentPath: '/retail/products',
              onOpenFull: () {},
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.byType(FloatingActionButton));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'How are products performing?');
    await tester.tap(find.byIcon(Icons.arrow_upward));
    await tester.pumpAndSettle();

    expect(find.text('Retail answer'), findsOneWidget);
    expect(sentBody, {
      'content': 'How are products performing?',
      'page_context': '/retail/products',
      'locale': 'en',
    });

    await tester.tap(find.byIcon(Icons.close));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(FloatingActionButton));
    await tester.pumpAndSettle();

    expect(find.text('Retail answer'), findsOneWidget);
    expect(centralAI.selected?.id, 'chat-1');
  });
}