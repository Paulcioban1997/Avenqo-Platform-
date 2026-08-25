import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/token_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class _TestTokenStore implements TokenStore {
  @override
  Future<void> clear() async {}
  @override
  Future<String?> readAccessToken() async => null;
  @override
  Future<String?> readRefreshToken() async => null;
  @override
  Future<void> writeTokens(String accessToken, String refreshToken) async {}
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
}
