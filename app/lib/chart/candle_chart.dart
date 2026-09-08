/// Le graphique interactif : bougies, volume, axes, crosshair.
///
/// Tout passe par `ChartViewport`. Ce widget ne calcule aucune position : il
/// convertit des gestes en changements de fenêtre, et le peintre convertit la
/// fenêtre en pixels. C'est ce qui permet d'ajouter des overlays plus tard
/// sans qu'aucun d'eux ne connaisse la taille de l'écran.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../api/models.dart';
import 'chart_layers.dart';
import 'chart_viewport.dart';
import 'pattern_geometry.dart';

// Palette, conforme à l'identité de l'application.
const _background = Color(0xFF071827);
const _grid = Color(0xFF29445A);
const _bull = Color(0xFF32DF98);
const _bear = Color(0xFFFF5866);
const _textPrimary = Color(0xFFEDF4FF);
const _textSecondary = Color(0xFFB7C5D9);

/// Réserve à droite pour l'axe des prix, et en bas pour les dates.
const double _priceAxisWidth = 62;
// Deux lignes — « 4 sept. » puis « 14:00 » — plus l'interligne. À 22 px
// l'heure était coupée en deux par le bord du cadre.
const double _timeAxisHeight = 34;
const double _volumeFraction = 0.18;

/// Combien de figures portent leur nom à l'écran, au plus.
const int _maxNamedPatterns = 4;

class CandleChart extends StatefulWidget {
  final List<CandlePoint> candles;
  final ChartLayerSet layers;

  /// Unité de temps, pour formater les dates de l'axe et du crosshair.
  final String timeframe;

  /// La paire réellement appelée et sa source. Affichées telles quelles: le
  /// graphique ne doit jamais annoncer un fournisseur dont les données ne
  /// viennent pas.
  final String? pair;
  final String? source;

  /// La lecture structurelle du backend: zones, range, position.
  ///
  /// Le graphique ne détecte rien. Il reçoit des prix calculés ailleurs et les
  /// place dans son repère — c'est ce qui garantit que le dessin et l'analyse
  /// ne peuvent pas diverger.
  final StructuralLocation? location;

  /// Les figures détectées, avec leur géométrie en temps et en prix.
  ///
  /// Le graphique ne reconnaît aucune forme et n'en complète aucune : une
  /// figure sans géométrie n'est pas dessinée. C'est ce qui garantit que ce
  /// qui est tracé est exactement ce que le détecteur a vu.
  final List<StructuralPatternRead> patterns;

  const CandleChart({
    super.key,
    required this.candles,
    required this.timeframe,
    required this.layers,
    this.pair,
    this.source,
    this.location,
    this.patterns = const [],
  });

  @override
  State<CandleChart> createState() => _CandleChartState();
}

class _CandleChartState extends State<CandleChart> {
  ChartViewport? _viewport;
  Offset? _crosshair;

  // État du geste en cours. Le pincement et le glissement arrivent par le même
  // rappel: on garde la fenêtre de départ pour appliquer une transformation
  // absolue plutôt que d'accumuler des arrondis à chaque image.
  ChartViewport? _gestureStart;
  Offset? _gestureOrigin;

  @override
  void didUpdateWidget(CandleChart old) {
    super.didUpdateWidget(old);
    // Un changement d'actif ou d'unité repart d'une vue propre: conserver la
    // fenêtre reviendrait à montrer un intervalle qui n'a pas de sens dans le
    // nouveau jeu.
    if (!identical(old.candles, widget.candles)) {
      _viewport = null;
      _crosshair = null;
    }
  }

  ChartViewport _ensureViewport(Rect plot) {
    final current = _viewport;
    if (current == null || current.candles.length != widget.candles.length) {
      return _viewport = ChartViewport.initial(
        candles: widget.candles,
        plot: plot,
      );
    }
    return _viewport = current.withPlot(plot);
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final size = Size(constraints.maxWidth, constraints.maxHeight);
        final full = Offset.zero & size;
        final body = Rect.fromLTRB(
          full.left,
          full.top,
          full.right - _priceAxisWidth,
          full.bottom - _timeAxisHeight,
        );
        final volumeHeight =
            widget.layers.isVisible(ChartLayer.volume) ? body.height * _volumeFraction : 0.0;
        final plot = Rect.fromLTRB(
          body.left, body.top, body.right, body.bottom - volumeHeight,
        );
        final viewport = _ensureViewport(plot);

        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onScaleStart: (details) {
            _gestureStart = _viewport;
            _gestureOrigin = details.localFocalPoint;
          },
          onScaleUpdate: (details) {
            final start = _gestureStart;
            final origin = _gestureOrigin;
            if (start == null || origin == null) return;
            // Zoom d'abord, déplacement ensuite: l'inverse ferait glisser la
            // vue pendant qu'elle change d'échelle.
            var next = start;
            if ((details.scale - 1).abs() > 0.01) {
              next = start.zoomedBy(details.scale, origin.dx);
            }
            final dx = details.localFocalPoint.dx - origin.dx;
            if (dx.abs() > 0.5) next = next.pannedByPixels(dx);
            if (next != _viewport) setState(() => _viewport = next);
          },
          onScaleEnd: (_) {
            _gestureStart = null;
            _gestureOrigin = null;
          },
          onDoubleTap: () => setState(() {
            _viewport = _viewport?.reset();
            _crosshair = null;
          }),
          onLongPressStart: (details) =>
              setState(() => _crosshair = details.localPosition),
          onLongPressMoveUpdate: (details) =>
              setState(() => _crosshair = details.localPosition),
          onLongPressEnd: (_) => setState(() => _crosshair = null),
          child: CustomPaint(
            size: size,
            painter: CandleChartPainter(
              viewport: viewport,
              layers: widget.layers,
              body: body,
              crosshair: _crosshair,
              timeframe: widget.timeframe,
              pair: widget.pair,
              source: widget.source,
              location: widget.location,
              patterns: widget.patterns,
            ),
          ),
        );
      },
    );
  }
}

