/// Client for the local Lexa routes.
///
/// Lexa content comes from a personal subscription whose terms forbid any
/// redistribution. So this client never reads the bundled snapshots, never
/// falls back to another host, and the tab that uses it only exists in a build
/// made with `--dart-define=LEXA_ENABLED=true`. The public web build never
/// contains it.
library;

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config.dart';

/// Compiled out of every build that does not ask for it.
const bool lexaEnabled = bool.fromEnvironment('LEXA_ENABLED');

/// The backend on this machine. Lexa routes answer loopback clients only.
const String lexaDefaultBaseUrl = 'http://127.0.0.1:8100';

class LexaException implements Exception {
  final String message;
  const LexaException(this.message);

  @override
  String toString() => message;
}

class LexaClient {
  final http.Client _http;
  final String baseUrl;

  LexaClient({http.Client? client, String? baseUrl})
      : _http = client ?? http.Client(),
        baseUrl = baseUrl ??
            (AppConfig.apiBaseUrl.isEmpty
                ? lexaDefaultBaseUrl
                : AppConfig.apiBaseUrl);

  Uri _uri(String path) =>
      Uri.parse('${baseUrl.replaceAll(RegExp(r'/+$'), '')}/api/lexa$path');

  Future<Map<String, dynamic>> _send(
    String method,
    String path, [
    Object? body,
  ]) async {
    final uri = _uri(path);
    const headers = {'Content-Type': 'application/json'};
    http.Response response;
    try {
      response = await switch (method) {
        'POST' => _http.post(uri, headers: headers, body: jsonEncode(body)),
        'PUT' => _http.put(uri, headers: headers, body: jsonEncode(body)),
        _ => _http.get(uri),
      }
          .timeout(const Duration(seconds: 60));
    } on TimeoutException {
      throw const LexaException('Le backend local ne répond pas.');
    } catch (_) {
      throw const LexaException(
          'Backend local injoignable. Lance-le sur 127.0.0.1 pour voir les analyses Lexa.');
    }
    final decoded = response.body.isEmpty
        ? <String, dynamic>{}
        : jsonDecode(utf8.decode(response.bodyBytes));
    if (response.statusCode >= 400) {
      final detail = decoded is Map ? decoded['detail'] : null;
      throw LexaException(detail is String
          ? detail
          : 'Erreur ${response.statusCode} du backend local.');
    }
    return (decoded as Map).cast<String, dynamic>();
  }

  Future<Map<String, dynamic>> videos() => _send('GET', '/videos');

  Future<Map<String, dynamic>> analysis(int id) =>
      _send('GET', '/analyses/$id');

  Future<Map<String, dynamic>> history(String asset) =>
      _send('GET', '/history/${asset.toUpperCase()}');

  Future<Map<String, dynamic>> compare(int id) => _send('GET', '/compare/$id');

  Future<int> createVideo(Map<String, dynamic> body) async =>
      (await _send('POST', '/videos', body))['video_id'] as int;

  Future<void> correctLevel(int levelId, double value) =>
      _send('POST', '/levels/$levelId/correction', {'value': value});

  Future<void> setCapital(double value, {String? asset}) =>
      _send('PUT', '/settings/capital', {'value': value, 'asset': asset});

  Future<String> startTestRun({
    required String transcript,
    required String title,
    String? publishedAt,
    double capital = 100,
  }) async =>
      (await _send('POST', '/test-runs', {
        'transcript': transcript,
        'title': title,
        'published_at': publishedAt,
        'capital': capital,
      }))['run_id'] as String;

  Future<Map<String, dynamic>> testRun(String id) =>
      _send('GET', '/test-runs/$id');

  Future<Map<String, dynamic>> testRuns() => _send('GET', '/test-runs');

  void close() => _http.close();
}
