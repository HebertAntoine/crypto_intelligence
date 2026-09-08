/// Les bougies récupérées par l'app elle-même.
///
/// La règle du projet vaut ici comme ailleurs : aucune valeur n'est inventée.
/// Une ligne malformée est ignorée, pas complétée — une bougie fabriquée au
/// milieu d'un graphique est indétectable à l'œil.
library;

import 'dart:convert';

import 'package:crypto_intelligence_app/chart/live_candles.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// Une kline Binance est positionnelle: [ouverture, o, h, l, c, volume, ...].
List<dynamic> _kline(int millis, double base) => [
      millis,
      '$base',
      '${base + 5}',
      '${base - 5}',
      '${base + 2}',
      '123.45',
      millis + 1000,
      '0', 0, '0', '0', '0',
    ];

LiveCandleService _service(String body, {int status = 200}) => LiveCandleService(
      client: MockClient((_) async => http.Response(body, status)),
    );

void main() {
  group('Lecture des klines', () {
    test('une réponse valide devient des bougies exploitables', () async {
      final body = jsonEncode([
        _kline(1757000000000, 100),
        _kline(1757003600000, 110),
      ]);
      final result = await _service(body).fetch('BTC', '1h');
      expect(result.candles, hasLength(2));
      expect(result.candles.first.open, 100);
      expect(result.candles.first.high, 105);
      expect(result.candles.first.low, 95);
      expect(result.candles.first.close, 102);
      expect(result.candles.first.volume, 123.45);
      expect(result.candles.first.time!.isUtc, isTrue);
      expect(result.source, 'Binance');
      expect(result.symbol, 'BTCUSDT');
    });

    test('une ligne malformée est ignorée, pas complétée', () {
      final body = jsonEncode([
        _kline(1757000000000, 100),
        [1757003600000, 'abc', null, '5', '6', '7'],
        ['pas une bougie'],
        _kline(1757007200000, 120),
      ]);
      final candles = LiveCandleService.parseKlines(body);
      // Deux valides sur quatre lignes: rien n'est fabriqué pour combler.
      expect(candles, hasLength(2));
      expect(candles.map((c) => c.open), [100, 120]);
    });

    test('une réponse vide ne produit aucune bougie', () {
      expect(LiveCandleService.parseKlines('[]'), isEmpty);
      expect(LiveCandleService.parseKlines('{"code":-1}'), isEmpty);
    });
  });

  group('Erreurs nommées plutôt que silencieuses', () {
    test('un statut non 200 est dit', () async {
      await expectLater(
        _service('nope', status: 429).fetch('BTC', '1h'),
        throwsA(isA<LiveCandlesUnavailable>().having(
            (e) => e.reason, 'raison', contains('429'))),
      );
    });

    test('une panne réseau est dite', () async {
      final service = LiveCandleService(
        client: MockClient((_) async => throw const SocketExceptionStub()),
      );
      await expectLater(
        service.fetch('BTC', '1h'),
        throwsA(isA<LiveCandlesUnavailable>()),
      );
    });

    test('une unité non gérée est refusée avant tout appel', () async {
      var called = false;
      final service = LiveCandleService(
        client: MockClient((_) async {
          called = true;
          return http.Response('[]', 200);
        }),
      );
      await expectLater(
        service.fetch('BTC', '3m'),
        throwsA(isA<LiveCandlesUnavailable>()),
      );
      expect(called, isFalse);
    });
  });

  group('Correspondance des symboles et intervalles', () {
    test('chaque actif a sa paire cotée', () {
      expect(LiveCandleService.symbolFor('BTC'), 'BTCUSDT');
      expect(LiveCandleService.symbolFor('eth'), 'ETHUSDT');
      expect(LiveCandleService.symbolFor('SOL'), 'SOLUSDT');
    });

    test('les cinq unités de l’app ont un intervalle', () {
      for (final tf in ['15m', '1h', '4h', '1d', '1w']) {
        expect(LiveCandleService.intervalFor(tf), isNotNull, reason: tf);
      }
      expect(LiveCandleService.intervalFor('2h'), isNull);
    });

    test('l’appel demande assez de bougies pour pouvoir se déplacer', () async {
      late Uri seen;
      final service = LiveCandleService(
        client: MockClient((request) async {
          seen = request.url;
          return http.Response('[]', 200);
        }),
      );
      await service.fetch('BTC', '1w');
      expect(seen.queryParameters['symbol'], 'BTCUSDT');
      expect(seen.queryParameters['interval'], '1w');
      // La fenêtre en affiche 80: en charger mille est ce qui donne de la
      // matière au déplacement vers l'historique.
      expect(int.parse(seen.queryParameters['limit']!), kLiveCandleLimit);
      expect(kLiveCandleLimit, greaterThan(500));
    });
  });

  group('Fraîcheur', () {
    test('l’âge de la dernière bougie est mesuré, pas supposé', () {
      final now = DateTime.now().toUtc();
      final result = LiveCandles(
        candles: LiveCandleService.parseKlines(jsonEncode([
          _kline(now.subtract(const Duration(hours: 3))
              .millisecondsSinceEpoch, 100),
        ])),
        source: 'Binance',
        symbol: 'BTCUSDT',
        fetchedAt: now,
      );
      expect(result.lastCandleAge!.inHours, 3);
    });

    test('sans bougie, aucun âge n’est inventé', () {
      final result = LiveCandles(
        candles: const [],
        source: 'Binance',
        symbol: 'BTCUSDT',
        fetchedAt: DateTime.now().toUtc(),
      );
      expect(result.isEmpty, isTrue);
      expect(result.lastCandleAge, isNull);
    });
  });
}

class SocketExceptionStub implements Exception {
  const SocketExceptionStub();
}
