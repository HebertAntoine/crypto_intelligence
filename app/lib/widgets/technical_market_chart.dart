import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../api/models.dart';

/// Graphique technique natif base uniquement sur les donnees de [ChartRead].
///
/// Toutes les bougies recues sont dessinees. Quand la serie depasse la largeur
/// disponible, elle devient horizontalement defilable et s'ouvre sur les
/// dernieres bougies. Ce widget ne construit aucune figure chartiste : les
/// seules annotations structurelles sont les supports et resistances reels
/// exposes par `ChartRead.levels`.
class TechnicalMarketChart extends StatefulWidget {
  final ChartRead data;
  final String asset;
  final String timeframe;
  final bool showAverages;
  final bool showBollinger;
  final bool showLevels;
  final bool showVolume;
  final bool showMacd;
  final bool showRsi;

  const TechnicalMarketChart({
    super.key,
    required this.data,
    required this.asset,
    required this.timeframe,
    this.showAverages = true,
    this.showBollinger = true,
    this.showLevels = true,
    this.showVolume = true,
    this.showMacd = true,
    this.showRsi = true,
  });

  @override
  State<TechnicalMarketChart> createState() => _TechnicalMarketChartState();
}

class _TechnicalMarketChartState extends State<TechnicalMarketChart> {
  static const _axisWidth = 66.0;
  static const _priceHeight = 300.0;
  static const _volumeHeight = 76.0;
  static const _macdHeight = 112.0;
  static const _rsiHeight = 96.0;
  static const _timeAxisHeight = 34.0;
  static const _candleSlot = 7.5;
  static const _horizontalPadding = 14.0;

  final ScrollController _horizontalController = ScrollController();
  bool _positionOnLatest = true;
  bool _positionCallbackScheduled = false;

