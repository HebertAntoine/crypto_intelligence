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

  const CandleChart({
    super.key,
    required this.candles,
    required this.timeframe,
    required this.layers,
    this.pair,
    this.source,
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
            painter: _CandleChartPainter(
              viewport: viewport,
              layers: widget.layers,
              body: body,
              crosshair: _crosshair,
              timeframe: widget.timeframe,
              pair: widget.pair,
              source: widget.source,
            ),
          ),
        );
      },
    );
  }
}

class _CandleChartPainter extends CustomPainter {
  final ChartViewport viewport;
  final ChartLayerSet layers;
  final Rect body;
  final Offset? crosshair;
  final String timeframe;
  final String? pair;
  final String? source;

  _CandleChartPainter({
    required this.viewport,
    required this.layers,
    required this.body,
    required this.crosshair,
    required this.timeframe,
    this.pair,
    this.source,
  });

  Rect get _plot => viewport.plot;
  Rect get _volume => Rect.fromLTRB(body.left, _plot.bottom, body.right, body.bottom);

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Paint()..color = _background);
    if (viewport.isEmpty) {
      _paintEmpty(canvas, size);
      return;
    }
    // L'ordre est celui de `ChartLayer`: chaque élément a sa place et une
    // seule.
    if (layers.isVisible(ChartLayer.grid)) _paintGrid(canvas);
    if (layers.isVisible(ChartLayer.volume)) _paintVolume(canvas);
    if (layers.isVisible(ChartLayer.candles)) _paintCandles(canvas);
    if (layers.isVisible(ChartLayer.currentPrice)) _paintCurrentPrice(canvas);
    if (layers.isVisible(ChartLayer.labels)) {
      _paintPriceAxis(canvas, size);
      _paintTimeAxis(canvas, size);
      _paintHeader(canvas);
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

    final title = [pair, _timeframeLabel]
        .whereType<String>()
        .where((part) => part.isNotEmpty)
        .join(' · ');
    if (title.isNotEmpty) {
      _text(canvas, title, Offset(_plot.left + 6, dy),
          const TextStyle(
              color: _textPrimary, fontSize: 11.5, fontWeight: FontWeight.w800));
      dy += 14;
    }
    if (source != null && source!.isNotEmpty) {
      _text(canvas, source!, Offset(_plot.left + 6, dy),
          const TextStyle(color: Color(0xFF7790A8), fontSize: 10));
      dy += 13;
    }
    _text(
      canvas,
      '${_price(last.close)}  ${rising ? '+' : ''}'
      '${change.toStringAsFixed(2).replaceAll('.', ',')} %',
      Offset(_plot.left + 6, dy),
      TextStyle(color: colour, fontSize: 11.5, fontWeight: FontWeight.w700),
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
  bool shouldRepaint(_CandleChartPainter old) =>
      old.viewport != viewport ||
      old.crosshair != crosshair ||
      old.layers != layers ||
      old.body != body ||
      old.pair != pair ||
      old.source != source;
}

enum _Anchor { topLeft, topRight, topCenter, centerLeft, center }
