/// Les bougies, récupérées par l'application elle-même.
///
/// L'app ouvre déjà une socket Kraken pour le prix au comptant : ce service
/// suit le même principe pour l'OHLCV. Il appelle l'endpoint public des
/// klines Binance — sans clé, sans contournement d'aucune protection, la même
/// source que le backend utilise déjà pour son historique.
///
/// Deux raisons de le faire côté client plutôt que d'attendre le backend :
///
///   * les bougies arrivent **en direct**, pas à la fraîcheur d'un instantané
///     exporté ;
///   * le moteur reçoit un millier de bougies là où l'instantané en portait
///     quelques dizaines, et un graphique qu'on peut déplacer a besoin de
///     plus de données que ce qu'il affiche.
///
/// L'analyse, elle, continue de venir du backend. Le graphique dessine des
/// bougies en direct et raconte une analyse datée : ce sont deux horloges,
/// et l'écran doit les distinguer plutôt que les confondre.
library;

import 'dart:convert';
import 'dart:math' as math;

import 'package:http/http.dart' as http;

import '../api/models.dart';

/// Le maximum que Binance sert en un appel. Au-delà, il faut paginer.
const int kBinanceKlineLimit = 1000;

/// Combien de bougies charger, par unité de temps.
///
/// Un millier de bougies suffisait à déplacer la vue, pas à voir l'histoire :
/// en hebdomadaire cela couvrait un an, alors que le moteur trouve des
/// figures jusqu'en 2018. Les cibles ci-dessous couvrent tout ce que Binance
/// conserve pour les grandes unités, et restent bornées sur les petites où
/// la profondeur n'apporterait que du poids.
///
///   1 sem. — 474 barres, soit l'intégralité depuis août 2017
///   1 j    — 3 400 barres, soit neuf ans
///   4 h    — 3 000 barres, soit un an et demi
///   1 h    — 2 000 barres, soit trois mois
///   15 min — 1 500 barres, soit seize jours
const Map<String, int> kCandleDepth = {
  '1w': 600,
  '1d': 3400,
  '4h': 3000,
  '1h': 2000,
  '15m': 1500,
};

/// Combien de bougies demander par défaut quand l'unité est inconnue.
const int kLiveCandleLimit = 1000;

int candleDepthFor(String timeframe) =>
    kCandleDepth[timeframe] ?? kLiveCandleLimit;

/// Ce que le graphique a reçu, et d'où.
class LiveCandles {
  final List<CandlePoint> candles;
  final String source;
  final String symbol;
  final DateTime fetchedAt;

  const LiveCandles({
    required this.candles,
    required this.source,
    required this.symbol,
    required this.fetchedAt,
  });

  bool get isEmpty => candles.isEmpty;

  /// Âge de la dernière bougie. Une bougie en cours est normale ; une bougie
  /// vieille de plusieurs périodes ne l'est pas, et l'écran doit pouvoir le
  /// dire plutôt que de présenter un graphique dormant comme du temps réel.
  Duration? get lastCandleAge {
    final last = candles.isEmpty ? null : candles.last.time;
    return last == null ? null : DateTime.now().toUtc().difference(last.toUtc());
  }
}

/// Erreur de récupération, nommée pour que l'écran puisse la dire.
class LiveCandlesUnavailable implements Exception {
  final String reason;
  const LiveCandlesUnavailable(this.reason);
  @override
  String toString() => reason;
}

class LiveCandleService {
  final http.Client _client;
  final Uri Function(String symbol, String interval, int limit) _endpoint;

  LiveCandleService({
    http.Client? client,
    Uri Function(String, String, int)? endpoint,
  })  : _client = client ?? http.Client(),
        _endpoint = endpoint ?? _binanceKlines;

  static Uri _binanceKlines(String symbol, String interval, int limit) =>
      Uri.https('api.binance.com', '/api/v3/klines', {
        'symbol': symbol,
        'interval': interval,
        'limit': '$limit',
      });

  /// Le même appel, borné dans le passé — c'est ce qui permet de paginer.
  static Uri _binanceKlinesBefore(
    String symbol,
    String interval,
    int limit,
    int endMillis,
  ) =>
      Uri.https('api.binance.com', '/api/v3/klines', {
        'symbol': symbol,
        'interval': interval,
        'limit': '$limit',
        'endTime': '$endMillis',
      });