  @override
  void didUpdateWidget(covariant TechnicalMarketChart oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.asset != widget.asset ||
        oldWidget.timeframe != widget.timeframe ||
        oldWidget.data != widget.data) {
      _positionOnLatest = true;
    }
  }

  @override
  void dispose() {
    _horizontalController.dispose();
    super.dispose();
  }

  void _scheduleLatestPosition() {
    if (!_positionOnLatest || _positionCallbackScheduled) return;
    _positionCallbackScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _positionCallbackScheduled = false;
      if (!mounted || !_horizontalController.hasClients) return;
      _horizontalController.jumpTo(
        _horizontalController.position.maxScrollExtent,
      );
      _positionOnLatest = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final candles = widget.data.candles;
    final priceRange = _priceRange(
      widget.data,
      showAverages: widget.showAverages,
      showBollinger: widget.showBollinger,
      showLevels: widget.showLevels,
    );
    final maxVolume = _maxVolume(candles);
    final macdRange = _macdRange(widget.data);

    return Semantics(
      label: 'Graphique technique ${widget.asset}, '
          '${_timeframeLabel(widget.timeframe)}, ${candles.length} bougies',
      child: Container(
        key: const Key('technical-market-chart'),
        clipBehavior: Clip.hardEdge,
        decoration: BoxDecoration(
          color: const Color(0xFF061426),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: const Color(0xFF147ED0), width: 1.4),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF058CFF).withValues(alpha: 0.12),
              blurRadius: 24,
              spreadRadius: -8,
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _MarketHeader(
              data: widget.data,
              asset: widget.asset,
              timeframe: widget.timeframe,
              showAverages: widget.showAverages,
              showBollinger: widget.showBollinger,
            ),
            const Divider(height: 1, color: Color(0xFF173B5C)),
            if (!widget.data.available || candles.isEmpty)
              SizedBox(
                key: const Key('technical-market-chart-unavailable'),
                height: _priceHeight,
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text(
                      widget.data.reason.isEmpty
                          ? 'Bougies OHLCV indisponibles.'
                          : widget.data.reason,
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        color: Color(0xFFABC0DE),
                        fontSize: 15,
                        height: 1.35,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ),
              )
            else
              LayoutBuilder(
                builder: (context, constraints) {
                  final viewportWidth = math.max(
                    1.0,
                    constraints.maxWidth - _axisWidth,
                  );
                  final seriesWidth = math.max(
                    viewportWidth,
                    candles.length * _candleSlot + _horizontalPadding * 2,
                  );
                  _scheduleLatestPosition();

                  return SizedBox(
                    height: _bodyHeight,
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Expanded(
                          child: Scrollbar(
                            key: const Key('technical-market-chart-scrollbar'),
                            controller: _horizontalController,
                            thumbVisibility: true,
                            interactive: true,
                            scrollbarOrientation: ScrollbarOrientation.bottom,
                            child: SingleChildScrollView(
                              key: const Key('technical-market-chart-scroll'),
                              controller: _horizontalController,
                              scrollDirection: Axis.horizontal,
                              physics: const ClampingScrollPhysics(),
                              child: SizedBox(
                                width: seriesWidth,
                                child: Column(
                                  crossAxisAlignment:
                                      CrossAxisAlignment.stretch,
                                  children: [
                                    SizedBox(
                                      key: const Key(
                                          'technical-market-chart-price-panel'),
                                      height: _priceHeight,
                                      child: CustomPaint(
                                        painter: _PricePanelPainter(
                                          data: widget.data,
                                          range: priceRange,
                                          showAverages: widget.showAverages,
                                          showBollinger: widget.showBollinger,
                                          showLevels: widget.showLevels,
                                        ),
                                      ),
                                    ),
                                    if (widget.showVolume)
                                      SizedBox(
                                        key: const Key(
                                            'technical-market-chart-volume-panel'),
                                        height: _volumeHeight,
                                        child: CustomPaint(
                                          painter: _VolumePanelPainter(
                                            candles: candles,
                                            maximum: maxVolume,
                                          ),
                                        ),
                                      ),
                                    if (widget.showMacd)
                                      SizedBox(
                                        key: const Key(
                                            'technical-market-chart-macd-panel'),
                                        height: _macdHeight,
                                        child: CustomPaint(
                                          painter: _MacdPanelPainter(
                                            candles: candles,
                                            macd: widget.data.panels['macd'],
                                            signal: widget
                                                .data.panels['macd_signal'],
                                            histogram:
                                                widget.data.panels['macd_hist'],
                                            range: macdRange,
                                          ),
                                        ),
                                      ),
                                    if (widget.showRsi)
                                      SizedBox(
                                        key: const Key(
                                            'technical-market-chart-rsi-panel'),
                                        height: _rsiHeight,
                                        child: CustomPaint(
                                          painter: _RsiPanelPainter(
                                            candles: candles,
                                            rsi: widget.data.panels['rsi'],
                                          ),
                                        ),
                                      ),
                                    SizedBox(
                                      key: const Key(
                                          'technical-market-chart-time-axis'),
                                      height: _timeAxisHeight,
                                      child: CustomPaint(
                                        painter: _TimeAxisPainter(
                                          candles: candles,
                                          timeframe: widget.timeframe,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ),
                        SizedBox(
                          key: const Key('technical-market-chart-value-axis'),
                          width: _axisWidth,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              SizedBox(
                                height: _priceHeight,
                                child: CustomPaint(
                                  painter: _PriceAxisPainter(
                                    range: priceRange,
                                    current: candles.last.close,
                                    positive: widget.data.changePct == null ||
                                        widget.data.changePct! >= 0,
                                  ),
                                ),
                              ),
                              if (widget.showVolume)
                                SizedBox(
                                  height: _volumeHeight,
                                  child: CustomPaint(
                                    painter: _SimpleAxisPainter(
                                      minimum: 0,
                                      maximum: maxVolume,
                                      labels: const [1, 0],
                                      compact: true,
                                    ),
                                  ),
                                ),
                              if (widget.showMacd)
                                SizedBox(
                                  height: _macdHeight,
                                  child: CustomPaint(
                                    painter: _SimpleAxisPainter(
                                      minimum: macdRange.min,
                                      maximum: macdRange.max,
                                      labels: const [1, .5, 0],
                                      compact: true,
                                    ),
                                  ),
                                ),
                              if (widget.showRsi)
                                const SizedBox(
                                  height: _rsiHeight,
                                  child: CustomPaint(
                                    painter: _SimpleAxisPainter(
                                      minimum: 0,
                                      maximum: 100,
                                      labels: [.7, .5, .3],
                                    ),
                                  ),
                                ),
                              const SizedBox(height: _timeAxisHeight),
                            ],
                          ),
                        ),
                      ],
                    ),
                  );
                },
              ),
          ],
        ),
      ),
    );
  }

  double get _bodyHeight =>
      _priceHeight +
      (widget.showVolume ? _volumeHeight : 0) +
      (widget.showMacd ? _macdHeight : 0) +
      (widget.showRsi ? _rsiHeight : 0) +
      _timeAxisHeight;
}

class _MarketHeader extends StatelessWidget {
  final ChartRead data;
  final String asset;
  final String timeframe;
  final bool showAverages;
  final bool showBollinger;

  const _MarketHeader({
    required this.data,
    required this.asset,
    required this.timeframe,
    required this.showAverages,
    required this.showBollinger,
  });

