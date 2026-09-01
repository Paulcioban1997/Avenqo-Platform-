import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/token_store.dart';
import 'package:avenqo/pages/assistant_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class TestTokenStore implements TokenStore {
  @override
  Future<void> clear() async {}
  @override
  Future<String?> readAccessToken() async => null;
  @override
  Future<String?> readRefreshToken() async => null;
  @override
  Future<void> writeTokens(String accessToken, String refreshToken) async {}
}

ApiClient chatApi(http.Client client) => ApiClient(
      tokenStore: TestTokenStore(),
      httpClient: client,
      baseUrl: 'https://avenqo.test/api/v1',
    );

void main() {
  testWidgets('renders the empty business chat state', (tester) async {
    final client = MockClient((request) async => http.Response('[]', 200));
    await tester.pumpWidget(MaterialApp(home: AssistantPage(api: chatApi(client))));
    await tester.pumpAndSettle();

    expect(find.text('Ask Avenqo about your business'), findsOneWidget);
    expect(find.text('Connect your business data'), findsOneWidget);
  });

  testWidgets('creates a conversation and renders Central AI response', (tester) async {
    final client = MockClient((request) async {
      if (request.method == 'GET') return http.Response('[]', 200);
      if (request.url.path.endsWith('/conversations')) {
        return http.Response('{"id":"chat-1","title":"Sales","created_at":"2026-08-18T12:00:00Z","updated_at":"2026-08-18T12:00:00Z"}', 201);
      }
      if (request.url.path.endsWith('/messages')) {
        return http.Response(
          '{"selected_agent":"retail","status":"success","answer":"Sales improved this month.","remaining_ai_credits":4999,"agent_availability":"available","conversation_id":"chat-1"}',
          200,
        );
      }
      return http.Response('{}', 404);
    });
    await tester.pumpWidget(MaterialApp(home: AssistantPage(api: chatApi(client))));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), 'How are sales?');
    await tester.tap(find.byTooltip('Send message'));
    await tester.pumpAndSettle();

    expect(find.text('How are sales?'), findsOneWidget);
    expect(find.text('Sales improved this month.'), findsOneWidget);
    expect(find.text('AI credits remaining: 4999'), findsOneWidget);
  });

  testWidgets('renders structured Coming Soon response', (tester) async {
    final client = MockClient((request) async {
      if (request.method == 'GET') return http.Response('[]', 200);
      if (request.url.path.endsWith('/conversations')) {
        return http.Response('{"id":"chat-2","title":"CRM","created_at":"2026-08-18T12:00:00Z","updated_at":"2026-08-18T12:00:00Z"}', 201);
      }
      return http.Response(
        '{"selected_agent":"crm","status":"agent_unavailable","answer":null,"remaining_ai_credits":5000,"agent_availability":"coming_soon","conversation_id":"chat-2"}',
        200,
      );
    });
    await tester.pumpWidget(MaterialApp(home: AssistantPage(api: chatApi(client))));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), 'Prioritize my CRM leads');
    await tester.tap(find.byTooltip('Send message'));
    await tester.pumpAndSettle();

    expect(find.text('This specialist is Coming Soon.'), findsOneWidget);
  });

  testWidgets('offers credit management when AI credits are exhausted', (tester) async {
    final client = MockClient((request) async {
      if (request.method == 'GET') return http.Response('[]', 200);
      if (request.url.path.endsWith('/conversations')) {
        return http.Response('{"id":"chat-3","title":"Sales","created_at":"2026-08-18T12:00:00Z","updated_at":"2026-08-18T12:00:00Z"}', 201);
      }
      return http.Response(
        '{"selected_agent":"retail","status":"credits_exhausted","answer":null,"remaining_ai_credits":0,"agent_availability":"available","conversation_id":"chat-3"}',
        200,
      );
    });
    await tester.pumpWidget(MaterialApp(home: AssistantPage(api: chatApi(client))));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), 'Show sales trends');
    await tester.tap(find.byTooltip('Send message'));
    await tester.pumpAndSettle();

    expect(find.text('Your AI credits are exhausted. Add credits to continue.'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Manage credits'), findsOneWidget);
  });

  testWidgets('uses a conversation drawer on compact screens', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final client = MockClient((request) async => http.Response('[]', 200));
    await tester.pumpWidget(MaterialApp(home: AssistantPage(api: chatApi(client))));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Conversations'));
    await tester.pumpAndSettle();
    expect(find.text('New conversation'), findsOneWidget);
  });
}