/// Le peintre. Public pour être testable: c'est le seul endroit qui convertit
/// une géométrie en pixels, donc le seul endroit où l'on peut vérifier qu'une
/// figure reste accrochée à ses bougies quand la fenêtre change.
class CandleChartPainter extends CustomPainter {
  final ChartViewport viewport;
  final ChartLayerSet layers;
  final Rect body;
  final Offset? crosshair;
  final String timeframe;
  final String? pair;
  final String? source;
  final StructuralLocation? location;
  final List<StructuralPatternRead> patterns;

  CandleChartPainter({
    required this.viewport,
    required this.layers,
    required this.body,
    required this.crosshair,
    required this.timeframe,
    this.pair,
    this.source,
    this.location,
    this.patterns = const [],
  });

  Rect get _plot => viewport.plot;
  Rect get _volume => Rect.fromLTRB(body.left, _plot.bottom, body.right, body.bottom);

  /// Les rectangles déjà occupés par une étiquette, pour cette image.
  ///
  /// Deux annotations superposées ne se lisent ni l'une ni l'autre. Le registre
  /// est vidé à chaque peinture: une position libre dépend de la fenêtre
  /// courante, pas de la précédente.
  final List<Rect> _taken = [];

  @override
  void paint(Canvas canvas, Size size) {
    _taken.clear();
    canvas.drawRect(Offset.zero & size, Paint()..color = _background);
    if (viewport.isEmpty) {
      _paintEmpty(canvas, size);
      return;
    }
    // L'ordre est celui de `ChartLayer`: chaque élément a sa place et une
    // seule.
    if (layers.isVisible(ChartLayer.grid)) _paintGrid(canvas);
    if (layers.isVisible(ChartLayer.volume)) _paintVolume(canvas);
    // Les zones passent sous les bougies: elles décrivent un contexte, elles
    // ne doivent pas masquer le prix.
    if (layers.isVisible(ChartLayer.range)) _paintRange(canvas);
    if (layers.isVisible(ChartLayer.levels)) _paintZones(canvas);
    if (layers.isVisible(ChartLayer.candles)) _paintCandles(canvas);
    // Les figures passent au-dessus des bougies: elles décrivent ces bougies
    // précisément, les glisser dessous les rendrait illisibles.
    if (layers.isVisible(ChartLayer.patternGeometry)) _paintPatterns(canvas);
    if (layers.isVisible(ChartLayer.currentPrice)) _paintCurrentPrice(canvas);
    if (layers.isVisible(ChartLayer.labels)) {
      _paintPriceAxis(canvas, size);
      _paintTimeAxis(canvas, size);
      _paintHeader(canvas);
      if (layers.isVisible(ChartLayer.patternGeometry)) {
        _paintPatternLabels(canvas);
      }
      if (layers.isVisible(ChartLayer.range)) _paintRangeLabels(canvas);
      if (layers.isVisible(ChartLayer.levels)) _paintZoneLabels(canvas);
    }
    if (crosshair != null) _paintCrosshair(canvas, size);
  }

  void _paintEmpty(Canvas canvas, Size size) {
    _text(
      canvas,
      'Aucune bougie disponible pour cette vue.',
      Offset(size.width / 2, size.height / 2),
      const TextStyle(color: _textSecondary, fontSize: 15),
      align: TextAlign.center,
      anchor: _Anchor.center,
    );
  }

