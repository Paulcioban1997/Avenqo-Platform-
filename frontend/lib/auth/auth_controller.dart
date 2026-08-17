import 'package:flutter/foundation.dart';
import 'package:avenqo/core/api_client.dart';

class AuthController extends ChangeNotifier {
  AuthController(this.api);

  final ApiClient api;
  bool _initialized = false;
  bool _busy = false;
  Map<String, dynamic>? _account;

  bool get initialized => _initialized;
  bool get busy => _busy;
  bool get isAuthenticated => _account != null;
  Map<String, dynamic>? get account => _account;
  Map<String, dynamic>? get user => _account?['user'] as Map<String, dynamic>?;
  Map<String, dynamic>? get company =>
      _account?['company'] as Map<String, dynamic>?;

  Future<void> initialize() async {
    await api.initialize();
    if (api.hasSession) {
      try {
        _account = await api.get('/auth/me') as Map<String, dynamic>;
      } on ApiException {
        await api.clearSession();
      }
    }
    _initialized = true;
    notifyListeners();
  }

  Future<void> login(String email, String password) async {
    await _run(() async {
      final data = await api.login(email.trim(), password);
      _account = {'user': data['user'], 'company': data['company']};
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
      notifyListeners();
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
}
