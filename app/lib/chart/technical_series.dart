/// Indicateurs calculés sur les bougies réellement affichées.
///
/// Les formules reproduisent celles du backend (`adjust=False` pour les EMA,
/// écart-type population pour Bollinger et lissage de Wilder pour le RSI).
/// Les zones de chauffe restent `null` : une valeur impossible à calculer
/// n'est jamais remplacée par zéro.
library;

import 'dart:math' as math;

import '../api/models.dart';

class TechnicalSeries {
  final List<double?> ema20;
  final List<double?> ema50;
  final List<double?> ema200;
  final List<double?> bbUpper;
  final List<double?> bbMiddle;
  final List<double?> bbLower;
  final List<double?> macd;
  final List<double?> macdSignal;
  final List<double?> macdHistogram;
  final List<double?> rsi;

  const TechnicalSeries({
    required this.ema20,
    required this.ema50,
    required this.ema200,
    required this.bbUpper,
    required this.bbMiddle,
    required this.bbLower,
    required this.macd,
    required this.macdSignal,
    required this.macdHistogram,
    required this.rsi,
  });

  factory TechnicalSeries.fromCandles(List<CandlePoint> candles) {
    final closes =
        candles.map((candle) => candle.close).toList(growable: false);
    final ema20 = _ema(closes, 20);
    final ema50 = _ema(closes, 50);
    final ema200 = _ema(closes, 200);
    final (upper, middle, lower) = _bollinger(closes, 20, 2);
    final ema12 = _ema(closes, 12);
    final ema26 = _ema(closes, 26);
    final macd = List<double?>.generate(closes.length, (index) {
      final fast = ema12[index], slow = ema26[index];
      return fast == null || slow == null ? null : fast - slow;
    }, growable: false);
    final signal = _emaNullable(macd, 9);
    final histogram = List<double?>.generate(closes.length, (index) {
      final line = macd[index], average = signal[index];
      return line == null || average == null ? null : line - average;
    }, growable: false);

    return TechnicalSeries(
      ema20: ema20,
      ema50: ema50,
      ema200: ema200,
      bbUpper: upper,
      bbMiddle: middle,
      bbLower: lower,
      macd: macd,
      macdSignal: signal,
      macdHistogram: histogram,
      rsi: _rsi(closes, 14),
    );
  }

  static const empty = TechnicalSeries(
    ema20: [],
    ema50: [],
    ema200: [],
    bbUpper: [],
    bbMiddle: [],
    bbLower: [],
    macd: [],
    macdSignal: [],
    macdHistogram: [],
    rsi: [],
  );
}

List<double?> _ema(List<double> values, int period) {
  if (values.isEmpty) return const [];
  final out = List<double?>.filled(values.length, null);
  final alpha = 2 / (period + 1);
  var average = values.first;
  for (var index = 0; index < values.length; index++) {
    if (index > 0) average = alpha * values[index] + (1 - alpha) * average;
    if (index >= period - 1) out[index] = average;
  }
  return out;
}

List<double?> _emaNullable(List<double?> values, int period) {
  final out = List<double?>.filled(values.length, null);
  final alpha = 2 / (period + 1);
  var seen = 0;
  double? average;
  for (var index = 0; index < values.length; index++) {
    final value = values[index];
    if (value == null || !value.isFinite) continue;
    average = average == null ? value : alpha * value + (1 - alpha) * average;
    seen += 1;
    if (seen >= period) out[index] = average;
  }
  return out;
}

(List<double?>, List<double?>, List<double?>) _bollinger(
  List<double> values,
  int period,
  double deviations,
) {
  final upper = List<double?>.filled(values.length, null);
  final middle = List<double?>.filled(values.length, null);
  final lower = List<double?>.filled(values.length, null);
  var sum = 0.0, squareSum = 0.0;
  for (var index = 0; index < values.length; index++) {
    final value = values[index];
    sum += value;
    squareSum += value * value;
    if (index >= period) {
      final removed = values[index - period];
      sum -= removed;
      squareSum -= removed * removed;
    }
    if (index < period - 1) continue;
    final mean = sum / period;
    final variance = math.max(0, squareSum / period - mean * mean);
    final deviation = math.sqrt(variance) * deviations;
    middle[index] = mean;
    upper[index] = mean + deviation;
    lower[index] = mean - deviation;
  }
  return (upper, middle, lower);
}

List<double?> _rsi(List<double> values, int period) {
  final out = List<double?>.filled(values.length, null);
  if (values.length <= period) return out;
  var gainSum = 0.0, lossSum = 0.0;
  for (var index = 1; index <= period; index++) {
    final delta = values[index] - values[index - 1];
    if (delta >= 0) {
      gainSum += delta;
    } else {
      lossSum -= delta;
    }
  }
  var averageGain = gainSum / period;
  var averageLoss = lossSum / period;
  out[period] = _rsiValue(averageGain, averageLoss);
  for (var index = period + 1; index < values.length; index++) {
    final delta = values[index] - values[index - 1];
    final gain = math.max(0, delta);
    final loss = math.max(0, -delta);
    averageGain = (averageGain * (period - 1) + gain) / period;
    averageLoss = (averageLoss * (period - 1) + loss) / period;
    out[index] = _rsiValue(averageGain, averageLoss);
  }
  return out;
}

double? _rsiValue(double gain, double loss) {
  if (loss == 0 && gain > 0) return 100;
  if (gain == 0 && loss > 0) return 0;
  if (gain == 0 && loss == 0) return null;
  final relativeStrength = gain / loss;
  return 100 - 100 / (1 + relativeStrength);
}