  /// L'identité de ce qui est dessiné, en haut à gauche.
  ///
  /// La paire et la source viennent de l'appel réellement effectué. Le prix et
  /// la variation se lisent sur la dernière bougie **visible**, pas sur la
  /// dernière du jeu: en remontant l'historique, l'en-tête doit décrire ce
  /// qu'on regarde.
  void _paintHeader(Canvas canvas) {
    final last = viewport.candles[viewport.endIndex - 1];
    final first = viewport.candles[viewport.startIndex];
    final change = first.close == 0
        ? 0.0
        : (last.close - first.close) / first.close * 100;
    final rising = change >= 0;
    final colour = rising ? _bull : _bear;
    var dy = _plot.top + 4;
    var width = 0.0;

    void line(String value, TextStyle style, double advance) {
      final painter = _painter(value, style);
      painter.paint(canvas, Offset(_plot.left + 6, dy));
      width = math.max(width, painter.width);
      dy += advance;
    }

    final title = [pair, _timeframeLabel]
        .whereType<String>()
        .where((part) => part.isNotEmpty)
        .join(' · ');
    if (title.isNotEmpty) {
      line(
        title,
        const TextStyle(
            color: _textPrimary, fontSize: 11.5, fontWeight: FontWeight.w800),
        14,
      );
    }
    if (source != null && source!.isNotEmpty) {
      line(source!, const TextStyle(color: Color(0xFF7790A8), fontSize: 10), 13);
    }
    line(
      _price(last.close),
      const TextStyle(
          color: _textPrimary, fontSize: 11.5, fontWeight: FontWeight.w700),
      13,
    );
    // La variation dit sur quoi elle porte. Elle se mesure entre la première
    // et la dernière bougie **visibles**, donc elle change quand on zoome:
    // sans cette mention, un cadrage de trois mois se lisait comme la
    // variation du jour.
    line(
      '${rising ? '+' : ''}'
      '${change.toStringAsFixed(2).replaceAll('.', ',')} % sur la vue',
      TextStyle(color: colour, fontSize: 11, fontWeight: FontWeight.w700),
      4,
    );

    // L'en-tête est prioritaire: les étiquettes qui suivent se décalent
    // plutôt que de se poser dessus.
    _taken.add(
      Rect.fromLTRB(_plot.left, _plot.top, _plot.left + width + 14, dy),
    );
  }

  String get _timeframeLabel => switch (timeframe) {
        '15m' => '15 min',
        '1h' => '1 h',
        '4h' => '4 h',
        '1d' => '1 j',
        '1w' => '1 sem.',
        _ => timeframe,
      };

  // --- calque 0 : grille --------------------------------------------------

  void _paintGrid(Canvas canvas) {
    final paint = Paint()
      ..color = _grid.withValues(alpha: 0.30)
      ..strokeWidth = 1;
    for (final price in _priceTicks()) {
      final y = viewport.priceToY(price);
      if (y < _plot.top || y > _plot.bottom) continue;
      canvas.drawLine(Offset(_plot.left, y), Offset(_plot.right, y), paint);
    }
    for (final index in _timeTicks()) {
      final x = viewport.indexToX(index.toDouble());
      canvas.drawLine(Offset(x, _plot.top), Offset(x, body.bottom), paint);
    }
  }

  /// Bornes de prix « rondes », adaptées à l'amplitude visible.
  List<double> _priceTicks() {
    final min = viewport.visibleMinPrice, max = viewport.visibleMaxPrice;
    final span = max - min;
    if (span <= 0) return const [];
    final rough = span / 5;
    final magnitude = math.pow(10, (math.log(rough) / math.ln10).floor()).toDouble();
    final step = [1.0, 2.0, 2.5, 5.0, 10.0]
        .map((m) => m * magnitude)
        .firstWhere((s) => s >= rough, orElse: () => magnitude * 10);
    final ticks = <double>[];
    for (var v = (min / step).ceil() * step; v <= max; v += step) {
      ticks.add(v);
    }
    return ticks;
  }

  /// Le nombre d'étiquettes s'adapte à la largeur: pas de chevauchement.
  List<int> _timeTicks() {
    final maxLabels = math.max(2, (_plot.width / 84).floor());
    final step = math.max(1, (viewport.visibleCount / maxLabels).ceil());
    final ticks = <int>[];
    for (var i = viewport.startIndex; i < viewport.endIndex; i += step) {
      ticks.add(i);
    }
    return ticks;
  }

  // --- calque 1 : bougies -------------------------------------------------

  void _paintCandles(Canvas canvas) {
    final width = viewport.candleWidth;
    // Corps proportionnel à l'espacement, jamais plus épais que lisible.
    final bodyWidth = math.max(1.0, math.min(width * 0.7, 18.0));
    for (var i = viewport.startIndex; i < viewport.endIndex; i++) {
      final candle = viewport.candles[i];
      final rising = candle.close >= candle.open;
      final colour = rising ? _bull : _bear;
      final x = viewport.indexToX(i.toDouble());
      final highY = viewport.priceToY(candle.high);
      final lowY = viewport.priceToY(candle.low);
      canvas.drawLine(
        Offset(x, highY),
        Offset(x, lowY),
        Paint()
          ..color = colour.withValues(alpha: 0.72)
          ..strokeWidth = math.max(1.0, bodyWidth * 0.18),
      );
      final openY = viewport.priceToY(candle.open);
      final closeY = viewport.priceToY(candle.close);
      final top = math.min(openY, closeY);
      final height = math.max(1.0, (openY - closeY).abs());
      canvas.drawRect(
        Rect.fromLTWH(x - bodyWidth / 2, top, bodyWidth, height),
        Paint()..color = colour,
      );
    }
  }

