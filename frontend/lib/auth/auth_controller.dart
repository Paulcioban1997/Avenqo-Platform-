import 'package:flutter/foundation.dart';
import 'package:avenqo/auth/subscription_route_guard.dart';
import 'package:avenqo/core/api_client.dart';

class AuthController extends ChangeNotifier {
  AuthController(this.api);

  final ApiClient api;
  bool _initialized = false;
  bool _busy = false;
  Map<String, dynamic>? _account;
  String _subscriptionStatus = 'inactive';

  bool get initialized => _initialized;
  bool get busy => _busy;
  bool get isAuthenticated => _account != null;
  Map<String, dynamic>? get account => _account;
  Map<String, dynamic>? get user => _account?['user'] as Map<String, dynamic>?;
  Map<String, dynamic>? get company =>
      _account?['company'] as Map<String, dynamic>?;
  bool get isPlatformAdmin => user?['is_platform_admin'] == true;
  String get subscriptionStatus => _subscriptionStatus;
  bool get hasActiveSubscription =>
      isPlatformAdmin || subscriptionAllowsTenantApp(_subscriptionStatus);

  Future<void> initialize() async {
    await api.initialize();
    if (api.hasSession) {
      try {
        _account = await api.get('/auth/me') as Map<String, dynamic>;
        await _refreshSubscription();
      } on ApiException {
        await api.clearSession();
        _account = null;
        _subscriptionStatus = 'inactive';
      }
    }
    _initialized = true;
    notifyListeners();
  }

  Future<void> login(String email, String password) async {
    await _run(() async {
      final data = await api.login(email.trim(), password);
      _account = {'user': data['user'], 'company': data['company']};
      await _refreshSubscription();
    });
  }

  Future<void> register(Map<String, dynamic> request) async {
    await _run(
      () => api.post('/auth/register', body: request, authenticated: false),
    );
  }

  Future<void> forgotPassword(String email) async {
    await _run(
      () => api.post(
        '/auth/password/forgot',
        body: {'email': email.trim()},
        authenticated: false,
      ),
    );
  }

  Future<void> verifyEmail(String token) async {
    await _run(
      () => api.post(
        '/auth/email/verify',
        body: {'token': token.trim()},
        authenticated: false,
      ),
    );
  }

  Future<void> resetPassword(String token, String password) async {
    await _run(
      () => api.post(
        '/auth/password/reset',
        body: {'token': token.trim(), 'new_password': password},
        authenticated: false,
      ),
    );
  }

  Future<void> logout() async {
    try {
      await api.post('/auth/logout');
    } finally {
      await api.clearSession();
      _account = null;
      _subscriptionStatus = 'inactive';
      notifyListeners();
    }
  }

  /// Recharge `/auth/me` pour refléter un changement côté serveur qui n'est
  /// pas issu de `login` (ex. : complétion/abandon de l'onboarding), sans
  /// exiger de nouvelle authentification.
  Future<void> refreshAccount() async {
    if (!api.hasSession) return;
    try {
      _account = await api.get('/auth/me') as Map<String, dynamic>;
      await _refreshSubscription();
      notifyListeners();
    } on ApiException {
      // Best-effort : on garde l'état local précédent si le rafraîchissement échoue.
    }
  }

  Future<void> _run(Future<void> Function() action) async {
    _busy = true;
    notifyListeners();
    try {
      await action();
    } finally {
      _busy = false;
      notifyListeners();
    }
  }

  Future<void> _refreshSubscription() async {
    if (_account == null || isPlatformAdmin) {
      _subscriptionStatus = isPlatformAdmin ? 'active' : 'inactive';
      return;
    }
    try {
      final subscription =
          await api.get('/billing/subscription') as Map<String, dynamic>;
      _subscriptionStatus =
          subscription['status']?.toString().trim().toLowerCase() ?? 'inactive';
    } on ApiException {
      _subscriptionStatus = 'inactive';
    }
  }
}
