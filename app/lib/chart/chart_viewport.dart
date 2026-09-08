/// Le repère du graphique : temps ↔ x, prix ↔ y.
///
/// Le peintre précédent n'avait pas de fenêtre. Il prenait le minimum et le
/// maximum de **toutes** les bougies et les étalait sur la largeur disponible,
/// si bien qu'il n'existait aucun repère indépendant de la taille de l'écran :
/// rien à déplacer, rien à zoomer, et une annotation ne pouvait être posée
/// qu'en pixels — donc décrochée du chandelier dès le premier redimensionnement.
///
/// Ce viewport sépare deux choses que ce peintre confondait :
///
///   le **jeu de données**  toutes les bougies chargées
///   la **fenêtre visible** celles qui sont à l'écran maintenant
///
/// L'échelle verticale se calcule sur la fenêtre seule. Toute conversion passe
/// par les quatre fonctions ci-dessous, et rien d'autre n'a le droit de
/// calculer une position : c'est ce qui garantit qu'un support, une neckline
/// ou un point de figure restent collés aux mêmes bougies après un zoom, un
/// déplacement ou une rotation.
library;

import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/painting.dart';

import '../api/models.dart';

/// Bornes du zoom, en nombre de bougies visibles.
const int kMinVisibleCandles = 15;
const int kMaxVisibleCandles = 300;

/// Vue par défaut à l'ouverture et après un double tap.
const int kDefaultVisibleCandles = 80;

/// Marge verticale, en part de l'amplitude visible.
const double kPricePadding = 0.06;

@immutable
class ChartViewport {
  /// Le jeu complet. La fenêtre s'y déplace, il ne bouge jamais.
  final List<CandlePoint> candles;

  /// Index de la première bougie visible, et combien le sont.
  final int startIndex;
  final int visibleCount;

  /// La zone de dessin des prix, en pixels.
  final Rect plot;

  const ChartViewport({
    required this.candles,
    required this.startIndex,
    required this.visibleCount,
    required this.plot,
  });

  /// Une vue initiale raisonnable : les dernières bougies, pas tout le passé.
  factory ChartViewport.initial({
    required List<CandlePoint> candles,
    required Rect plot,
    int desired = kDefaultVisibleCandles,
  }) {
    final count = _clampCount(desired, candles.length);
    return ChartViewport(
      candles: candles,
      startIndex: math.max(0, candles.length - count),
      visibleCount: count,
      plot: plot,
    );
  }

  static int _clampCount(int desired, int total) {
    if (total <= 0) return 0;
    final upper = math.min(kMaxVisibleCandles, total);
    final lower = math.min(kMinVisibleCandles, total);
    return desired.clamp(lower, upper);
  }

  bool get isEmpty => candles.isEmpty || visibleCount <= 0;

  int get endIndex => math.min(candles.length, startIndex + visibleCount);

  /// Les bougies réellement à l'écran.
  List<CandlePoint> get visible =>
      isEmpty ? const [] : candles.sublist(startIndex, endIndex);

  DateTime? get visibleStartTime =>
      isEmpty ? null : candles[startIndex].time;

  DateTime? get visibleEndTime =>
      isEmpty ? null : candles[endIndex - 1].time;

  /// Largeur d'une bougie, espacement compris.
  double get candleWidth =>
      visibleCount <= 0 ? 0 : plot.width / visibleCount;

  // --- échelle verticale -------------------------------------------------
  //
  // Calculée sur la fenêtre seule. La calculer sur tout le jeu écrasait les
  // mouvements récents contre un extrême vieux de plusieurs années.

  double get _rawLow => visible.isEmpty
      ? 0
      : visible.map((c) => c.low).reduce(math.min);

  double get _rawHigh => visible.isEmpty
      ? 1
      : visible.map((c) => c.high).reduce(math.max);

  double get visibleMinPrice {
    final low = _rawLow, high = _rawHigh;
    final span = high - low;
    return low - (span > 0 ? span * kPricePadding : low.abs() * 0.01 + 1);
  }

  double get visibleMaxPrice {
    final low = _rawLow, high = _rawHigh;
    final span = high - low;
    return high + (span > 0 ? span * kPricePadding : high.abs() * 0.01 + 1);
  }

  // --- conversions -------------------------------------------------------

  /// Position horizontale du centre de la bougie d'index donné.
  ///
  /// L'index peut être fractionnaire : c'est ce qui permet de poser une
  /// annotation à un horodatage qui ne tombe pas exactement sur une bougie.
  double indexToX(double index) =>
      plot.left + (index - startIndex + 0.5) * candleWidth;

  double xToIndex(double x) =>
      candleWidth <= 0 ? 0 : (x - plot.left) / candleWidth - 0.5 + startIndex;

  /// Index fractionnaire d'un horodatage, interpolé entre deux bougies.
  ///
  /// Une géométrie de figure porte des horodatages réels, pas des index de
  /// barres : c'est ce qui la rend valable après un changement d'unité de
  /// temps ou de fenêtre.
  double timeToIndex(DateTime time) {
    if (candles.isEmpty) return 0;
    final target = time.toUtc();
    var low = 0, high = candles.length - 1;
    if (_timeAt(0) != null && target.isBefore(_timeAt(0)!)) {
      return _extrapolatedIndex(target, before: true);
    }
    if (_timeAt(high) != null && target.isAfter(_timeAt(high)!)) {
      return _extrapolatedIndex(target, before: false);
    }
    while (low < high - 1) {
      final mid = (low + high) ~/ 2;
      final at = _timeAt(mid);
      if (at == null) break;
      if (at.isAfter(target)) {
        high = mid;
      } else {
        low = mid;
      }
    }
    final a = _timeAt(low), b = _timeAt(high);
    if (a == null || b == null) return low.toDouble();
    final span = b.difference(a).inMilliseconds;
    if (span <= 0) return low.toDouble();
    final offset = target.difference(a).inMilliseconds / span;
    return low + offset.clamp(0.0, 1.0);
  }

