import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:avenqo/core/app_config.dart';
import 'package:avenqo/core/token_store.dart';

class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode, this.isTimeout = false});

  final String message;
  final int? statusCode;
  final bool isTimeout;

  @override
  String toString() => message;
}

class DownloadedFile {
  const DownloadedFile(this.bytes, this.fileName);

  final Uint8List bytes;
  final String fileName;
}

class ApiClient {
  ApiClient({
    required this.tokenStore,
    http.Client? httpClient,
    String baseUrl = AppConfig.apiBaseUrl,
    this._requestTimeout = const Duration(seconds: 15),
  }) : _httpClient = httpClient ?? http.Client(),
       _baseUrl = baseUrl.replaceFirst(RegExp(r'/$'), '');

  final TokenStore tokenStore;
  final http.Client _httpClient;
  final String _baseUrl;
  final Duration _requestTimeout;
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

  Future<Map<String, dynamic>> register(Map<String, dynamic> request) async {
    return await post('/auth/register', body: request, authenticated: false)
        as Map<String, dynamic>;
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

  Future<DownloadedFile> download(
    String path, {
    bool retryAfterRefresh = true,
  }) async {
    final headers = <String, String>{};
    if (_accessToken != null) headers['Authorization'] = 'Bearer $_accessToken';
    late final http.Response response;
    try {
      response = await _httpClient
          .get(Uri.parse('$_baseUrl$path'), headers: headers)
          .timeout(_requestTimeout);
    } on TimeoutException {
      throw const ApiException('Avenqo request timed out', isTimeout: true);
    } on Object {
      throw const ApiException('Avenqo request failed');
    }
    if (response.statusCode == 401 && retryAfterRefresh && await _refresh()) {
      return download(path, retryAfterRefresh: false);
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      _decode(response);
    }
    final disposition = response.headers['content-disposition'] ?? '';
    final match = RegExp(r'filename="?([^";]+)').firstMatch(disposition);
    return DownloadedFile(
      response.bodyBytes,
      match?.group(1) ?? 'avenqo-export',
    );
  }

  /// Envoi multipart authentifié (ex. `/datasets/upload`) : `fields` devient
  /// des champs de formulaire, `fileBytes`/`fileName` le fichier joint.
  /// Les archives ZIP sélectionnées depuis l'écran Connexions sont routées
  /// automatiquement vers `/datasets/archive`, où le backend extrait puis
  /// ingère chaque dataset supporté indépendamment.
  ///
  /// Les imports de gros datasets peuvent légitimement prendre plusieurs
  /// minutes côté serveur (parsing XLSX, profilage, nettoyage). Ils utilisent
  /// donc un délai dédié, beaucoup plus long que les requêtes API ordinaires,
  /// afin que le navigateur ne ferme pas la requête pendant le traitement.
  Future<dynamic> postMultipart(
    String path, {
    required Map<String, String> fields,
    required List<int> fileBytes,
    required String fileName,
    String fileField = 'file',
    void Function(int sent, int total)? onProgress,
    bool retryAfterRefresh = true,
  }) async {
    const uploadTimeout = Duration(minutes: 10);
    final isDatasetZip =
        path == '/datasets/upload' && fileName.toLowerCase().endsWith('.zip');
    final effectivePath = isDatasetZip ? '/datasets/archive' : path;
    final uri = Uri.parse('$_baseUrl$effectivePath');
    final request = http.MultipartRequest('POST', uri)
      ..fields.addAll(fields)
      ..files.add(
        http.MultipartFile.fromBytes(fileField, fileBytes, filename: fileName),
      );
    if (_accessToken != null) {
      request.headers['Authorization'] = 'Bearer $_accessToken';
    }

    final total = request.contentLength;
    onProgress?.call(0, total);
    late final http.Response response;
    try {
      final streamed = await _httpClient.send(request).timeout(uploadTimeout);
      response = await http.Response.fromStream(streamed).timeout(uploadTimeout);
    } on TimeoutException {
      throw const ApiException(
        'Le traitement du fichier prend plus de temps que prévu. Réessayez dans quelques instants.',
        isTimeout: true,
      );
    } on Object catch (error) {
      if (error is ApiException) rethrow;
      throw const ApiException('Avenqo request failed');
    }
    onProgress?.call(total, total);
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
    late final http.StreamedResponse response;
    try {
      response = await _httpClient.send(request).timeout(_requestTimeout);
    } on TimeoutException {
      throw const ApiException('Avenqo request timed out', isTimeout: true);
    } on Object catch (error) {
      if (error is ApiException) rethrow;
      throw const ApiException('Avenqo request failed');
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final error = await http.Response.fromStream(response);
      _decode(error);
      return;
    }

    await for (final line
        in response.stream
            .transform(utf8.decoder)
            .transform(const LineSplitter())) {
      if (!line.startsWith('data: ')) continue;
      final payload = jsonDecode(line.substring(6));
      if (payload is Map<String, dynamic> && payload['detail'] != null) {
        throw ApiException(
          payload['detail'].toString(),
          statusCode: response.statusCode,
        );
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
    late final http.Response response;
    try {
      final streamed = await _httpClient.send(request).timeout(_requestTimeout);
      response = await http.Response.fromStream(
        streamed,
      ).timeout(_requestTimeout);
    } on TimeoutException {
      throw const ApiException('Avenqo request timed out', isTimeout: true);
    } on Object catch (error) {
      if (error is ApiException) rethrow;
      throw const ApiException('Avenqo request failed');
    }
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
    late final http.Response response;
    try {
      response = await _httpClient
          .post(
            Uri.parse('$_baseUrl/auth/refresh'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'refresh_token': _refreshToken}),
          )
          .timeout(_requestTimeout);
    } on TimeoutException {
      await clearSession();
      return false;
    } on Object {
      await clearSession();
      return false;
    }
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
      if (error is Map<String, dynamic>) {
        final fieldMessage = _fieldValidationMessage(error['details']);
        if (fieldMessage != null) {
          message = fieldMessage;
        } else if (error['message'] != null) {
          message = error['message'].toString();
        }
      } else if (data['detail'] != null) {
        message = data['detail'].toString();
      }
    }
    throw ApiException(message, statusCode: response.statusCode);
  }

  String? _fieldValidationMessage(dynamic details) {
    if (details is! List || details.isEmpty) return null;
    final lines = <String>[];
    for (final detail in details) {
      if (detail is! Map<String, dynamic>) continue;
      final loc = detail['loc'];
      final field = loc is List && loc.isNotEmpty ? loc.last.toString() : null;
      final msg = detail['msg']?.toString();
      if (msg == null) continue;
      lines.add(field != null ? '$field: $msg' : msg);
    }
    return lines.isEmpty ? null : lines.join('\n');
  }
}
