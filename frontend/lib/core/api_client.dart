import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:avenqo/core/app_config.dart';
import 'package:avenqo/core/token_store.dart';

class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({
    required this.tokenStore,
    http.Client? httpClient,
    String baseUrl = AppConfig.apiBaseUrl,
  }) : _httpClient = httpClient ?? http.Client(),
       _baseUrl = baseUrl.replaceFirst(RegExp(r'/$'), '');

  final TokenStore tokenStore;
  final http.Client _httpClient;
  final String _baseUrl;
  String? _accessToken;
  String? _refreshToken;

  bool get hasSession => _accessToken != null && _refreshToken != null;

  Future<void> initialize() async {
    _accessToken = await tokenStore.readAccessToken();
    _refreshToken = await tokenStore.readRefreshToken();
  }

  Future<Map<String, dynamic>> login(String email, String password) async {
    final data = await post(
      '/auth/login',
      body: {'email': email, 'password': password},
      authenticated: false,
    );
    await _saveSession(data as Map<String, dynamic>);
    return data;
  }

  Future<void> clearSession() async {
    _accessToken = null;
    _refreshToken = null;
    await tokenStore.clear();
  }

  Future<dynamic> get(String path, {bool authenticated = true}) {
    return _request('GET', path, authenticated: authenticated);
  }

  Future<dynamic> post(
    String path, {
    Map<String, dynamic>? body,
    bool authenticated = true,
  }) {
    return _request('POST', path, body: body, authenticated: authenticated);
  }

  Future<dynamic> patch(String path, {required Map<String, dynamic> body}) {
    return _request('PATCH', path, body: body, authenticated: true);
  }

  Future<dynamic> delete(String path) {
    return _request('DELETE', path, authenticated: true);
  }

  /// Envoi multipart authentifié (ex. `/datasets/upload`) : `fields` devient
  /// des champs de formulaire, `fileBytes`/`fileName` le fichier joint.
  /// `onProgress` reçoit `(bytesEnvoyés, totalBytes)` pendant l'envoi.
  Future<dynamic> postMultipart(
    String path, {
    required Map<String, String> fields,
    required List<int> fileBytes,
    required String fileName,
    String fileField = 'file',
    void Function(int sent, int total)? onProgress,
    bool retryAfterRefresh = true,
  }) async {
    final uri = Uri.parse('$_baseUrl$path');
    final request = http.MultipartRequest('POST', uri)
      ..fields.addAll(fields)
      ..files.add(
        http.MultipartFile.fromBytes(fileField, fileBytes, filename: fileName),
      );
    if (_accessToken != null) {
      request.headers['Authorization'] = 'Bearer $_accessToken';
    }

    final total = request.contentLength;
    var sent = 0;
    final byteStream = request.finalize().map((chunk) {
      sent += chunk.length;
      onProgress?.call(sent, total);
      return chunk;
    });
    final streamedRequest = http.StreamedRequest(request.method, uri)
      ..headers.addAll(request.headers)
      ..contentLength = total;
    byteStream.listen(
      streamedRequest.sink.add,
      onDone: streamedRequest.sink.close,
      onError: streamedRequest.sink.addError,
    );

    final streamed = await _httpClient.send(streamedRequest);
    final response = await http.Response.fromStream(streamed);
    if (response.statusCode == 401 && retryAfterRefresh) {
      if (await _refresh()) {
        return postMultipart(
          path,
          fields: fields,
          fileBytes: fileBytes,
          fileName: fileName,
          fileField: fileField,
          onProgress: onProgress,
          retryAfterRefresh: false,
        );
      }
    }
    return _decode(response);
  }

  Stream<Map<String, dynamic>> postSseEvents(
    String path, {
    required Map<String, dynamic> body,
  }) async* {
    final headers = <String, String>{
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
    };
    if (_accessToken != null) {
      headers['Authorization'] = 'Bearer $_accessToken';
    }
    final request = http.Request('POST', Uri.parse('$_baseUrl$path'))
      ..headers.addAll(headers)
      ..body = jsonEncode(body);
    final response = await _httpClient.send(request);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final error = await http.Response.fromStream(response);
      _decode(error);
      return;
    }

    await for (final line in response.stream
        .transform(utf8.decoder)
        .transform(const LineSplitter())) {
      if (!line.startsWith('data: ')) continue;
      final payload = jsonDecode(line.substring(6));
      if (payload is Map<String, dynamic> && payload['detail'] != null) {
        throw ApiException(payload['detail'].toString(), statusCode: response.statusCode);
      }
      if (payload is Map<String, dynamic>) {
        yield payload;
      }
    }
  }

  Future<dynamic> _request(
    String method,
    String path, {
    Map<String, dynamic>? body,
    required bool authenticated,
    bool retryAfterRefresh = true,
  }) async {
    final headers = <String, String>{'Content-Type': 'application/json'};
    if (authenticated && _accessToken != null) {
      headers['Authorization'] = 'Bearer $_accessToken';
    }
    final request = http.Request(method, Uri.parse('$_baseUrl$path'))
      ..headers.addAll(headers);
    if (body != null) {
      request.body = jsonEncode(body);
    }
    final streamed = await _httpClient.send(request);
    final response = await http.Response.fromStream(streamed);
    if (response.statusCode == 401 && authenticated && retryAfterRefresh) {
      if (await _refresh()) {
        return _request(
          method,
          path,
          body: body,
          authenticated: authenticated,
          retryAfterRefresh: false,
        );
      }
    }
    return _decode(response);
  }

  Future<bool> _refresh() async {
    if (_refreshToken == null) return false;
    final response = await _httpClient.post(
      Uri.parse('$_baseUrl/auth/refresh'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'refresh_token': _refreshToken}),
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      await clearSession();
      return false;
    }
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    await _saveSession(data);
    return true;
  }

  Future<void> _saveSession(Map<String, dynamic> data) async {
    _accessToken = data['access_token'] as String;
    _refreshToken = data['refresh_token'] as String;
    await tokenStore.writeTokens(_accessToken!, _refreshToken!);
  }

  dynamic _decode(http.Response response) {
    final data = response.body.isEmpty ? null : jsonDecode(response.body);
    if (response.statusCode >= 200 && response.statusCode < 300) return data;
    var message = 'Erreur API';
    if (data is Map<String, dynamic>) {
      final error = data['error'];
      if (error is Map<String, dynamic> && error['message'] != null) {
        message = error['message'].toString();
      } else if (data['detail'] != null) {
        message = data['detail'].toString();
      }
    }
    throw ApiException(message, statusCode: response.statusCode);
  }
}
