/// HTTP client for the Crypto Intelligence backend.
///
/// The app renders what the backend computed and computes nothing itself.
/// That is deliberate: every analytical decision, every threshold and every
/// edge verdict lives in one place, so the phone and the web UI can never
/// disagree with each other or with the research.
library;
import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config.dart';
import 'models.dart';

class ApiException implements Exception {
  final int? statusCode;
  final String message;

  const ApiException(this.message, {this.statusCode});

  @override
  String toString() =>
      statusCode == null ? message : 'HTTP $statusCode: $message';
}

class ApiClient {
  final http.Client _http;
  final String baseUrl;
  final Duration timeout;

  ApiClient({http.Client? client, String? baseUrl, this.timeout = const Duration(seconds: 30)})
      : _http = client ?? http.Client(),
        baseUrl = baseUrl ?? AppConfig.apiBaseUrl;

  Uri _uri(String path, [Map<String, String>? query]) {
    final normalised = path.startsWith('/') ? path : '/$path';
    if (baseUrl.isEmpty) {
      // Same-origin build: let the browser resolve it.
      return Uri.parse('/api$normalised').replace(queryParameters: query);
    }
    final base = baseUrl.endsWith('/')
        ? baseUrl.substring(0, baseUrl.length - 1)
        : baseUrl;
    return Uri.parse('$base/api$normalised').replace(queryParameters: query);
  }

  Future<dynamic> _get(String path, [Map<String, String>? query]) async {
    late final http.Response response;
    try {
      response = await _http.get(_uri(path, query)).timeout(timeout);
    } on TimeoutException {
      throw ApiException(
        'The backend did not answer within ${timeout.inSeconds}s. '
        'Some research endpoints are genuinely slow on a cold cache.',
      );
    } catch (error) {
      throw ApiException('Could not reach the backend: $error');
    }

    if (response.statusCode >= 400) {
      String detail = response.reasonPhrase ?? 'request failed';
      try {
        final body = jsonDecode(response.body) as Map<String, dynamic>;
        detail = (body['detail'] ?? body['error'] ?? detail).toString();
      } catch (_) {
        // Body was not JSON; the status line is the best we have.
      }
      throw ApiException(detail, statusCode: response.statusCode);
    }
    return jsonDecode(response.body);
  }

  Future<Map<String, dynamic>> health() async =>
      await _get('/health') as Map<String, dynamic>;

  Future<TodayRead> today(String asset) async =>
      TodayRead.fromJson(await _get('/today/$asset') as Map<String, dynamic>);

  Future<List<TodayRead>> todayAll(List<String> assets) async {
    // Parallel, because three sequential round trips on a phone is a visible
    // wait for no reason.
    final results = await Future.wait(assets.map(today));
    return results;
  }

  Future<StructureRead> structure(String asset, {String timeframe = '4h'}) async =>
      StructureRead.fromJson(
        await _get('/structure/$asset', {'timeframe': timeframe})
            as Map<String, dynamic>,
      );

  Future<Map<String, dynamic>> multiTimeframe(String asset) async =>
      await _get('/structure/$asset/multi-timeframe') as Map<String, dynamic>;

  Future<EntryOpportunity> entryOpportunity(
    String asset, {
    String timeframe = '4h',
  }) async =>
      EntryOpportunity.fromJson(
        await _get('/entry-opportunity/$asset', {'timeframe': timeframe})
            as Map<String, dynamic>,
      );

  Future<Map<String, dynamic>> educationalClaims() async =>
      await _get('/knowledge/educational-claims') as Map<String, dynamic>;

  Future<Map<String, dynamic>> claimValidation() async =>
      await _get('/research/claim-validation') as Map<String, dynamic>;

  Future<Map<String, dynamic>> datasetQuality() async =>
      await _get('/knowledge/dataset-quality') as Map<String, dynamic>;

  Future<Map<String, dynamic>> sourceHierarchy() async =>
      await _get('/sources/hierarchy') as Map<String, dynamic>;

  Future<Map<String, dynamic>> marginalValue() async =>
      await _get('/research/marginal-value') as Map<String, dynamic>;

  Future<Map<String, dynamic>> structuralResearch() async =>
      await _get('/research/structural') as Map<String, dynamic>;

  Future<Map<String, dynamic>> replication() async =>
      await _get('/research/replication') as Map<String, dynamic>;

  Future<Map<String, dynamic>> edgeAll() async =>
      await _get('/edge') as Map<String, dynamic>;

  Future<Map<String, dynamic>> derivativesAggregate(String asset) async =>
      await _get('/derivatives/aggregate/$asset') as Map<String, dynamic>;

  Future<Map<String, dynamic>> crossAsset(String asset) async =>
      await _get('/cross-asset/$asset') as Map<String, dynamic>;

  void close() => _http.close();
}
