/// URL construction and error handling.
///
/// The recurring assertion: a failure must surface as an exception the UI can
/// show, never as an empty result that looks like "no data".
library;

import 'package:crypto_intelligence_app/api/client.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

/// Minimal stub so the tests need no extra package.
class StubClient extends http.BaseClient {
  final Future<http.Response> Function(http.BaseRequest) handler;

  StubClient(this.handler);

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final response = await handler(request);
    return http.StreamedResponse(
      Stream.value(response.bodyBytes),
      response.statusCode,
      reasonPhrase: response.reasonPhrase,
    );
  }
}

void main() {
  group('URL building', () {
    test('a configured base URL is used for API calls', () async {
      late Uri seen;
      final client = ApiClient(
        baseUrl: 'https://api.example.com',
        client: StubClient((request) async {
          seen = request.url;
          return http.Response('{"status":"ok"}', 200);
        }),
      );
      await client.health();
      expect(seen.toString(), 'https://api.example.com/api/health');
    });

    test('a trailing slash on the base URL does not double up', () async {
      late Uri seen;
      final client = ApiClient(
        baseUrl: 'https://api.example.com/',
        client: StubClient((request) async {
          seen = request.url;
          return http.Response('{}', 200);
        }),
      );
      await client.health();
      expect(seen.path, '/api/health');
    });

    test('query parameters are passed through', () async {
      late Uri seen;
      final client = ApiClient(
        baseUrl: 'https://api.example.com',
        client: StubClient((request) async {
          seen = request.url;
          return http.Response('{}', 200);
        }),
      );
      await client.structure('BTC', timeframe: '1d');
      expect(seen.path, '/api/structure/BTC');
      expect(seen.queryParameters['timeframe'], '1d');
    });

    test('chart requests carry period and timeframe', () async {
      late Uri seen;
      final client = ApiClient(
        baseUrl: 'https://api.example.com',
        client: StubClient((request) async {
          seen = request.url;
          return http.Response('''
{
  "asset": "BTC",
  "timeframe": "4h",
  "period": "7d",
  "available": true,
  "candles": [],
  "summary": {"available": true}
}
''', 200);
        }),
      );
      await client.chart('BTC', timeframe: '4h', period: '7d');
      expect(seen.path, '/api/chart/BTC');
      expect(seen.queryParameters['timeframe'], '4h');
      expect(seen.queryParameters['period'], '7d');
    });

    test('market price endpoint is typed', () async {
      late Uri seen;
      final client = ApiClient(
        baseUrl: 'https://api.example.com',
        client: StubClient((request) async {
          seen = request.url;
          return http.Response('''
{
  "asset": "BTC",
  "status": "LIVE",
  "price_usd": 100000,
  "price_eur": 92000,
  "change_24h_pct": 1.5,
  "timestamp": "2026-09-07T08:00:00Z",
  "as_of": "2026-09-07T08:00:00Z",
  "fetched_at": "2026-09-07T08:00:02Z",
  "providers": [],
  "provider_count": 2,
  "quality": "HIGH",
  "freshness": "LIVE"
}
''', 200);
        }),
      );
      final price = await client.marketPrice('BTC');
      expect(seen.path, '/api/market/price/BTC');
      expect(price.available, isTrue);
      expect(price.displayUnit, 'EUR');
      expect(price.displayPrice, 92000);
    });
  });

  group('Error handling', () {
    test('a backend error message is surfaced, not swallowed', () async {
      final client = ApiClient(
        baseUrl: 'https://api.example.com',
        client: StubClient(
            (_) async => http.Response('{"detail":"Unknown asset DOGE"}', 404)),
      );
      expect(
        () => client.today('DOGE'),
        throwsA(isA<ApiException>()
            .having((e) => e.message, 'message', contains('Unknown asset'))),
      );
    });

    test('a non-JSON error still produces a usable exception', () async {
      final client = ApiClient(
        baseUrl: 'https://api.example.com',
        client: StubClient((_) async => http.Response('<html>502</html>', 502)),
      );
      expect(() => client.health(), throwsA(isA<ApiException>()));
    });

    test('an unreachable backend is reported, never silently empty', () async {
      final client = ApiClient(
        baseUrl: 'https://api.example.com',
        client: StubClient((_) async => throw Exception('connection refused')),
      );
      expect(
        () => client.health(),
        throwsA(isA<ApiException>()
            .having((e) => e.message, 'message', contains('Could not reach'))),
      );
    });

    test('same-origin HTML falls back to a bundled static snapshot', () async {
      var requestCount = 0;
      final client = ApiClient(
        baseUrl: '',
        client: StubClient((_) async {
          requestCount += 1;
          return http.Response('<html>app shell</html>', 200);
        }),
        loadAsset: (path) async {
          expect(path, 'assets/static_api/health.json');
          return '{"status":"ok","source":"static"}';
        },
      );

      final health = await client.health();
      expect(health['status'], 'ok');
      expect(health['source'], 'static');
      expect(requestCount, 0);
    });

    test('configured API HTML can still fall back to a bundled snapshot',
        () async {
      final client = ApiClient(
        baseUrl: 'https://wrong.example.com',
        client: StubClient(
            (_) async => http.Response('<html>app shell</html>', 200)),
        loadAsset: (path) async {
          expect(path, 'assets/static_api/health.json');
          return '{"status":"ok","source":"static"}';
        },
      );

      final health = await client.health();
      expect(health['status'], 'ok');
      expect(health['source'], 'static');
    });
  });

  _provenanceTests();

  group('Payload parsing', () {
    test('a today payload maps into the model', () async {
      final client = ApiClient(
        baseUrl: 'https://api.example.com',
        client: StubClient((_) async => http.Response('''
{
  "asset": "BTC",
  "market_data": {
    "asset": "BTC",
    "status": "LIVE",
    "price_usd": 100000,
    "price_eur": 92000,
    "change_24h_pct": 1.5,
    "timestamp": "2026-09-07T08:00:00Z",
    "as_of": "2026-09-07T08:00:00Z",
    "fetched_at": "2026-09-07T08:00:02Z",
    "providers": [
      {
        "provider": "binance_spot",
        "source": "Binance",
        "status": "OK",
        "unit": "USD",
        "price": 100000,
        "change_24h_pct": 1.5,
        "freshness": "LIVE",
        "quality": "MEASURED"
      }
    ],
    "provider_count": 1,
    "quality": "SINGLE_PROVIDER",
    "freshness": "LIVE"
  },
  "decision_summary": {
    "asset": "BTC",
    "market_direction": "STRONGLY_BULLISH",
    "edge_state": "NO_MEASURABLE_EDGE",
    "actionable": false,
    "statement": "BTC is strongly bullish, but we hold no robust edge.",
    "caveats": []
  },
  "edge": {"state": "NO_MEASURABLE_EDGE", "admitted_count": 0, "rejected_count": 3},
  "uncertainty": {"level": "HIGH", "score": 60, "drivers": []},
  "crowding": {"level": "NORMAL", "direction": "UNKNOWN"},
  "leverage_state": {"state": "NEW_LONGS"},
  "funding": {"band": "NEUTRAL", "percentile": 45.7},
  "volatility": {"regime": "LOW"}
}
''', 200)),
      );
      final read = await client.today('BTC');
      expect(read.asset, 'BTC');
      expect(read.summary.marketDirection, 'STRONGLY_BULLISH');
      expect(read.edgeState.isMeasured, isFalse);
      expect(read.rejectedCount, 3);
      expect(read.crowdingDirection, 'UNKNOWN');
      expect(read.marketData?.displayPrice, 92000);
      expect(read.marketData?.change24hPct, 1.5);
    });

    test('a chart payload maps candles and indicator series', () async {
      final client = ApiClient(
        baseUrl: 'https://api.example.com',
        client: StubClient((_) async => http.Response('''
{
  "asset": "BTC",
  "timeframe": "4h",
  "period": "7d",
  "available": true,
  "candles": [
    {
      "time": "2026-09-07T08:00:00Z",
      "open": 100,
      "high": 110,
      "low": 98,
      "close": 108,
      "volume": 42
    }
  ],
  "overlays": {"ema20": [null, 104.5]},
  "panels": {"rsi": [55.1]},
  "summary": {"last_price": 108, "change_pct": 8, "bars": 1}
}
''', 200)),
      );
      final read = await client.chart('BTC');
      expect(read.available, isTrue);
      expect(read.candles.single.close, 108);
      expect(read.overlays['ema20']!.last, 104.5);
      expect(read.panels['rsi']!.single, 55.1);
      expect(read.lastPrice, 108);
      expect(read.changePct, 8);
      expect(read.bars, 1);
    });
  });
}