  // --- calque 2 : volume --------------------------------------------------

  void _paintVolume(Canvas canvas) {
    final area = _volume;
    if (area.height <= 2) return;
    final visible = viewport.visible;
    if (visible.isEmpty) return;
    final peak = visible.map((c) => c.volume).reduce(math.max);
    if (peak <= 0) return;
    final width = math.max(1.0, math.min(viewport.candleWidth * 0.7, 18.0));
    for (var i = viewport.startIndex; i < viewport.endIndex; i++) {
      final candle = viewport.candles[i];
      final x = viewport.indexToX(i.toDouble());
      final height = (candle.volume / peak) * (area.height - 2);
      canvas.drawRect(
        Rect.fromLTWH(x - width / 2, area.bottom - height, width, height),
        Paint()
          ..color = (candle.close >= candle.open
                  ? const Color(0xFF258D72)
                  : const Color(0xFFA84857))
              .withValues(alpha: 0.75),
      );
    }
  }

  // --- calques 5 et 6 : zones et range -------------------------------------
  //
  // Rien n'est inventé ici. Une zone porte ses bornes basse et haute telles
  // que le moteur les a calculées; dessiner une bande d'épaisseur arbitraire
  // autour d'un prix unique aurait été une précision fabriquée.

  DetectedRange? get _range {
    final detected = location?.range;
    return (detected != null && detected.valid) ? detected : null;
  }

  /// Le range: une bande légère entre ses deux zones, et son milieu.
  void _paintRange(Canvas canvas) {
    final range = _range;
    final top = range?.topZone, bottom = range?.bottomZone;
    if (top == null || bottom == null) return;

    final upper = viewport.priceToY(top.midpoint);
    final lower = viewport.priceToY(bottom.midpoint);
    final band = Rect.fromLTRB(
      _plot.left, math.min(upper, lower), _plot.right, math.max(upper, lower),
    );
    final clipped = band.intersect(_plot);
    if (clipped.height <= 0) return;
    canvas.drawRect(
      clipped,
      Paint()..color = const Color(0xFF6B79FF).withValues(alpha: 0.05),
    );
    for (final y in [upper, lower]) {
      if (y < _plot.top || y > _plot.bottom) continue;
      canvas.drawLine(
        Offset(_plot.left, y), Offset(_plot.right, y),
        Paint()
          ..color = const Color(0xFF6B79FF).withValues(alpha: 0.5)
          ..strokeWidth = 1.2,
      );
    }
    // Le milieu, en pointillés: c'est un repère, pas une borne.
    final middle = viewport.priceToY((top.midpoint + bottom.midpoint) / 2);
    if (middle >= _plot.top && middle <= _plot.bottom) {
      final paint = Paint()
        ..color = const Color(0xFF6FAEFF).withValues(alpha: 0.45)
        ..strokeWidth = 1;
      for (var x = _plot.left; x < _plot.right; x += 10) {
        canvas.drawLine(
            Offset(x, middle), Offset(math.min(x + 5, _plot.right), middle), paint);
      }
    }
  }

  /// Support et résistance: des bandes réelles, `low` à `high`.
  void _paintZones(Canvas canvas) {
    final range = _range;
    for (final zone in [range?.bottomZone, range?.topZone]) {
      if (zone == null) continue;
      final support = zone.kind == 'support';
      final colour = support ? const Color(0xFF25D98F) : const Color(0xFFFF5964);
      final top = viewport.priceToY(zone.high);
      final bottom = viewport.priceToY(zone.low);
      final band = Rect.fromLTRB(
        _plot.left, math.min(top, bottom), _plot.right, math.max(top, bottom),
      ).intersect(_plot);
      if (band.height <= 0 || band.width <= 0) continue;
      canvas.drawRect(band, Paint()..color = colour.withValues(alpha: 0.13));
      canvas.drawRect(
        band,
        Paint()
          ..color = colour.withValues(alpha: 0.75)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1,
      );
    }
  }

  void _paintRangeLabels(Canvas canvas) {
    final range = _range;
    final top = range?.topZone, bottom = range?.bottomZone;
    if (top == null || bottom == null) return;
    final middle = viewport.priceToY((top.midpoint + bottom.midpoint) / 2);
    if (middle < _plot.top + 8 || middle > _plot.bottom - 8) return;
    _tag(canvas, Offset(_plot.left + 8, middle - 7), 'MILIEU DU RANGE',
        const Color(0xFF6FAEFF));
  }