  /// Hors du jeu de données, on prolonge à la cadence moyenne plutôt que de
  /// coller l'annotation au bord : une neckline projetée vers la droite doit
  /// sortir de l'écran, pas s'écraser sur la dernière bougie.
  double _extrapolatedIndex(DateTime target, {required bool before}) {
    final step = _averageStepMs;
    if (step <= 0) return before ? 0 : (candles.length - 1).toDouble();
    final anchorIndex = before ? 0 : candles.length - 1;
    final anchor = _timeAt(anchorIndex);
    if (anchor == null) return anchorIndex.toDouble();
    final delta = target.difference(anchor).inMilliseconds / step;
    return anchorIndex + delta;
  }

  double get _averageStepMs {
    if (candles.length < 2) return 0;
    final first = _timeAt(0), last = _timeAt(candles.length - 1);
    if (first == null || last == null) return 0;
    final span = last.difference(first).inMilliseconds;
    return span <= 0 ? 0 : span / (candles.length - 1);
  }

  DateTime? _timeAt(int index) {
    if (index < 0 || index >= candles.length) return null;
    return candles[index].time?.toUtc();
  }

  double timeToX(DateTime time) => indexToX(timeToIndex(time));

  /// Horodatage sous une abscisse, interpolé entre bougies.
  DateTime? xToTime(double x) {
    if (candles.isEmpty) return null;
    final index = xToIndex(x);
    final lower = index.floor().clamp(0, candles.length - 1);
    final upper = (lower + 1).clamp(0, candles.length - 1);
    final a = _timeAt(lower), b = _timeAt(upper);
    if (a == null) return null;
    if (b == null || upper == lower) return a;
    final fraction = (index - lower).clamp(0.0, 1.0);
    final span = b.difference(a).inMilliseconds;
    return a.add(Duration(milliseconds: (span * fraction).round()));
  }

  double priceToY(double price) {
    final min = visibleMinPrice, max = visibleMaxPrice;
    if (max <= min) return plot.center.dy;
    final ratio = (price - min) / (max - min);
    return plot.bottom - ratio * plot.height;
  }

  double yToPrice(double y) {
    final min = visibleMinPrice, max = visibleMaxPrice;
    if (plot.height <= 0) return min;
    final ratio = (plot.bottom - y) / plot.height;
    return min + ratio * (max - min);
  }

  /// La bougie sous une abscisse, ou null hors de la fenêtre.
  ///
  /// Bornée au visible, pas au jeu complet: une abscisse à gauche du cadre
  /// retombe arithmétiquement sur un index valide du jeu, et le crosshair
  /// aurait désigné une bougie qui n'est pas dessinée là.
  int? candleIndexAtX(double x) {
    if (isEmpty) return null;
    final index = xToIndex(x).round();
    if (index < startIndex || index >= endIndex) return null;
    return index;
  }

  // --- navigation --------------------------------------------------------

  /// Déplacement horizontal. Un glissement vers la droite remonte le temps.
  ChartViewport pannedByPixels(double dx) {
    if (isEmpty || candleWidth <= 0) return this;
    final shift = (-dx / candleWidth).round();
    if (shift == 0) return this;
    return copyWith(startIndex: _clampStart(startIndex + shift));
  }

  /// Zoom autour d'un point d'ancrage : ce qui est sous le doigt y reste.
  ChartViewport zoomedBy(double scale, double focalX) {
    if (isEmpty || scale <= 0) return this;
    final anchor = xToIndex(focalX);
    final count = _clampCount(
      (visibleCount / scale).round(),
      candles.length,
    );
    if (count == visibleCount) return this;
    // Fraction de la fenêtre occupée par l'ancre, préservée après le zoom.
    final fraction = visibleCount <= 0
        ? 0.5
        : ((anchor - startIndex) / visibleCount).clamp(0.0, 1.0);
    final start = (anchor - fraction * count).round();
    return copyWith(
      startIndex: _clampStart(start, count: count),
      visibleCount: count,
    );
  }

  /// Retour à une vue raisonnable : les dernières bougies.
  ChartViewport reset({int desired = kDefaultVisibleCandles}) =>
      ChartViewport.initial(candles: candles, plot: plot, desired: desired);

  int _clampStart(int start, {int? count}) {
    final window = count ?? visibleCount;
    final maxStart = math.max(0, candles.length - window);
    return start.clamp(0, maxStart);
  }

  ChartViewport copyWith({
    List<CandlePoint>? candles,
    int? startIndex,
    int? visibleCount,
    Rect? plot,
  }) {
    final data = candles ?? this.candles;
    final count = _clampCount(visibleCount ?? this.visibleCount, data.length);
    final maxStart = math.max(0, data.length - count);
    return ChartViewport(
      candles: data,
      startIndex: (startIndex ?? this.startIndex).clamp(0, maxStart),
      visibleCount: count,
      plot: plot ?? this.plot,
    );
  }

  /// Le viewport suit un changement de taille sans perdre sa fenêtre.
  ChartViewport withPlot(Rect value) =>
      value == plot ? this : copyWith(plot: value);

  // Égalité par valeur: `shouldRepaint` doit pouvoir dire que rien n'a bougé,
  // sinon chaque image repeint tout le graphique.
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is ChartViewport &&
          other.startIndex == startIndex &&
          other.visibleCount == visibleCount &&
          other.plot == plot &&
          identical(other.candles, candles);

  @override
  int get hashCode => Object.hash(startIndex, visibleCount, plot, candles.length);
}