/// Provenance: the app must never present a frozen snapshot as live data.
void _provenanceTests() {
  group('Data provenance', () {
    test('a live response is marked live', () async {
      final client = ApiClient(
        baseUrl: 'https://api.example.com',
        client: StubClient((_) async => http.Response('{"status":"ok"}', 200)),
      );
      await client.health();
      expect(client.lastProvenance.origin, DataOrigin.live);
      expect(client.lastProvenance.isSnapshot, isFalse);
    });

    test('a snapshot is marked as such, with its generation time', () async {
      final generated = DateTime.utc(2026, 9, 6, 20, 1);
      final client = ApiClient(
        baseUrl: 'https://api.example.com',
        client: StubClient((_) async => throw Exception('offline')),
        loadAsset: (_) async =>
            '{"generated_at":"${generated.toIso8601String()}"}',
      );
      await client.health();
      expect(client.lastProvenance.isSnapshot, isTrue);
      expect(client.lastProvenance.generatedAt, generated);
    });

    test('a snapshot older than twelve hours is stale', () {
      final old = DataProvenance(
        DataOrigin.snapshot,
        generatedAt: DateTime.now().toUtc().subtract(const Duration(days: 3)),
      );
      expect(old.isStale, isTrue);
      expect(old.describe(), contains('3 jours'));
    });

    test('an undated snapshot is never treated as fresh', () {
      const undated = DataProvenance(DataOrigin.snapshot);
      // Unknown age must not read as "just now".
      expect(undated.isStale, isTrue);
      expect(undated.describe(), contains('âge inconnu'));
      expect(undated.age, isNull);
    });

    test('the decision_summary timestamp is read when present', () async {
      final client = ApiClient(
        baseUrl: 'https://api.example.com',
        client: StubClient((_) async => throw Exception('offline')),
        loadAsset: (_) async =>
            '{"decision_summary":{"generated_at":"2026-09-06T20:01:00Z"}}',
      );
      await client.today('BTC');
      expect(
          client.lastProvenance.generatedAt, DateTime.utc(2026, 9, 6, 20, 1));
    });
  });
}
