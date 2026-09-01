import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/auth/subscription_route_guard.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/token_store.dart';

class _SessionTokenStore implements TokenStore {
  @override
  Future<void> clear() async {}
  @override
  Future<String?> readAccessToken() async => 'access';
  @override
  Future<String?> readRefreshToken() async => 'refresh';
  @override
  Future<void> writeTokens(String accessToken, String refreshToken) async {}
}

String? redirect(
  String path, {
  bool authenticated = true,
  bool active = false,
  bool platformAdmin = false,
}) => subscriptionRedirect(
  path: path,
  isAuthenticated: authenticated,
  isPlatformAdmin: platformAdmin,
  hasActiveSubscription: active,
);

void main() {
  test('unauthenticated protected route redirects to login', () {
    expect(redirect('/dashboard', authenticated: false), '/login');
  });

  test('active and trialing tenant state allows the application', () {
    expect(subscriptionAllowsTenantApp('active'), isTrue);
    expect(subscriptionAllowsTenantApp('trialing'), isTrue);
    expect(redirect('/retail', active: true), isNull);
  });

  test('inactive and canceled tenant state redirects to billing', () {
    expect(subscriptionAllowsTenantApp('inactive'), isFalse);
    expect(subscriptionAllowsTenantApp('canceled'), isFalse);
    expect(
      redirect('/dashboard', active: subscriptionAllowsTenantApp('inactive')),
      '/billing',
    );
    expect(
      redirect('/dashboard', active: subscriptionAllowsTenantApp('canceled')),
      '/billing',
    );
  });

  test(
    'platform admin follows the admin flow independently of subscription',
    () {
      expect(redirect('/login', platformAdmin: true), '/admin');
      expect(redirect('/admin', platformAdmin: true), isNull);
      expect(redirect('/admin/agents', platformAdmin: true), isNull);
      expect(redirect('/admin/agents/retail', platformAdmin: true), isNull);
      expect(redirect('/retail', platformAdmin: true), '/admin');
      expect(redirect('/connections', platformAdmin: true), '/admin');
      expect(redirect('/support', platformAdmin: true), '/admin');
    },
  );

  test(
    'subscribed client is returned from admin routes to Retail Intelligence',
    () {
      expect(redirect('/admin/agents', active: true), '/retail');
    },
  );

  test('billing route is exempt and cannot redirect-loop', () {
    expect(redirect('/billing'), isNull);
  });

  test('account setup and security routes remain available', () {
    expect(redirect('/onboarding'), isNull);
    expect(redirect('/settings'), isNull);
    expect(redirect('/pricing'), isNull);
  });

  test(
    'authentication initialization waits for subscription resolution',
    () async {
      final subscriptionResponse = Completer<http.Response>();
      final client = MockClient((request) async {
        if (request.url.path.endsWith('/auth/me')) {
          return http.Response(
            '{"user":{"is_platform_admin":false},"company":{"id":"company-1"}}',
            200,
          );
        }
        if (request.url.path.endsWith('/billing/subscription')) {
          return subscriptionResponse.future;
        }
        return http.Response('{}', 404);
      });
      final auth = AuthController(
        ApiClient(
          tokenStore: _SessionTokenStore(),
          httpClient: client,
          baseUrl: 'https://avenqo.test/api/v1',
        ),
      );

      final initialization = auth.initialize();
      await Future<void>.delayed(Duration.zero);
      expect(auth.initialized, isFalse);

      subscriptionResponse.complete(
        http.Response('{"plan_code":"demo","status":"canceled"}', 200),
      );
      await initialization;

      expect(auth.initialized, isTrue);
      expect(auth.subscriptionStatus, 'canceled');
      expect(auth.hasActiveSubscription, isFalse);
      expect(
        redirect('/dashboard', active: auth.hasActiveSubscription),
        '/billing',
      );
    },
  );
}
