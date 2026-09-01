import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/token_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class _TestTokenStore implements TokenStore {
  String? accessToken;
  String? refreshToken;

  @override
  Future<void> clear() async {
    accessToken = null;
    refreshToken = null;
  }

  @override
  Future<String?> readAccessToken() async => null;
  @override
  Future<String?> readRefreshToken() async => null;
  @override
  Future<void> writeTokens(String accessToken, String refreshToken) async {
    this.accessToken = accessToken;
    this.refreshToken = refreshToken;
  }
}

void main() {
  test(
    'a 422 validation error surfaces the field detail instead of the generic message',
    () async {
      final client = MockClient((request) async {
        return http.Response(
          '{"success": false, "error": {"code": "VALIDATION_ERROR", '
          '"message": "Request validation failed", "details": '
          '[{"loc": ["body", "password"], "msg": "String should have at '
          'least 10 characters"}]}, "request_id": null}',
          422,
        );
      });
      final api = ApiClient(
        tokenStore: _TestTokenStore(),
        httpClient: client,
        baseUrl: 'https://avenqo.test/api/v1',
      );

      await expectLater(
        api.post('/auth/register', authenticated: false, body: const {}),
        throwsA(
          isA<ApiException>().having(
            (error) => error.message,
            'message',
            contains('String should have at least 10 characters'),
          ),
        ),
      );
    },
  );

  test('register logs in immediately and persists the session', () async {
    final store = _TestTokenStore();
    final requestedPaths = <String>[];
    final client = MockClient((request) async {
      requestedPaths.add(request.url.path);
      if (request.url.path.endsWith('/auth/register')) {
        return http.Response('{"message":"Compte créé"}', 201);
      }
      return http.Response(
        '{"access_token":"access-123","refresh_token":"refresh-456",'
        '"user":{"id":"user-1"},"company":{"id":"company-1"}}',
        200,
      );
    });
    final api = ApiClient(
      tokenStore: store,
      httpClient: client,
      baseUrl: 'https://avenqo.test/api/v1',
    );

    final response = await api.register({
      'email': 'owner@avenqo.test',
      'password': 'Avenqo2026!',
      'selected_modules': ['retail', 'crm'],
    });

    expect(requestedPaths, ['/api/v1/auth/register', '/api/v1/auth/login']);
    expect(response['user']['id'], 'user-1');
    expect(store.accessToken, 'access-123');
    expect(store.refreshToken, 'refresh-456');
    expect(api.hasSession, isTrue);
  });
}