  /// La paire cotée pour un actif. Le graphique affiche « BTC / USDT » : le
  /// libellé doit correspondre à ce qui a réellement été appelé.
  static String symbolFor(String asset) => switch (asset.toUpperCase()) {
        'BTC' => 'BTCUSDT',
        'ETH' => 'ETHUSDT',
        'SOL' => 'SOLUSDT',
        _ => '${asset.toUpperCase()}USDT',
      };

  /// L'intervalle Binance correspondant à une unité de l'application.
  static String? intervalFor(String timeframe) => switch (timeframe) {
        '15m' => '15m',
        '1h' => '1h',
        '4h' => '4h',
        '1d' => '1d',
        '1w' => '1w',
        _ => null,
      };

  Future<LiveCandles> fetch(
    String asset,
    String timeframe, {
    int? limit,
  }) async {
    final interval = intervalFor(timeframe);
    if (interval == null) {
      throw LiveCandlesUnavailable('Unité « $timeframe » non gérée en direct.');
    }
    final symbol = symbolFor(asset);
    final wanted = limit ?? candleDepthFor(timeframe);

    // Première page: les bougies les plus récentes.
    var candles = parseKlines(await _get(_endpoint(
      symbol, interval, math.min(wanted, kBinanceKlineLimit),
    )));
    if (candles.isEmpty) {
      return LiveCandles(
        candles: candles, source: 'Binance', symbol: symbol,
        fetchedAt: DateTime.now().toUtc(),
      );
    }

    // Puis on remonte, page par page, jusqu'à la profondeur voulue.
    //
    // `endTime` est inclusif chez Binance: on demande la barre juste avant la
    // plus ancienne obtenue, sinon chaque page rechargerait la précédente.
    // La boucle est bornée pour ne jamais tourner indéfiniment si la source
    // renvoie autre chose que ce qu'on attend.
    var guard = 0;
    while (candles.length < wanted && guard < 12) {
      guard++;
      final oldest = candles.first.time;
      if (oldest == null) break;
      final page = parseKlines(await _get(_binanceKlinesBefore(
        symbol,
        interval,
        math.min(wanted - candles.length, kBinanceKlineLimit),
        oldest.millisecondsSinceEpoch - 1,
      )));
      // Uniquement ce qui est réellement plus ancien. Une source qui renvoie
      // la même page indéfiniment ferait sinon grossir la série de copies,
      // et le graphique dessinerait douze fois les mêmes bougies.
      final older = page
          .where((candle) =>
              candle.time != null && candle.time!.isBefore(oldest))
          .toList();
      if (older.isEmpty) break;
      candles = [...older, ...candles];
    }

    return LiveCandles(
      candles: candles,
      source: 'Binance',
      symbol: symbol,
      fetchedAt: DateTime.now().toUtc(),
    );
  }

  Future<String> _get(Uri url) async {
    final http.Response response;
    try {
      response = await _client.get(url).timeout(const Duration(seconds: 12));
    } catch (error) {
      throw LiveCandlesUnavailable('Source de bougies injoignable ($error).');
    }
    if (response.statusCode != 200) {
      throw LiveCandlesUnavailable(
        'Source de bougies indisponible (HTTP ${response.statusCode}).',
      );
    }
    return response.body;
  }

  /// Une kline Binance est un tableau positionnel :
  /// `[ouverture, o, h, l, c, volume, fermeture, ...]`.
  ///
  /// Une ligne malformée est ignorée, jamais complétée : une bougie inventée
  /// au milieu d'un graphique est indétectable à l'œil.
  static List<CandlePoint> parseKlines(String body) {
    final decoded = jsonDecode(body);
    if (decoded is! List) return const [];
    final out = <CandlePoint>[];
    for (final row in decoded) {
      if (row is! List || row.length < 6) continue;
      final open = double.tryParse('${row[1]}');
      final high = double.tryParse('${row[2]}');
      final low = double.tryParse('${row[3]}');
      final close = double.tryParse('${row[4]}');
      final volume = double.tryParse('${row[5]}');
      final millis = row[0] is num ? (row[0] as num).toInt() : null;
      if (open == null ||
          high == null ||
          low == null ||
          close == null ||
          volume == null ||
          millis == null) {
        continue;
      }
      out.add(CandlePoint(
        time: DateTime.fromMillisecondsSinceEpoch(millis, isUtc: true),
        open: open,
        high: high,
        low: low,
        close: close,
        volume: volume,
      ));
    }
    return out;
  }

  void dispose() => _client.close();
}