  /// L'étiquette porte le prix médian de la zone, pas une borne choisie.
  void _paintZoneLabels(Canvas canvas) {
    final range = _range;
    for (final zone in [range?.bottomZone, range?.topZone]) {
      if (zone == null) continue;
      final support = zone.kind == 'support';
      final y = viewport.priceToY(zone.midpoint);
      if (y < _plot.top + 8 || y > _plot.bottom - 8) continue;
      _tag(
        canvas,
        Offset(_plot.right - 6, y - 7),
        '${support ? 'SUPPORT' : 'RÉSISTANCE'} ${_price(zone.midpoint)}',
        support ? const Color(0xFF25D98F) : const Color(0xFFFF5964),
        rightAligned: true,
      );
    }
    _paintPositionTag(canvas);
  }

  /// « 85 % du range », posé près du prix courant.
  void _paintPositionTag(Canvas canvas) {
    final position = location?.relativePosition;
    if (position == null || _range == null) return;
    final last = viewport.candles[viewport.endIndex - 1];
    final y = viewport.priceToY(last.close);
    if (y < _plot.top + 22 || y > _plot.bottom - 8) return;
    _tag(
      canvas,
      Offset(_plot.right - 6, y - 22),
      '${(position.clamp(0.0, 1.0) * 100).round()} % DU RANGE',
      const Color(0xFF8DCAFF),
      rightAligned: true,
    );
  }

  /// Une étiquette compacte sur fond opaque: sans fond, elle se perd dans les
  /// bougies dès que la zone en croise une.
  void _tag(Canvas canvas, Offset at, String label, Color colour,
      {bool rightAligned = false}) {
    final painter = _painter(
      label,
      TextStyle(color: colour, fontSize: 9.5, fontWeight: FontWeight.w800),
    );
    final left = rightAligned ? at.dx - painter.width - 8 : at.dx;
    final wanted =
        Rect.fromLTWH(left, at.dy, painter.width + 8, painter.height + 3);
    if (wanted.left < _plot.left || wanted.right > _plot.right) return;
    final rect = _freeSlot(wanted);
    if (rect == null) return;
    canvas.drawRRect(
      RRect.fromRectAndRadius(rect, const Radius.circular(3)),
      Paint()..color = const Color(0xFF071827).withValues(alpha: 0.82),
    );
    painter.paint(canvas, Offset(rect.left + 4, rect.top + 1.5));
    _taken.add(rect);
  }

  /// La première place libre à partir de celle demandée, ou aucune.
  ///
  /// Deux étiquettes superposées ne se lisent ni l'une ni l'autre; celle qui
  /// arrive après se décale verticalement, et renonce plutôt que de recouvrir
  /// une voisine. Renoncer est honnête: l'information reste dans les fiches
  /// en dessous, alors qu'un empilement illisible ne serait nulle part.
  Rect? _freeSlot(Rect wanted) {
    const step = 15.0;
    for (var attempt = 0; attempt < 9; attempt++) {
      final dy = attempt.isEven
          ? step * (attempt ~/ 2)
          : -step * ((attempt + 1) ~/ 2);
      final candidate = wanted.shift(Offset(0, dy));
      if (candidate.top < _plot.top + 2) continue;
      if (candidate.bottom > _plot.bottom - 2) continue;
      if (_taken.any(candidate.overlaps)) continue;
      return candidate;
    }
    return null;
  }

  // --- calque 6 : figures --------------------------------------------------

  /// Les figures, telles que le détecteur les a décrites.
  ///
  /// Rien n'est déduit ici. Chaque point, chaque droite, chaque aire arrive du
  /// backend avec un horodatage et un prix; le peintre ne fait que les
  /// convertir en pixels. C'est ce qui garde le tracé collé aux bougies quand
  /// la fenêtre bouge, et ce qui interdit au graphique de « voir » une figure
  /// que l'analyse n'a pas vue.
  /// Les figures qui croisent l'intervalle affiché, les plus récentes en
  /// dernier.
  ///
  /// Le backend renvoie l'historique — jusqu'à trente-cinq figures sur une
  /// vue. Toutes les tracer quel que soit le zoom donnerait une bouillie de
  /// rectangles ; filtrer sur la fenêtre est gratuit, puisqu'elle connaît ses
  /// propres bornes de temps, et c'est ce que le lecteur attend : en zoomant,
  /// il ne reste que ce qu'il regarde.
  List<StructuralPatternRead> get _visiblePatterns {
    if (patterns.isEmpty || viewport.isEmpty) return const [];
    final first = viewport.candles[viewport.startIndex].time;
    final last = viewport.candles[viewport.endIndex - 1].time;
    if (first == null || last == null) return patterns;
    return patterns
        .where((pattern) => pattern.isDrawable && pattern.overlaps(first, last))
        .toList();
  }

  void _paintPatterns(Canvas canvas) {
    final visible = _visiblePatterns;
    if (visible.isEmpty) return;
    canvas.save();
    canvas.clipRect(_plot);
    for (final pattern in visible) {
      final colour = _patternColour(pattern);
      // Aires d'abord, droites ensuite, points en dernier: un point posé sur
      // une droite doit rester visible.
      for (final zone in pattern.geometry.drawableZones) {
        _paintGeometryZone(canvas, zone, colour);
      }
      for (final line in pattern.geometry.drawableLines) {
        _paintGeometryLine(canvas, line, colour);
      }
      for (final point in pattern.geometry.points) {
        _paintGeometryPoint(canvas, point, colour);
      }
    }
    canvas.restore();
  }

