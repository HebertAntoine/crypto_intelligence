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
import 'dart:typed_data';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:http/http.dart' as http;

import '../config.dart';

/// Compiled out of every build that does not ask for it.
const bool lexaEnabled = bool.fromEnvironment('LEXA_ENABLED');

/// Where the member's plans live when the app is served from elsewhere (the
/// public site): the PC, reachable only inside their private Tailscale
/// network. The public build carries this address, never any Lexa content.
const String lexaBaseUrl = String.fromEnvironment('LEXA_BASE_URL');

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
            (lexaBaseUrl.isNotEmpty
                ? lexaBaseUrl
                : AppConfig.apiBaseUrl.isNotEmpty
                    ? AppConfig.apiBaseUrl
                    // Served by the backend itself (PC or private Tailscale
                    // address): talk to the origin the page came from.
                    : (kIsWeb ? Uri.base.origin : lexaDefaultBaseUrl));

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
        'DELETE' => _http.delete(uri),
        _ => _http.get(uri),
      }
          .timeout(const Duration(seconds: 60));
    } on TimeoutException {
      throw const LexaException('Le backend local ne répond pas.');
    } catch (_) {
      throw const LexaException(
          'Tes plans Lexa sont sur ton PC : active Tailscale sur cet appareil '
          '(et vérifie que le PC est allumé), puis tire vers le bas pour recharger.');
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

  // --- the Lexa tab ---------------------------------------------------------

  Future<Map<String, dynamic>> overview() => _send('GET', '/overview');

  Future<Map<String, dynamic>> planForAsset(String asset) =>
      _send('GET', '/plans/${asset.toUpperCase()}');

  Future<Map<String, dynamic>> plan(int analysisId) =>
      _send('GET', '/analyses/$analysisId/plan');

  Future<Map<String, dynamic>> calendar() => _send('GET', '/calendar');

  Future<Map<String, dynamic>> plansHistory() => _send('GET', '/plans-history');

  Future<Map<String, dynamic>> notifications() =>
      _send('GET', '/notifications');

  Future<void> markNotificationsRead() =>
      _send('POST', '/notifications/read', {});

  Future<Map<String, dynamic>> putUserPlan(
          int analysisId, double? budget, List<Map<String, dynamic>> items) =>
      _send('PUT', '/analyses/$analysisId/user-plan',
          {'budget_eur': budget, 'items': items});

  Future<Map<String, dynamic>> addFill(
          int analysisId, Map<String, dynamic> fill) =>
      _send('POST', '/analyses/$analysisId/fills', fill);

  Future<void> deleteFill(int fillId) => _send('DELETE', '/fills/$fillId');

  Future<Map<String, dynamic>> setPlanStatus(
          int analysisId, Map<String, dynamic> body) =>
      _send('POST', '/analyses/$analysisId/status', body);

  Future<Map<String, dynamic>> importTestRun(String runId) =>
      _send('POST', '/test-runs/$runId/import', {});

  // --- 🎙️ listening ------------------------------------------------------------

  Future<String> startListen({String title = '', String? publishedAt}) async =>
      (await _send('POST', '/listen', {
        'title': title,
        'published_at': publishedAt,
      }))['session_id'] as String;

  /// One complete audio slice, sent as is. Never kept by the server.
  Future<void> sendChunk(String sid, Uint8List bytes, String mime) async {
    try {
      final response = await _http
          .post(_uri('/listen/$sid/chunk'),
              headers: {'Content-Type': mime.isEmpty ? 'audio/webm' : mime},
              body: bytes)
          .timeout(const Duration(seconds: 60));
      if (response.statusCode >= 400) {
        final decoded = jsonDecode(utf8.decode(response.bodyBytes));
        throw LexaException(decoded is Map && decoded['detail'] is String
            ? decoded['detail'] as String
            : 'Erreur ${response.statusCode} du backend.');
      }
    } on LexaException {
      rethrow;
    } catch (_) {
      throw const LexaException(
          'Morceau audio non envoyé : vérifie Tailscale.');
    }
  }

  Future<Map<String, dynamic>> finishListen(String sid) =>
      _send('POST', '/listen/$sid/finish', {});

  Future<Map<String, dynamic>> listenStatus(String sid) =>
      _send('GET', '/listen/$sid');

  Future<Map<String, dynamic>> autoImport() =>
      _send('GET', '/settings/auto-import');

  Future<Map<String, dynamic>> setAutoImport(bool enabled) =>
      _send('PUT', '/settings/auto-import', {'enabled': enabled});

  void close() => _http.close();
}