  @override
  Widget build(BuildContext context) {
    final latest = data.candles.isEmpty ? null : data.candles.last;
    final change = data.changePct;
    final changeColor = change == null
        ? const Color(0xFFAFC2DD)
        : change >= 0
            ? const Color(0xFF35E6A1)
            : const Color(0xFFFF6171);
    final ema50 = _lastNumeric(data.overlays['ema50']);
    final ema200 = _lastNumeric(data.overlays['ema200']);
    final bbMiddle = _lastNumeric(data.overlays['bb_middle']);

    return Padding(
      key: const Key('technical-market-chart-header'),
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 11),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.candlestick_chart_rounded,
                color: Color(0xFF37D9A0),
                size: 23,
              ),
              const SizedBox(width: 7),
              Expanded(
                child: Text(
                  '${asset.toUpperCase()} / USDT',
                  key: const Key('technical-market-chart-symbol'),
                  style: const TextStyle(
                    color: Color(0xFFF2F6FF),
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
              Text(
                _timeframeLabel(timeframe),
                key: const Key('technical-market-chart-timeframe-label'),
                style: const TextStyle(
                  color: Color(0xFFAFC2DD),
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 7),
          Wrap(
            spacing: 12,
            runSpacing: 5,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(
                latest == null ? '—' : _formatPrice(latest.close),
                key: const Key('technical-market-chart-last-price'),
                style: TextStyle(
                  color: changeColor,
                  fontSize: 17,
                  fontWeight: FontWeight.w800,
                ),
              ),
              Text(
                change == null
                    ? 'variation indisponible'
                    : '${_signed(change, digits: 2)} %',
                key: const Key('technical-market-chart-change'),
                style: TextStyle(
                  color: changeColor,
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                ),
              ),
              if (showAverages && ema50 != null)
                _HeaderMetric(
                  label: 'EMA 50',
                  value: _formatPrice(ema50),
                  color: const Color(0xFF3090FF),
                ),
              if (showAverages && ema200 != null)
                _HeaderMetric(
                  label: 'EMA 200',
                  value: _formatPrice(ema200),
                  color: const Color(0xFFFFA12B),
                ),
              if (showBollinger && bbMiddle != null)
                _HeaderMetric(
                  label: 'BB 20',
                  value: _formatPrice(bbMiddle),
                  color: const Color(0xFF91A7C9),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _HeaderMetric extends StatelessWidget {
  final String label;
  final String value;
  final Color color;

  const _HeaderMetric({
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Text.rich(
      TextSpan(
        children: [
          TextSpan(
            text: '$label  ',
            style: const TextStyle(color: Color(0xFFAFC2DD)),
          ),
          TextSpan(
            text: value,
            style: TextStyle(color: color, fontWeight: FontWeight.w800),
          ),
        ],
      ),
      style: const TextStyle(fontSize: 12.5),
    );
  }
}

class _PricePanelPainter extends CustomPainter {
  final ChartRead data;
  final _ValueRange range;
  final bool showAverages;
  final bool showBollinger;
  final bool showLevels;

  const _PricePanelPainter({
    required this.data,
    required this.range,
    required this.showAverages,
    required this.showBollinger,
    required this.showLevels,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final candles = data.candles;
    _paintPanelBackground(canvas, size);
    _drawHorizontalGrid(canvas, size, 5);
    _drawVerticalGrid(canvas, size, candles);
    if (candles.isEmpty) return;

    double yFor(double value) => range.y(value, size.height, padding: 12);

    if (showBollinger) {
      final upper = data.overlays['bb_upper'];
      final middle = data.overlays['bb_middle'];
      final lower = data.overlays['bb_lower'];
      if (upper != null && lower != null) {
        _drawBand(
          canvas,
          size,
          candles.length,
          upper,
          lower,
          yFor,
          const Color(0xFF2468DD).withValues(alpha: 0.13),
        );
        _drawSeries(
          canvas,
          size,
          candles.length,
          upper,
          yFor,
          Paint()
            ..color = const Color(0xFF397AE8).withValues(alpha: 0.75)
            ..strokeWidth = 1.15
            ..style = PaintingStyle.stroke,
        );
        _drawSeries(
          canvas,
          size,
          candles.length,
          lower,
          yFor,
          Paint()
            ..color = const Color(0xFF397AE8).withValues(alpha: 0.75)
            ..strokeWidth = 1.15
            ..style = PaintingStyle.stroke,
        );
      }
      if (middle != null) {
        _drawSeries(
          canvas,
          size,
          candles.length,
          middle,
          yFor,
          Paint()
            ..color = const Color(0xFF6C8CCA).withValues(alpha: 0.72)
            ..strokeWidth = 1
            ..style = PaintingStyle.stroke,
        );
      }
    }

    if (showLevels) {
      _drawLevels(canvas, size, range, data.levels);
    }

    final stride = _stride(size.width, candles.length);
    final bodyWidth = math.min(7.0, math.max(2.2, stride * .62));
    for (var index = 0; index < candles.length; index += 1) {
      final candle = candles[index];
      final x = _xFor(index, size.width, candles.length);
      final bullish = candle.close >= candle.open;
      final color = bullish ? const Color(0xFF28D99A) : const Color(0xFFFF5368);
      final paint = Paint()
        ..color = color
        ..strokeWidth = 1.05;
      canvas.drawLine(
        Offset(x, yFor(candle.high)),
        Offset(x, yFor(candle.low)),
        paint,
      );
      final openY = yFor(candle.open);
      final closeY = yFor(candle.close);
      final top = math.min(openY, closeY);
      final bottom = math.max(openY, closeY);
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromCenter(
            center: Offset(x, (top + bottom) / 2),
            width: bodyWidth,
            height: math.max(1.8, bottom - top),
          ),
          const Radius.circular(.8),
        ),
        paint,
      );
    }

    if (showAverages) {
      _drawSeries(
        canvas,
        size,
        candles.length,
        data.overlays['ema50'] ?? const [],
        yFor,
        Paint()
          ..color = const Color(0xFF2D8EFF)
          ..strokeWidth = 1.7
          ..style = PaintingStyle.stroke,
      );
      _drawSeries(
        canvas,
        size,
        candles.length,
        data.overlays['ema200'] ?? const [],
        yFor,
        Paint()
          ..color = const Color(0xFFFF9D24)
          ..strokeWidth = 1.7
          ..style = PaintingStyle.stroke,
      );
    }

    final last = candles.last;
    final currentY = yFor(last.close);
    _drawDashedLine(
      canvas,
      Offset(0, currentY),
      Offset(size.width, currentY),
      Paint()
        ..color = (last.close >= last.open
                ? const Color(0xFF39DFA1)
                : const Color(0xFFFF5C70))
            .withValues(alpha: .72)
        ..strokeWidth = 1,
    );
  }

  void _drawLevels(
    Canvas canvas,
    Size size,
    _ValueRange priceRange,
    Map<String, dynamic> levels,
  ) {
    for (final entry in <(String, Color)>[
      ('support', const Color(0xFF34D58A)),
      ('resistance', const Color(0xFFFF5265)),
    ]) {
      final values = _realLevels(levels, entry.$1);
      for (final level in values) {
        if (level.price < priceRange.min || level.price > priceRange.max) {
          continue;
        }
        final y = priceRange.y(level.price, size.height, padding: 12);
        final opacity = (.42 + level.strength.clamp(0, 1) * .42).toDouble();
        final paint = Paint()
          ..color = entry.$2.withValues(alpha: opacity)
          ..strokeWidth = 1.15;
        canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
        final touches = level.touches > 0 ? ' · ${level.touches}x' : '';
        _paintText(
          canvas,
          '${entry.$1 == 'support' ? 'Support' : 'Résistance'}$touches',
          Offset(size.width - 118, math.max(2, y - 17)),
          TextStyle(
            color: entry.$2,
            fontSize: 11.5,
            fontWeight: FontWeight.w800,
          ),
          maxWidth: 112,
          align: TextAlign.right,
        );
      }
    }
  }

  @override
  bool shouldRepaint(covariant _PricePanelPainter oldDelegate) =>
      oldDelegate.data != data ||
      oldDelegate.range != range ||
      oldDelegate.showAverages != showAverages ||
      oldDelegate.showBollinger != showBollinger ||
      oldDelegate.showLevels != showLevels;
}

class _VolumePanelPainter extends CustomPainter {
  final List<CandlePoint> candles;
  final double maximum;

  const _VolumePanelPainter({required this.candles, required this.maximum});

  @override
  void paint(Canvas canvas, Size size) {
    _paintPanelBackground(canvas, size);
    _drawVerticalGrid(canvas, size, candles);
    final latest = candles.isEmpty ? null : candles.last.volume;
    _paintPanelTitle(
      canvas,
      'Vol.${latest == null ? '' : '  ${_formatCompact(latest)}'}',
    );
    if (candles.isEmpty || maximum <= 0) return;
    final stride = _stride(size.width, candles.length);
    final barWidth = math.min(6.5, math.max(2.0, stride * .65));
    for (var index = 0; index < candles.length; index += 1) {
      final candle = candles[index];
      final ratio = (candle.volume / maximum).clamp(0.0, 1.0);
      final x = _xFor(index, size.width, candles.length);
      final height = math.max(1.0, (size.height - 20) * ratio);
      canvas.drawRect(
        Rect.fromLTWH(
          x - barWidth / 2,
          size.height - height,
          barWidth,
          height,
        ),
        Paint()
          ..color = (candle.close >= candle.open
                  ? const Color(0xFF27C992)
                  : const Color(0xFFFF5368))
              .withValues(alpha: .68),
      );
    }
  }

  @override
  bool shouldRepaint(covariant _VolumePanelPainter oldDelegate) =>
      oldDelegate.candles != candles || oldDelegate.maximum != maximum;
}

class _MacdPanelPainter extends CustomPainter {
  final List<CandlePoint> candles;
  final List<double?>? macd;
  final List<double?>? signal;
  final List<double?>? histogram;
  final _ValueRange range;

  const _MacdPanelPainter({
    required this.candles,
    required this.macd,
    required this.signal,
    required this.histogram,
    required this.range,
  });

  @override
  void paint(Canvas canvas, Size size) {
    _paintPanelBackground(canvas, size);
    _drawVerticalGrid(canvas, size, candles);
    _drawHorizontalGrid(canvas, size, 2);
    final currentMacd = _lastNumeric(macd);
    final currentSignal = _lastNumeric(signal);
    _paintPanelTitle(
      canvas,
      'MACD 12 26 9'
      '${currentMacd == null ? '' : '  ${_formatCompact(currentMacd)}'}'
      '${currentSignal == null ? '' : '  ${_formatCompact(currentSignal)}'}',
    );
    if (candles.isEmpty ||
        (macd == null && signal == null && histogram == null)) {
      _paintUnavailable(canvas, size, 'MACD indisponible');
      return;
    }

    double yFor(double value) => range.y(value, size.height, padding: 11);
    final zeroY = yFor(0);
    canvas.drawLine(
      Offset(0, zeroY),
      Offset(size.width, zeroY),
      Paint()
        ..color = const Color(0xFF6282A7).withValues(alpha: .55)
        ..strokeWidth = 1,
    );

    final values = histogram ?? const <double?>[];
    final stride = _stride(size.width, candles.length);
    final barWidth = math.min(6.5, math.max(2.0, stride * .67));
    for (var index = 0;
        index < candles.length && index < values.length;
        index += 1) {
      final value = values[index];
      if (!_valid(value)) continue;
      final x = _xFor(index, size.width, candles.length);
      final y = yFor(value!);
      canvas.drawRect(
        Rect.fromLTRB(
          x - barWidth / 2,
          math.min(y, zeroY),
          x + barWidth / 2,
          math.max(y, zeroY),
        ),
        Paint()
          ..color =
              value >= 0 ? const Color(0xFF38D8AE) : const Color(0xFFFF536D),
      );
    }

    _drawSeries(
      canvas,
      size,
      candles.length,
      macd ?? const [],
      yFor,
      Paint()
        ..color = const Color(0xFF2C8EFF)
        ..strokeWidth = 1.65
        ..style = PaintingStyle.stroke,
    );
    _drawSeries(
      canvas,
      size,
      candles.length,
      signal ?? const [],
      yFor,
      Paint()
        ..color = const Color(0xFFFF9F24)
        ..strokeWidth = 1.55
        ..style = PaintingStyle.stroke,
    );
  }

  @override
  bool shouldRepaint(covariant _MacdPanelPainter oldDelegate) =>
      oldDelegate.candles != candles ||
      oldDelegate.macd != macd ||
      oldDelegate.signal != signal ||
      oldDelegate.histogram != histogram ||
      oldDelegate.range != range;
}

class _RsiPanelPainter extends CustomPainter {
  final List<CandlePoint> candles;
  final List<double?>? rsi;

  const _RsiPanelPainter({required this.candles, required this.rsi});

  @override
  void paint(Canvas canvas, Size size) {
    _paintPanelBackground(canvas, size);
    _drawVerticalGrid(canvas, size, candles);
    final current = _lastNumeric(rsi);
    _paintPanelTitle(
      canvas,
      'RSI 14${current == null ? '' : '  ${current.toStringAsFixed(1)}'}',
    );

    double yFor(double value) =>
        size.height - 8 - (size.height - 16) * (value.clamp(0, 100) / 100);
    for (final level in [70.0, 50.0, 30.0]) {
      _drawDashedLine(
        canvas,
        Offset(0, yFor(level)),
        Offset(size.width, yFor(level)),
        Paint()
          ..color =
              const Color(0xFF8293C0).withValues(alpha: level == 50 ? .34 : .60)
          ..strokeWidth = 1,
        dash: 4,
        gap: 4,
      );
    }
    if (candles.isEmpty || rsi == null) {
      _paintUnavailable(canvas, size, 'RSI indisponible');
      return;
    }
    _drawSeries(
      canvas,
      size,
      candles.length,
      rsi!,
      yFor,
      Paint()
        ..color = const Color(0xFF9A6DFF)
        ..strokeWidth = 1.55
        ..style = PaintingStyle.stroke,
    );
  }

  @override
  bool shouldRepaint(covariant _RsiPanelPainter oldDelegate) =>
      oldDelegate.candles != candles || oldDelegate.rsi != rsi;
}

class _TimeAxisPainter extends CustomPainter {
  final List<CandlePoint> candles;
  final String timeframe;

  const _TimeAxisPainter({required this.candles, required this.timeframe});

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(
        Offset.zero & size, Paint()..color = const Color(0xFF07182B));
    canvas.drawLine(
      Offset.zero,
      Offset(size.width, 0),
      Paint()
        ..color = const Color(0xFF1A3B5B)
        ..strokeWidth = 1,
    );
    if (candles.isEmpty) return;
    for (final index in _timeLabelIndexes(size.width, candles.length)) {
      final time = candles[index].time;
      if (time == null) continue;
      final x = _xFor(index, size.width, candles.length);
      _paintText(
        canvas,
        _formatTime(time.toLocal(), timeframe),
        Offset(x - 34, 9),
        const TextStyle(color: Color(0xFFA8BBD5), fontSize: 10.5),
        maxWidth: 68,
        align: TextAlign.center,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _TimeAxisPainter oldDelegate) =>
      oldDelegate.candles != candles || oldDelegate.timeframe != timeframe;
}

class _PriceAxisPainter extends CustomPainter {
  final _ValueRange range;
  final double current;
  final bool positive;

  const _PriceAxisPainter({
    required this.range,
    required this.current,
    required this.positive,
  });

  @override
  void paint(Canvas canvas, Size size) {
    _paintAxisBackground(canvas, size);
    for (var index = 0; index < 5; index += 1) {
      final ratio = index / 4;
      final value = range.max - range.span * ratio;
      final y = 12 + (size.height - 24) * ratio;
      _paintText(
        canvas,
        _formatPrice(value),
        Offset(5, y - 7),
        const TextStyle(color: Color(0xFFB5C7E1), fontSize: 10.5),
        maxWidth: size.width - 8,
      );
    }

    final y = range.y(current, size.height, padding: 12);
    final color = positive ? const Color(0xFF39DFA1) : const Color(0xFFFF5C70);
    final pill = RRect.fromRectAndRadius(
      Rect.fromLTWH(2, (y - 11).clamp(1, size.height - 23), size.width - 4, 22),
      const Radius.circular(4),
    );
    canvas.drawRRect(pill, Paint()..color = color);
    _paintText(
      canvas,
      _formatPrice(current),
      Offset(5, (y - 7).clamp(5, size.height - 17)),
      const TextStyle(
        color: Color(0xFF031B16),
        fontSize: 10.5,
        fontWeight: FontWeight.w900,
      ),
      maxWidth: size.width - 10,
    );
  }

  @override
  bool shouldRepaint(covariant _PriceAxisPainter oldDelegate) =>
      oldDelegate.range != range ||
      oldDelegate.current != current ||
      oldDelegate.positive != positive;
}

class _SimpleAxisPainter extends CustomPainter {
  final double minimum;
  final double maximum;
  final List<double> labels;
  final bool compact;

  const _SimpleAxisPainter({
    required this.minimum,
    required this.maximum,
    required this.labels,
    this.compact = false,
  });

  @override
  void paint(Canvas canvas, Size size) {
    _paintAxisBackground(canvas, size);
    final span = maximum - minimum;
    for (final fraction in labels) {
      final value = minimum + span * fraction;
      final y = size.height - 8 - (size.height - 16) * fraction;
      _paintText(
        canvas,
        compact ? _formatCompact(value) : value.toStringAsFixed(0),
        Offset(5, y - 7),
        const TextStyle(color: Color(0xFFB5C7E1), fontSize: 10.5),
        maxWidth: size.width - 8,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _SimpleAxisPainter oldDelegate) =>
      oldDelegate.minimum != minimum ||
      oldDelegate.maximum != maximum ||
      oldDelegate.labels != labels ||
      oldDelegate.compact != compact;
}

@immutable
class _ValueRange {
  final double min;
  final double max;

  const _ValueRange(this.min, this.max);

  double get span => max - min;

  double y(double value, double height, {double padding = 0}) {
    final drawable = math.max(1.0, height - padding * 2);
    final ratio = ((value - min) / span).clamp(0.0, 1.0);
    return height - padding - drawable * ratio;
  }

  @override
  bool operator ==(Object other) =>
      other is _ValueRange && other.min == min && other.max == max;

  @override
  int get hashCode => Object.hash(min, max);
}

class _RealLevel {
  final double price;
  final int touches;
  final double strength;

  const _RealLevel({
    required this.price,
    required this.touches,
    required this.strength,
  });
}

_ValueRange _priceRange(
  ChartRead data, {
  required bool showAverages,
  required bool showBollinger,
  required bool showLevels,
}) {
  final values = <double>[];
  for (final candle in data.candles) {
    if (candle.low.isFinite && candle.low > 0) values.add(candle.low);
    if (candle.high.isFinite && candle.high > 0) values.add(candle.high);
  }
  if (showAverages) {
    _addValid(values, data.overlays['ema50']);
    _addValid(values, data.overlays['ema200']);
  }
  if (showBollinger) {
    _addValid(values, data.overlays['bb_upper']);
    _addValid(values, data.overlays['bb_middle']);
    _addValid(values, data.overlays['bb_lower']);
  }
  if (showLevels) {
    values
        .addAll(_realLevels(data.levels, 'support').map((item) => item.price));
    values.addAll(
        _realLevels(data.levels, 'resistance').map((item) => item.price));
  }
  if (values.isEmpty) return const _ValueRange(0, 1);
  final rawMin = values.reduce(math.min);
  final rawMax = values.reduce(math.max);
  final rawSpan = rawMax - rawMin;
  final padding = rawSpan > 0
      ? rawSpan * .055
      : math.max(rawMax.abs() * .01, .01).toDouble();
  return _ValueRange(rawMin - padding, rawMax + padding);
}

_ValueRange _macdRange(ChartRead data) {
  final values = <double>[0];
  _addValid(values, data.panels['macd']);
  _addValid(values, data.panels['macd_signal']);
  _addValid(values, data.panels['macd_hist']);
  final rawMin = values.reduce(math.min);
  final rawMax = values.reduce(math.max);
  final rawSpan = rawMax - rawMin;
  final padding = rawSpan > 0 ? rawSpan * .1 : 1.0;
  return _ValueRange(rawMin - padding, rawMax + padding);
}

double _maxVolume(List<CandlePoint> candles) {
  var maximum = 0.0;
  for (final candle in candles) {
    if (candle.volume.isFinite && candle.volume > maximum) {
      maximum = candle.volume;
    }
  }
  return maximum;
}

void _addValid(List<double> destination, List<double?>? source) {
  if (source == null) return;
  for (final value in source) {
    if (_valid(value)) destination.add(value!);
  }
}

List<_RealLevel> _realLevels(Map<String, dynamic> levels, String key) {
  final raw = levels[key];
  if (raw is! List) return const [];
  final result = <_RealLevel>[];
  for (final item in raw) {
    if (item is! Map) continue;
    final price = item['price'];
    if (price is! num || !price.toDouble().isFinite || price <= 0) continue;
    final touches = item['touches'];
    final strength = item['strength'];
    result.add(_RealLevel(
      price: price.toDouble(),
      touches: touches is num ? touches.toInt() : 0,
      strength: strength is num ? strength.toDouble() : 0,
    ));
  }
  return result;
}

double _stride(double width, int count) {
  if (count <= 0) return width;
  return (width - _TechnicalMarketChartState._horizontalPadding * 2) / count;
}

double _xFor(int index, double width, int count) =>
    _TechnicalMarketChartState._horizontalPadding +
    _stride(width, count) * (index + .5);

void _paintPanelBackground(Canvas canvas, Size size) {
  canvas.drawRect(Offset.zero & size, Paint()..color = const Color(0xFF07182B));
  canvas.drawLine(
    Offset(0, size.height - .5),
    Offset(size.width, size.height - .5),
    Paint()
      ..color = const Color(0xFF1A3B5B)
      ..strokeWidth = 1,
  );
}

void _paintAxisBackground(Canvas canvas, Size size) {
  canvas.drawRect(Offset.zero & size, Paint()..color = const Color(0xFF081526));
  canvas.drawLine(
    Offset(.5, 0),
    Offset(.5, size.height),
    Paint()
      ..color = const Color(0xFF315776)
      ..strokeWidth = 1,
  );
  canvas.drawLine(
    Offset(0, size.height - .5),
    Offset(size.width, size.height - .5),
    Paint()
      ..color = const Color(0xFF1A3B5B)
      ..strokeWidth = 1,
  );
}

void _drawHorizontalGrid(Canvas canvas, Size size, int divisions) {
  final paint = Paint()
    ..color = const Color(0xFF1D3853).withValues(alpha: .72)
    ..strokeWidth = .8;
  for (var index = 0; index <= divisions; index += 1) {
    final y = size.height * index / divisions;
    canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
  }
}

void _drawVerticalGrid(
  Canvas canvas,
  Size size,
  List<CandlePoint> candles,
) {
  if (candles.isEmpty) return;
  final paint = Paint()
    ..color = const Color(0xFF1D3853).withValues(alpha: .58)
    ..strokeWidth = .8;
  for (final index in _timeLabelIndexes(size.width, candles.length)) {
    final x = _xFor(index, size.width, candles.length);
    canvas.drawLine(Offset(x, 0), Offset(x, size.height), paint);
  }
}

List<int> _timeLabelIndexes(double width, int count) {
  if (count <= 0) return const [];
  final stride = _stride(width, count);
  final every = math.max(1, (78 / stride).ceil());
  final result = <int>[];
  for (var index = 0; index < count; index += every) {
    result.add(index);
  }
  if (result.isEmpty || result.last != count - 1) result.add(count - 1);
  return result;
}

void _drawSeries(
  Canvas canvas,
  Size size,
  int candleCount,
  List<double?> values,
  double Function(double) yFor,
  Paint paint,
) {
  if (candleCount <= 0 || values.isEmpty) return;
  var path = Path();
  var started = false;
  final length = math.min(candleCount, values.length);
  for (var index = 0; index < length; index += 1) {
    final value = values[index];
    if (!_valid(value)) {
      if (started) canvas.drawPath(path, paint);
      path = Path();
      started = false;
      continue;
    }
    final point = Offset(
      _xFor(index, size.width, candleCount),
      yFor(value!),
    );
    if (!started) {
      path.moveTo(point.dx, point.dy);
      started = true;
    } else {
      path.lineTo(point.dx, point.dy);
    }
  }
  if (started) canvas.drawPath(path, paint);
}

void _drawBand(
  Canvas canvas,
  Size size,
  int candleCount,
  List<double?> upper,
  List<double?> lower,
  double Function(double) yFor,
  Color color,
) {
  final length = math.min(candleCount, math.min(upper.length, lower.length));
  var index = 0;
  while (index < length) {
    while (index < length && !(_valid(upper[index]) && _valid(lower[index]))) {
      index += 1;
    }
    final start = index;
    while (index < length && _valid(upper[index]) && _valid(lower[index])) {
      index += 1;
    }
    final end = index - 1;
    if (end <= start) continue;
    final path = Path();
    for (var point = start; point <= end; point += 1) {
      final x = _xFor(point, size.width, candleCount);
      final y = yFor(upper[point]!);
      if (point == start) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }
    for (var point = end; point >= start; point -= 1) {
      path.lineTo(
        _xFor(point, size.width, candleCount),
        yFor(lower[point]!),
      );
    }
    path.close();
    canvas.drawPath(path, Paint()..color = color);
  }
}

void _drawDashedLine(
  Canvas canvas,
  Offset start,
  Offset end,
  Paint paint, {
  double dash = 5,
  double gap = 4,
}) {
  final vector = end - start;
  final distance = vector.distance;
  if (distance <= 0) return;
  final direction = vector / distance;
  var travelled = 0.0;
  while (travelled < distance) {
    final from = start + direction * travelled;
    final to = start + direction * math.min(distance, travelled + dash);
    canvas.drawLine(from, to, paint);
    travelled += dash + gap;
  }
}

void _paintPanelTitle(Canvas canvas, String text) {
  _paintText(
    canvas,
    text,
    const Offset(9, 7),
    const TextStyle(
      color: Color(0xFFDCE7F8),
      fontSize: 11.5,
      fontWeight: FontWeight.w700,
    ),
    maxWidth: 280,
  );
}

void _paintUnavailable(Canvas canvas, Size size, String text) {
  _paintText(
    canvas,
    text,
    Offset(9, size.height / 2 - 7),
    const TextStyle(color: Color(0xFF8296B2), fontSize: 11.5),
    maxWidth: math.min(220, size.width - 18),
  );
}

void _paintText(
  Canvas canvas,
  String text,
  Offset offset,
  TextStyle style, {
  double? maxWidth,
  TextAlign align = TextAlign.left,
}) {
  final painter = TextPainter(
    text: TextSpan(text: text, style: style),
    textDirection: TextDirection.ltr,
    textAlign: align,
    maxLines: 1,
    ellipsis: '…',
  )..layout(maxWidth: maxWidth ?? double.infinity);
  painter.paint(canvas, offset);
}

bool _valid(double? value) => value != null && value.isFinite && !value.isNaN;

double? _lastNumeric(List<double?>? values) {
  if (values == null) return null;
  for (var index = values.length - 1; index >= 0; index -= 1) {
    if (_valid(values[index])) return values[index];
  }
  return null;
}

String _timeframeLabel(String value) => switch (value) {
      '15m' => '15 min',
      '1h' => '1 h',
      '4h' => '4 h',
      '1d' => '1 j',
      '1w' => '1 sem.',
      _ => value,
    };

String _formatTime(DateTime time, String timeframe) {
  if (timeframe == '15m' || timeframe == '1h' || timeframe == '4h') {
    return '${_twoDigits(time.day)}/${_twoDigits(time.month)} '
        '${_twoDigits(time.hour)}:${_twoDigits(time.minute)}';
  }
  if (timeframe == '1d') {
    return '${_twoDigits(time.day)}/${_twoDigits(time.month)}';
  }
  return '${_twoDigits(time.month)}/${time.year}';
}

String _twoDigits(int value) => value.toString().padLeft(2, '0');

String _formatPrice(num value) {
  final digits = value.abs() >= 1000 ? 0 : 2;
  final fixed = value.toStringAsFixed(digits);
  final parts = fixed.split('.');
  final negative = parts.first.startsWith('-');
  final rawWhole = negative ? parts.first.substring(1) : parts.first;
  final buffer = StringBuffer(negative ? '-' : '');
  for (var index = 0; index < rawWhole.length; index += 1) {
    final remaining = rawWhole.length - index;
    buffer.write(rawWhole[index]);
    if (remaining > 1 && remaining % 3 == 1) buffer.write(' ');
  }
  if (digits == 0) return buffer.toString();
  return '${buffer.toString()},${parts.last}';
}

String _formatCompact(num value) {
  final absolute = value.abs();
  if (absolute >= 1000000000) {
    return '${(value / 1000000000).toStringAsFixed(1)} Md';
  }
  if (absolute >= 1000000) {
    return '${(value / 1000000).toStringAsFixed(1)} M';
  }
  if (absolute >= 1000) return '${(value / 1000).toStringAsFixed(1)} K';
  if (absolute >= 10) return value.toStringAsFixed(0);
  return value.toStringAsFixed(2);
}

String _signed(num value, {int digits = 2}) {
  final prefix = value > 0 ? '+' : '';
  return '$prefix${value.toStringAsFixed(digits).replaceAll('.', ',')}';
}