  /// La couleur dit ce que **la théorie** associe à la forme, rien de plus.
  ///
  /// Elle ne dit pas ce que le système attend du prix: cette question a sa
  /// propre réponse, `edge_state`, et elle est le plus souvent « jamais
  /// testée ».
  Color _patternColour(StructuralPatternRead pattern) =>
      switch (pattern.directionIfTextbook) {
        'BULLISH' => _bull,
        'BEARISH' => _bear,
        _ => const Color(0xFF9B8CFF),
      };

  void _paintGeometryZone(Canvas canvas, GeometryZone zone, Color colour) {
    final left = viewport.timeToX(zone.startTime);
    final right = viewport.timeToX(zone.endTime);
    final top = viewport.priceToY(zone.high);
    final bottom = viewport.priceToY(zone.low);
    final rect = Rect.fromLTRB(
      math.min(left, right),
      math.min(top, bottom),
      math.max(left, right),
      math.max(top, bottom),
    );
    if (rect.width <= 0 || rect.height <= 0) return;
    canvas.drawRect(rect, Paint()..color = colour.withValues(alpha: 0.07));
    canvas.drawRect(
      rect,
      Paint()
        ..color = colour.withValues(alpha: 0.34)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1,
    );
  }

  void _paintGeometryLine(Canvas canvas, GeometryLine line, Color colour) {
    final from = Offset(
      viewport.timeToX(line.start.time),
      viewport.priceToY(line.start.price),
    );
    var to = Offset(
      viewport.timeToX(line.end.time),
      viewport.priceToY(line.end.price),
    );
    // `extend` prolonge vers la droite du cadre. Le backend décide: la borne
    // d'un triangle garde un sens après la dernière barre, une droite tracée
    // entre deux sommets achevés non. Le graphique n'en juge pas.
    if (line.extend && to.dx > from.dx) {
      final slope = (to.dy - from.dy) / (to.dx - from.dx);
      to = Offset(_plot.right, to.dy + slope * (_plot.right - to.dx));
    }
    _dashedLine(
      canvas,
      from,
      to,
      Paint()
        ..color = colour.withValues(alpha: 0.9)
        ..strokeWidth = 1.4,
    );
  }

  /// Pointillés: une droite construite par un détecteur n'est pas un prix
  /// observé, et ne doit pas se lire comme un trait plein.
  void _dashedLine(Canvas canvas, Offset from, Offset to, Paint paint) {
    final total = (to - from).distance;
    if (total <= 0) return;
    final step = (to - from) / total;
    for (var travelled = 0.0; travelled < total; travelled += 9) {
      final end = math.min(travelled + 5, total);
      canvas.drawLine(from + step * travelled, from + step * end, paint);
    }
  }

  void _paintGeometryPoint(Canvas canvas, GeometryPoint point, Color colour) {
    final at = Offset(
      viewport.timeToX(point.time),
      viewport.priceToY(point.price),
    );
    canvas.drawCircle(at, 4.5, Paint()..color = _background);
    canvas.drawCircle(
      at,
      4.5,
      Paint()
        ..color = colour
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.8,
    );
  }

  /// Les noms: la figure, ses points, ses droites.
  ///
  /// Sur le calque des étiquettes, comme les zones — on doit pouvoir garder
  /// les tracés et enlever le texte quand le graphique se charge.
  void _paintPatternLabels(Canvas canvas) {
    // Nommer trente figures rendrait le graphique illisible, et `_freeSlot`
    // finirait par toutes les refuser sans dire lesquelles. On nomme les plus
    // récentes — celles qui décrivent le prix d'aujourd'hui — et le compte
    // total est affiché sous le graphique.
    final visible = _visiblePatterns;
    final named = visible.length <= _maxNamedPatterns
        ? visible
        : visible.sublist(visible.length - _maxNamedPatterns);

    for (final pattern in patterns) {
      final colour = _patternColour(pattern);
      if (!pattern.isDrawable) {
        // Détectée mais sans géométrie: le détecteur n'a pas fourni de quoi la
        // tracer. Le dire vaut mieux que laisser le lecteur chercher une
        // figure absente du dessin alors que la fiche en dessous l'annonce.
        _tag(
          canvas,
          Offset(_plot.left + 8, _plot.bottom - 16),
          '${pattern.label.toUpperCase()} · TRACÉ NON FOURNI',
          const Color(0xFF8FA3BC),
        );
        continue;
      }
      if (!named.contains(pattern)) continue;
      // Le nom, l'état, et ce que vaut la forme face au hasard. Afficher
      // « DOUBLE SOMMET » seul le ferait lire comme une découverte alors que
      // la mesure dit qu'une marche aléatoire en produit autant.
      final noise = pattern.isNoDifferentFromNoise ? ' · = HASARD' : '';
      _tag(
        canvas,
        Offset(_plot.right - 6, _plot.top + 4),
        '${pattern.label.toUpperCase()} · ${pattern.stateLabel}$noise',
        pattern.isNoDifferentFromNoise ? const Color(0xFF8FA3BC) : colour,
        rightAligned: true,
      );
      for (final point in pattern.geometry.points) {
        final label = point.label;
        if (label.isEmpty) continue;
        final x = viewport.timeToX(point.time);
        if (x < _plot.left || x > _plot.right) continue;
        _tag(
          canvas,
          Offset(x - 16, viewport.priceToY(point.price) - 20),
          label,
          colour,
        );
      }
      for (final line in pattern.geometry.drawableLines) {
        final label = line.label;
        if (label.isEmpty) continue;
        _tag(
          canvas,
          Offset(_plot.right - 6, viewport.priceToY(line.end.price) + 4),
          label,
          colour,
          rightAligned: true,
        );
      }
    }
  }

