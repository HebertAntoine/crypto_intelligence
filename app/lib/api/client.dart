/// HTTP client for the Crypto Intelligence backend.
///
/// The app renders what the backend computed and computes nothing itself.
/// That is deliberate: every analytical decision, every threshold and every
/// edge verdict lives in one place, so the phone and the web UI can never
/// disagree with each other or with the research.
library;
import 'dart:async';
import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;
import 'package:http/http.dart' as http;

import '../config.dart';
import 'models.dart';

/// Where the last response actually came from.
///
/// The app bundles JSON snapshots so it can render on a host with no backend.
/// That is a legitimate fallback, but a snapshot is a photograph of a past
/// moment: it must never be presented as today's reading without saying so.
/// Before this existed, `_get` returned identical shapes for live and frozen
/// data and the UI had no way to tell them apart.
enum DataOrigin { live, snapshot, unknown }

class DataProvenance {
  final DataOrigin origin;
  final DateTime? generatedAt;

  const DataProvenance(this.origin, {this.generatedAt});

  static const unknown = DataProvenance(DataOrigin.unknown);

  bool get isSnapshot => origin == DataOrigin.snapshot;

  /// How stale the snapshot is. Null when the data is live or undated.
  Duration? get age =>
      generatedAt == null ? null : DateTime.now().toUtc().difference(generatedAt!);

  /// A snapshot older than this is misleading if labelled "today".
  bool get isStale {
    final elapsed = age;
    return elapsed != null && elapsed > const Duration(hours: 12);
  }

  String describe() {
    if (origin == DataOrigin.live) return 'Données en direct';
    if (origin != DataOrigin.snapshot) return 'Origine inconnue';
    final elapsed = age;
    if (elapsed == null) return 'Instantané intégré, date inconnue';
    if (elapsed.inHours < 1) return 'Instantané intégré, il y a ${elapsed.inMinutes} min';
    if (elapsed.inHours < 48) return 'Instantané intégré, il y a ${elapsed.inHours} h';
    return 'Instantané intégré, il y a ${elapsed.inDays} jours';
  }
}

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
  final Future<String> Function(String) _loadAsset;

  /// Provenance of the most recent successful response. Read it after a call
  /// to know whether the UI is showing live data or a bundled snapshot.
  DataProvenance lastProvenance = DataProvenance.unknown;

  ApiClient({
    http.Client? client,
    String? baseUrl,
    this.timeout = const Duration(seconds: 30),
    Future<String> Function(String)? loadAsset,
  })
      : _http = client ?? http.Client(),
        baseUrl = baseUrl ?? AppConfig.apiBaseUrl,
        _loadAsset = loadAsset ?? rootBundle.loadString;

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
    if (_useStaticSnapshotFirst) {
      final snapshot = await _tryStaticSnapshot(path, query);
      if (snapshot != null) return snapshot;
    }

    late final http.Response response;
    try {
      response = await _http.get(_uri(path, query)).timeout(timeout);
    } on TimeoutException {
      final snapshot = await _tryStaticSnapshot(path, query);
      if (snapshot != null) return snapshot;
      throw ApiException(
        'The backend did not answer within ${timeout.inSeconds}s. '
        'Some research endpoints are genuinely slow on a cold cache.',
      );
    } catch (error) {
      final snapshot = await _tryStaticSnapshot(path, query);
      if (snapshot != null) return snapshot;
      throw ApiException('Could not reach the backend: $error');
    }

    if (response.statusCode >= 400) {
      final snapshot = await _tryStaticSnapshot(path, query);
      if (snapshot != null) return snapshot;
      String detail = response.reasonPhrase ?? 'request failed';
      try {
        final body = jsonDecode(response.body) as Map<String, dynamic>;
        detail = (body['detail'] ?? body['error'] ?? detail).toString();
      } catch (_) {
        // Body was not JSON; the status line is the best we have.
      }
      throw ApiException(detail, statusCode: response.statusCode);
    }
    try {
      final decoded = jsonDecode(response.body);
      lastProvenance = const DataProvenance(DataOrigin.live);
      return decoded;
    } catch (error) {
      final snapshot = await _tryStaticSnapshot(path, query);
      if (snapshot != null) return snapshot;
      throw ApiException('The backend returned invalid JSON: $error');
    }
  }

  Future<dynamic> _tryStaticSnapshot(
    String path,
    Map<String, String>? query,
  ) async {
    if (!_canUseStaticSnapshot) return null;
    try {
      final decoded = jsonDecode(await _loadAsset(_staticSnapshotPath(path, query)));
      lastProvenance = DataProvenance(
        DataOrigin.snapshot,
        generatedAt: _snapshotTimestamp(decoded),
      );
      return decoded;
    } catch (_) {
      return null;
    }
  }

  /// Pull the generation time out of a snapshot payload.
  ///
  /// The exporter stamps `decision_summary.generated_at`; other endpoints use
  /// `generated_at`. A snapshot without either is treated as undated rather
  /// than as fresh - an unknown age must never read as "just now".
  DateTime? _snapshotTimestamp(dynamic payload) {
    if (payload is! Map) return null;
    final candidates = <dynamic>[
      payload['generated_at'],
      (payload['decision_summary'] as Map?)?['generated_at'],
      payload['exported_at'],
    ];
    for (final value in candidates) {
      if (value is String) {
        final parsed = DateTime.tryParse(value);
        if (parsed != null) return parsed.toUtc();
      }
    }
    return null;
  }

  bool get _canUseStaticSnapshot => AppConfig.staticApiFallbackEnabled;

  bool get _useStaticSnapshotFirst =>
      baseUrl.isEmpty && AppConfig.staticApiFallbackEnabled;

  String _staticSnapshotPath(String path, Map<String, String>? query) {
    var name = path.startsWith('/') ? path.substring(1) : path;
    name = name.replaceAll('/', '__');
    if (query != null && query.isNotEmpty) {
      final pairs = query.entries.toList()
        ..sort((a, b) => a.key.compareTo(b.key));
      final suffix = pairs.map((e) => '${e.key}-${e.value}').join('__');
      name = '${name}__$suffix';
    }
    return 'assets/static_api/$name.json';
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