  // --- calque 9 : prix courant --------------------------------------------

  void _paintCurrentPrice(Canvas canvas) {
    final last = viewport.candles[viewport.endIndex - 1];
    final previous = viewport.endIndex >= 2
        ? viewport.candles[viewport.endIndex - 2]
        : null;
    final rising = previous == null || last.close >= previous.close;
    final colour = rising ? _bull : _bear;
    final y = viewport.priceToY(last.close);
    if (y < _plot.top || y > _plot.bottom) return;

    final dash = Paint()
      ..color = colour.withValues(alpha: 0.75)
      ..strokeWidth = 1;
    for (var x = _plot.left; x < _plot.right; x += 8) {
      canvas.drawLine(Offset(x, y), Offset(math.min(x + 4, _plot.right), y), dash);
    }
    _badge(canvas, Offset(_plot.right + 4, y), _price(last.close), colour,
        rising ? const Color(0xFF04271C) : const Color(0xFF2A0710));
  }

  // --- calque 8 : axes ----------------------------------------------------

  void _paintPriceAxis(Canvas canvas, Size size) {
    for (final price in _priceTicks()) {
      final y = viewport.priceToY(price);
      if (y < _plot.top + 6 || y > _plot.bottom - 6) continue;
      _text(
        canvas,
        _price(price),
        Offset(_plot.right + 6, y),
        const TextStyle(color: Color(0xFFBECDE0), fontSize: 10.5),
        anchor: _Anchor.centerLeft,
      );
    }
  }

  void _paintTimeAxis(Canvas canvas, Size size) {
    for (final index in _timeTicks()) {
      final time = viewport.candles[index].time;
      if (time == null) continue;
      final x = viewport.indexToX(index.toDouble());
      if (x < _plot.left + 20 || x > _plot.right - 20) continue;
      _text(
        canvas,
        _date(time.toLocal()),
        Offset(x, body.bottom + 4),
        const TextStyle(color: Color(0xFF7790A8), fontSize: 10),
        anchor: _Anchor.topCenter,
      );
    }
  }

  // --- calque 10 : crosshair ----------------------------------------------

  void _paintCrosshair(Canvas canvas, Size size) {
    final point = crosshair!;
    final index = viewport.candleIndexAtX(point.dx);
    if (index == null) return;
    final candle = viewport.candles[index];
    // Accroché à la bougie, pas au doigt: le trait vertical doit désigner une
    // bougie précise, pas un pixel entre deux.
    final x = viewport.indexToX(index.toDouble());
    final y = point.dy.clamp(_plot.top, _plot.bottom);

    final line = Paint()
      ..color = const Color(0xFF8DCAFF).withValues(alpha: 0.55)
      ..strokeWidth = 1;
    for (var dy = _plot.top; dy < body.bottom; dy += 7) {
      canvas.drawLine(Offset(x, dy), Offset(x, math.min(dy + 3.5, body.bottom)), line);
    }
    for (var dx = _plot.left; dx < _plot.right; dx += 7) {
      canvas.drawLine(Offset(dx, y), Offset(math.min(dx + 3.5, _plot.right), y), line);
    }
    _badge(canvas, Offset(_plot.right + 4, y), _price(viewport.yToPrice(y)),
        const Color(0xFF8DCAFF), const Color(0xFF04182B));
    _paintReadout(canvas, candle, size);
  }

  /// L'encadré OHLC. Placé du côté opposé au doigt pour ne pas être masqué.
  void _paintReadout(Canvas canvas, CandlePoint candle, Size size) {
    final time = candle.time?.toLocal();
    final rising = candle.close >= candle.open;
    final lines = <(String, String, Color)>[
      ('O', _price(candle.open), _textPrimary),
      ('H', _price(candle.high), _bull),
      ('L', _price(candle.low), _bear),
      ('C', _price(candle.close), rising ? _bull : _bear),
      ('Vol.', _volumeLabel(candle.volume), _textSecondary),
    ];
    const width = 138.0, lineHeight = 14.0, padding = 8.0;
    final height = padding * 2 + 16 + lines.length * lineHeight;
    final left = (crosshair!.dx > size.width / 2)
        ? _plot.left + 6
        : _plot.right - width - 6;
    final rect = Rect.fromLTWH(left, _plot.top + 6, width, height);
    canvas.drawRRect(
      RRect.fromRectAndRadius(rect, const Radius.circular(8)),
      Paint()..color = const Color(0xFF091B2B).withValues(alpha: 0.94),
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(rect, const Radius.circular(8)),
      Paint()
        ..color = const Color(0xFF264966)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1,
    );
    if (time != null) {
      _text(canvas, _dateTime(time), Offset(rect.left + padding, rect.top + padding),
          const TextStyle(color: _textSecondary, fontSize: 10.5));
    }
    var dy = rect.top + padding + 16;
    for (final (label, value, colour) in lines) {
      _text(canvas, label, Offset(rect.left + padding, dy),
          const TextStyle(color: Color(0xFF7790A8), fontSize: 10.5));
      _text(canvas, value, Offset(rect.right - padding, dy),
          TextStyle(color: colour, fontSize: 10.5, fontWeight: FontWeight.w700),
          anchor: _Anchor.topRight);
      dy += lineHeight;
    }
  }

  // --- primitives ---------------------------------------------------------

  void _badge(Canvas canvas, Offset at, String label, Color background,
      Color foreground) {
    final painter = _painter(
      label,
      TextStyle(color: foreground, fontSize: 10.5, fontWeight: FontWeight.w800),
    );
    final rect = Rect.fromLTWH(
      at.dx, at.dy - painter.height / 2 - 2,
      painter.width + 10, painter.height + 4,
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(rect, const Radius.circular(4)),
      Paint()..color = background,
    );
    painter.paint(canvas, Offset(rect.left + 5, rect.top + 2));
  }

  TextPainter _painter(String value, TextStyle style, {TextAlign align = TextAlign.left}) {
    final painter = TextPainter(
      text: TextSpan(text: value, style: style),
      textDirection: TextDirection.ltr,
      textAlign: align,
    )..layout();
    return painter;
  }

  void _text(Canvas canvas, String value, Offset at, TextStyle style,
      {_Anchor anchor = _Anchor.topLeft, TextAlign align = TextAlign.left}) {
    final painter = _painter(value, style, align: align);
    final offset = switch (anchor) {
      _Anchor.topLeft => at,
      _Anchor.topRight => Offset(at.dx - painter.width, at.dy),
      _Anchor.topCenter => Offset(at.dx - painter.width / 2, at.dy),
      _Anchor.centerLeft => Offset(at.dx, at.dy - painter.height / 2),
      _Anchor.center =>
        Offset(at.dx - painter.width / 2, at.dy - painter.height / 2),
    };
    painter.paint(canvas, offset);
  }

  String _price(double value) {
    final abs = value.abs();
    final digits = abs >= 1000 ? 0 : (abs >= 1 ? 2 : 4);
    final text = value.toStringAsFixed(digits);
    if (digits > 0) return text.replaceAll('.', ',');
    // Espace fine insécable entre les milliers, comme partout dans l'app.
    return text.replaceAllMapped(
        RegExp(r'(\d)(?=(\d{3})+$)'), (m) => '${m[1]} ');
  }

  String _volumeLabel(double value) {
    if (value >= 1e9) return '${(value / 1e9).toStringAsFixed(1).replaceAll('.', ',')} Md';
    if (value >= 1e6) return '${(value / 1e6).toStringAsFixed(1).replaceAll('.', ',')} M';
    if (value >= 1e3) return '${(value / 1e3).toStringAsFixed(1).replaceAll('.', ',')} k';
    return value.toStringAsFixed(0);
  }

  static const _months = [
    'janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin',
    'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.',
  ];

  bool get _intraday => timeframe == '15m' || timeframe == '1h' || timeframe == '4h';

  String _date(DateTime value) => _intraday
      ? '${value.day} ${_months[value.month - 1]}\n'
          '${value.hour.toString().padLeft(2, '0')}:'
          '${value.minute.toString().padLeft(2, '0')}'
      : '${value.day} ${_months[value.month - 1]}\n${value.year}';

  String _dateTime(DateTime value) {
    final date = '${value.day} ${_months[value.month - 1]} ${value.year}';
    if (!_intraday) return date;
    return '$date · ${value.hour.toString().padLeft(2, '0')}:'
        '${value.minute.toString().padLeft(2, '0')}';
  }

  @override
  bool shouldRepaint(CandleChartPainter oldDelegate) =>
      oldDelegate.viewport != viewport ||
      oldDelegate.crosshair != crosshair ||
      oldDelegate.layers != layers ||
      oldDelegate.body != body ||
      oldDelegate.pair != pair ||
      oldDelegate.source != source ||
      oldDelegate.location != location ||
      !identical(oldDelegate.patterns, patterns);
}

enum _Anchor { topLeft, topRight, topCenter, centerLeft, center }
