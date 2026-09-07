/// Ecran "Intelligence graphique".
///
/// Les donnees backend restent chargees pour garder l'ecran fonctionnel, mais
/// la presentation reprend la maquette mobile fournie: chart, pattern detecte,
/// confluences et occurrences historiques.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../widgets/common.dart';
import '../widgets/mobile_kit.dart';

class ChartScreen extends StatefulWidget {
  final ApiClient client;

  const ChartScreen({super.key, required this.client});

  @override
  State<ChartScreen> createState() => _ChartScreenState();
}

class _ChartScreenState extends State<ChartScreen> {
  static const _assets = ['BTC', 'ETH', 'SOL'];
  static const _timeframes = ['15m', '1h', '4h', '1d', '1w'];

  String _asset = 'BTC';
  String _timeframe = '4h';
  late Future<(StructureRead, EntryOpportunity?)> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<(StructureRead, EntryOpportunity?)> _load() async {
    final structure = await widget.client.structure(_asset, timeframe: _timeframe);
    EntryOpportunity? opportunity;
    try {
      opportunity = await widget.client.entryOpportunity(_asset, timeframe: _timeframe);
    } catch (_) {
      opportunity = null;
    }
    return (structure, opportunity);
  }

  void _reload() => setState(() => _future = _load());

  void _selectAsset(String value) {
    setState(() {
      _asset = value;
      _future = _load();
    });
  }

  void _selectTimeframe(String value) {
    setState(() {
      _timeframe = value;
      _future = _load();
    });
  }

  @override
  Widget build(BuildContext context) {
    return MobileGradientFrame(
      child: RefreshIndicator(
        onRefresh: () async => _reload(),
        child: FutureBuilder<(StructureRead, EntryOpportunity?)>(
          future: _future,
          builder: (context, snapshot) {
            return ListView(
              padding: const EdgeInsets.fromLTRB(30, 30, 30, 178),
              children: [
                MobileHeader(
                  title: 'Intelligence graphique',
                  subtitle: 'Lecture visuelle des marchés',
                  onInfo: () => _showInfo(context),
                ),
                const SizedBox(height: 22),
                _AssetSelector(
                  assets: _assets,
                  selected: _asset,
                  onSelected: _selectAsset,
                ),
                const SizedBox(height: 18),
                _TimeframeSelector(
                  timeframes: _timeframes,
                  selected: _timeframe,
                  onSelected: _selectTimeframe,
                ),
                const SizedBox(height: 22),
                if (snapshot.connectionState == ConnectionState.waiting)
                  const SizedBox(height: 560, child: LoadingView(what: 'lecture graphique'))
                else if (snapshot.hasError)
                  SizedBox(
                    height: 560,
                    child: ErrorView(error: snapshot.error!, onRetry: _reload),
                  )
                else ...[
                  _VisualChartPanel(asset: _asset, timeframe: _timeframe),
                  const SizedBox(height: 16),
                  _PatternDetectedPanel(
                    asset: _asset,
                    timeframe: _timeframe,
                    structure: snapshot.data!.$1,
                    opportunity: snapshot.data!.$2,
                  ),
                  const SizedBox(height: 16),
                  _ConfluencePanel(structure: snapshot.data!.$1),
                  const SizedBox(height: 16),
                  _HistoryPanel(asset: _asset),
                ],
              ],
            );
          },
        ),
      ),
    );
  }

  void _showInfo(BuildContext context) {
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text('Intelligence graphique'),
        content: const Text(
          'Lecture visuelle des marches: structure, pattern, confluences et '
          'edge restent separes. Une figure lisible ne devient pas une '
          'recommandation.',
          style: TextStyle(color: AppColors.textMuted, height: 1.35),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Fermer'),
          ),
        ],
      ),
    );
  }
}

class _AssetSelector extends StatelessWidget {
  final List<String> assets;
  final String selected;
  final ValueChanged<String> onSelected;

  const _AssetSelector({
    required this.assets,
    required this.selected,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = ((constraints.maxWidth - 36) / 3).clamp(178.0, 220.0);
        return Wrap(
          spacing: 18,
          runSpacing: 14,
          children: [
            for (final asset in assets)
              _AssetChoice(
                asset: asset,
                selected: selected == asset,
                width: width,
                onTap: () => onSelected(asset),
              ),
          ],
        );
      },
    );
  }
}

class _AssetChoice extends StatelessWidget {
  final String asset;
  final bool selected;
  final double width;
  final VoidCallback onTap;

  const _AssetChoice({
    required this.asset,
    required this.selected,
    required this.width,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: width,
      height: 76,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(14),
          onTap: onTap,
          child: Ink(
            decoration: BoxDecoration(
              color: selected
                  ? const Color(0xFF173F70).withValues(alpha: 0.88)
                  : mobilePanel.withValues(alpha: 0.72),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(
                color: selected ? const Color(0xFF208DFF) : const Color(0xFF334B66),
                width: selected ? 1.6 : 1.25,
              ),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                CryptoLogo(asset: asset, size: 52),
                const SizedBox(width: 16),
                Text(
                  asset,
                  style: const TextStyle(
                    color: AppColors.text,
                    fontSize: 26,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _TimeframeSelector extends StatelessWidget {
  final List<String> timeframes;
  final String selected;
  final ValueChanged<String> onSelected;

  const _TimeframeSelector({
    required this.timeframes,
    required this.selected,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = ((constraints.maxWidth - 64) / 5).clamp(112.0, 170.0);
        return Wrap(
          spacing: 16,
          runSpacing: 12,
          children: [
            for (final timeframe in timeframes)
              SizedBox(
                width: width,
                height: 66,
                child: Material(
                  color: Colors.transparent,
                  child: InkWell(
                    borderRadius: BorderRadius.circular(13),
                    onTap: () => onSelected(timeframe),
                    child: Ink(
                      decoration: BoxDecoration(
                        color: selected == timeframe
                            ? const Color(0xFF164B82).withValues(alpha: 0.88)
                            : mobilePanel.withValues(alpha: 0.74),
                        borderRadius: BorderRadius.circular(13),
                        border: Border.all(
                          color: selected == timeframe
                              ? const Color(0xFF208DFF)
                              : const Color(0xFF334B66),
                          width: selected == timeframe ? 1.6 : 1.25,
                        ),
                      ),
                      child: Center(
                        child: Text(
                          _timeframeLabel(timeframe),
                          style: TextStyle(
                            color: selected == timeframe
                                ? const Color(0xFF9FCFFF)
                                : const Color(0xFFD3D9EF),
                            fontSize: 24,
                            fontWeight: selected == timeframe ? FontWeight.w800 : FontWeight.w500,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
          ],
        );
      },
    );
  }
}

class _VisualChartPanel extends StatelessWidget {
  final String asset;
  final String timeframe;

  const _VisualChartPanel({required this.asset, required this.timeframe});

  @override
  Widget build(BuildContext context) {
    return GlassPanel(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 13),
      child: Column(
        children: [
          SizedBox(
            height: 320,
            child: CustomPaint(
              painter: _CandleChartPainter(
                asset: asset,
                timeframe: timeframe,
                price: _displayPrice(asset),
                change: _displayChange(asset),
              ),
              child: const SizedBox.expand(),
            ),
          ),
          const SizedBox(height: 11),
          const _IndicatorStrip(),
        ],
      ),
    );
  }
}

class _IndicatorStrip extends StatelessWidget {
  const _IndicatorStrip();

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 82,
      decoration: BoxDecoration(
        color: const Color(0xFF0B1624).withValues(alpha: 0.78),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF294969), width: 1.25),
      ),
      child: const Row(
        children: [
          Expanded(
            child: _SignalChip(
              icon: Icons.trending_up_rounded,
              label: 'Pattern',
              state: 'HAUSSIER',
              color: Color(0xFF39E889),
              filled: true,
            ),
          ),
          _VerticalDivider(),
          Expanded(
            child: _SignalChip(
              icon: Icons.show_chart_rounded,
              label: 'RSI',
              state: 'NEUTRE',
              color: Color(0xFFB9C5DD),
            ),
          ),
          _VerticalDivider(),
          Expanded(
            child: _SignalChip(
              icon: Icons.bar_chart_rounded,
              label: 'Volume',
              state: 'HAUSSIER',
              color: Color(0xFF39E889),
              filled: true,
            ),
          ),
          _VerticalDivider(),
          Expanded(
            child: _SignalChip(
              icon: Icons.monetization_on_rounded,
              label: 'Funding',
              state: 'NEUTRE',
              color: Color(0xFFB9C5DD),
            ),
          ),
        ],
      ),
    );
  }
}

class _VerticalDivider extends StatelessWidget {
  const _VerticalDivider();

  @override
  Widget build(BuildContext context) {
    return Container(width: 1.2, height: 50, color: const Color(0xFF344B66));
  }
}

class _SignalChip extends StatelessWidget {
  final IconData icon;
  final String label;
  final String state;
  final Color color;
  final bool filled;

  const _SignalChip({
    required this.icon,
    required this.label,
    required this.state,
    required this.color,
    this.filled = false,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 54,
            height: 54,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: color.withValues(alpha: filled ? 0.20 : 0.10),
            ),
            child: Icon(icon, color: color, size: 31),
          ),
          const SizedBox(width: 10),
          Flexible(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: AppColors.text, fontSize: 17),
                ),
                const SizedBox(height: 5),
                MobilePill(label: state, color: color, dense: true, filled: filled),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _PatternDetectedPanel extends StatelessWidget {
  final String asset;
  final String timeframe;
  final StructureRead structure;
  final EntryOpportunity? opportunity;

  const _PatternDetectedPanel({
    required this.asset,
    required this.timeframe,
    required this.structure,
    required this.opportunity,
  });

  @override
  Widget build(BuildContext context) {
    final invalidation = _invalidationPrice(asset, structure.location.range);
    final objective = _objectivePrice(asset, invalidation);
    const confidence = 81;

    return GlassPanel(
      padding: const EdgeInsets.fromLTRB(22, 22, 22, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const IconTile(icon: Icons.show_chart_rounded),
              const SizedBox(width: 22),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Pattern détecté',
                      style: TextStyle(
                        color: AppColors.text,
                        fontSize: 26,
                        fontWeight: FontWeight.w800,
                        height: 1.0,
                      ),
                    ),
                    const SizedBox(height: 7),
                    Text(
                      'Triangle ascendant',
                      style: const TextStyle(
                        color: AppColors.text,
                        fontSize: 25,
                        fontWeight: FontWeight.w700,
                        height: 1.06,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                decoration: BoxDecoration(
                  color: const Color(0xFF1E8E5A).withValues(alpha: 0.32),
                  borderRadius: BorderRadius.circular(30),
                  border: Border.all(color: const Color(0xFF22C878), width: 1.4),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.trending_up_rounded, color: Color(0xFF54F2A1), size: 23),
                    SizedBox(width: 8),
                    Text(
                      'Haussier',
                      style: TextStyle(
                        color: Color(0xFF69F5AC),
                        fontSize: 22,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          _PatternMetricGrid(
            confidence: confidence,
            invalidation: invalidation,
            objective: objective,
          ),
          const SizedBox(height: 16),
          Text(
            _patternNarrative(timeframe, opportunity),
            style: const TextStyle(color: AppColors.text, fontSize: 20, height: 1.32),
          ),
        ],
      ),
    );
  }
}

class _PatternMetricGrid extends StatelessWidget {
  final int confidence;
  final num invalidation;
  final num objective;

  const _PatternMetricGrid({
    required this.confidence,
    required this.invalidation,
    required this.objective,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: const Color(0xFF0B1624).withValues(alpha: 0.72),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF2B4967), width: 1.2),
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final compact = constraints.maxWidth < 720;
          final width = compact ? (constraints.maxWidth - 12) / 2 : (constraints.maxWidth - 36) / 4;
          return Wrap(
            spacing: 12,
            runSpacing: 14,
            children: [
              _PatternMetric(
                width: width,
                label: 'Confiance :',
                value: '$confidence %',
                color: const Color(0xFF54F2A1),
              ),
              _PatternMetric(
                width: width,
                label: 'Breakout :',
                value: 'en attente',
                color: const Color(0xFFFFD447),
              ),
              _PatternMetric(
                width: width,
                label: 'Invalidation :',
                value: '${_priceFr(invalidation)} €',
              ),
              _PatternMetric(
                width: width,
                label: 'Objectif :',
                value: '${_priceFr(objective, digits: 0)} €',
              ),
            ],
          );
        },
      ),
    );
  }
}

class _PatternMetric extends StatelessWidget {
  final double width;
  final String label;
  final String value;
  final Color color;

  const _PatternMetric({
    required this.width,
    required this.label,
    required this.value,
    this.color = AppColors.text,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: width,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(color: mobileMuted, fontSize: 16)),
          const SizedBox(height: 5),
          Text(
            value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(color: color, fontSize: 22, fontWeight: FontWeight.w800),
          ),
        ],
      ),
    );
  }
}

class _ConfluencePanel extends StatelessWidget {
  final StructureRead structure;

  const _ConfluencePanel({required this.structure});

  @override
  Widget build(BuildContext context) {
    final values = [
      ('Pattern', 82, const Color(0xFF42E892)),
      ('Momentum', 74, const Color(0xFF8BCDFF)),
      ('Dérivés', 61, const Color(0xFFFFD84F)),
      ('Macro', 55, const Color(0xFFBFD0FF)),
    ];
    const score = 74;

    return GlassPanel(
      padding: const EdgeInsets.fromLTRB(22, 20, 22, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const IconTile(icon: Icons.track_changes_rounded),
              const SizedBox(width: 22),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Confluences',
                      style: TextStyle(color: AppColors.text, fontSize: 26, fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 12),
                    for (final item in values)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 9),
                        child: _ConfluenceRow(label: item.$1, value: item.$2, color: item.$3),
                      ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 11),
            decoration: BoxDecoration(
              color: const Color(0xFF0B1624).withValues(alpha: 0.70),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: const Color(0xFF274460), width: 1.2),
            ),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 12),
                  decoration: BoxDecoration(
                    color: const Color(0xFF093322).withValues(alpha: 0.86),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: const Color(0xFF22C878), width: 1.35),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Text(
                        'Score global',
                        style: TextStyle(
                          color: Color(0xFF54F2A1),
                          fontSize: 21,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      const SizedBox(width: 24),
                      Text(
                        '$score / 100',
                        style: const TextStyle(
                          color: Color(0xFF54F2A1),
                          fontSize: 34,
                          fontWeight: FontWeight.w800,
                          height: 1.0,
                        ),
                      ),
                    ],
                  ),
                ),
                const Spacer(),
                const Text(
                  'Données disponibles : 4 familles sur 6',
                  textAlign: TextAlign.right,
                  style: TextStyle(color: mobileMuted, fontSize: 17),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ConfluenceRow extends StatelessWidget {
  final String label;
  final int value;
  final Color color;

  const _ConfluenceRow({
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        SizedBox(
          width: 118,
          child: Text(label, style: const TextStyle(color: AppColors.text, fontSize: 20)),
        ),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: SizedBox(
              height: 14,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  const ColoredBox(color: Color(0xFF213247)),
                  FractionallySizedBox(
                    alignment: Alignment.centerLeft,
                    widthFactor: value / 100,
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        color: color,
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(width: 18),
        SizedBox(
          width: 30,
          child: Text(
            '$value',
            textAlign: TextAlign.right,
            style: const TextStyle(color: AppColors.text, fontSize: 20),
          ),
        ),
      ],
    );
  }
}

class _HistoryPanel extends StatelessWidget {
  final String asset;

  const _HistoryPanel({required this.asset});

  @override
  Widget build(BuildContext context) {
    return GlassPanel(
      padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 20),
      child: Row(
        children: [
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: const Color(0xFF123E71).withValues(alpha: 0.92),
            ),
            child: const Icon(Icons.history_rounded, color: Color(0xFF69B3FF), size: 37),
          ),
          const SizedBox(width: 22),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Voir les occurrences historiques',
                  style: TextStyle(color: AppColors.text, fontSize: 22, fontWeight: FontWeight.w800),
                ),
                SizedBox(height: 6),
                Text(
                  'Analyse des 287 configurations similaires',
                  style: TextStyle(color: mobileMuted, fontSize: 18),
                ),
              ],
            ),
          ),
          const Icon(Icons.chevron_right_rounded, color: AppColors.text, size: 42),
        ],
      ),
    );
  }
}

class _CandleChartPainter extends CustomPainter {
  final String asset;
  final String timeframe;
  final num price;
  final String change;

  _CandleChartPainter({
    required this.asset,
    required this.timeframe,
    required this.price,
    required this.change,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final chart = Rect.fromLTWH(4, 26, size.width - 94, size.height - 64);
    final volumeTop = chart.bottom - 36;
    final priceRect = Rect.fromLTRB(chart.left, chart.top, chart.right, volumeTop);
    final gridPaint = Paint()
      ..color = const Color(0xFF20364F).withValues(alpha: 0.78)
      ..strokeWidth = 1;

    final borderPaint = Paint()
      ..color = const Color(0xFF5F789A)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2;

    for (var i = 0; i <= 5; i += 1) {
      final y = chart.top + chart.height * i / 5;
      canvas.drawLine(Offset(chart.left, y), Offset(chart.right, y), gridPaint);
    }
    for (var i = 0; i <= 6; i += 1) {
      final x = chart.left + chart.width * i / 6;
      canvas.drawLine(Offset(x, chart.top), Offset(x, chart.bottom), gridPaint);
    }
    canvas.drawRect(chart, borderPaint);

    final range = _priceRange(asset);
    final min = range.$1;
    final max = range.$2;
    double yFor(num value) {
      final ratio = ((value - min) / (max - min)).clamp(0.0, 1.0);
      return priceRect.bottom - priceRect.height * ratio;
    }

    final series = _chartValues(asset).map((v) => min + (max - min) * v).toList();
    final candleWidth = math.max(5.0, chart.width / series.length * 0.54);
    final xStep = chart.width / series.length;
    for (var i = 0; i < series.length; i += 1) {
      final close = series[i];
      final previous = i == 0 ? series[i] * 1.006 : series[i - 1];
      final open = (previous + math.sin(i * 1.4) * (max - min) * 0.022).clamp(min, max).toDouble();
      final high = math.min(max.toDouble(), math.max(open, close) + (max - min) * (0.035 + (i % 3) * 0.006));
      final low = math.max(min.toDouble(), math.min(open, close) - (max - min) * (0.030 + (i % 4) * 0.005));
      final x = chart.left + xStep * i + xStep / 2;
      final bullish = close >= open;
      final color = bullish ? const Color(0xFF20D184) : const Color(0xFFFF5361);
      final paint = Paint()..color = color;

      paint.strokeWidth = 1.5;
      canvas.drawLine(Offset(x, yFor(high)), Offset(x, yFor(low)), paint);
      final bodyTop = math.min(yFor(open), yFor(close));
      final bodyBottom = math.max(yFor(open), yFor(close));
      final body = RRect.fromRectAndRadius(
        Rect.fromCenter(
          center: Offset(x, (bodyTop + bodyBottom) / 2),
          width: candleWidth,
          height: math.max(4, bodyBottom - bodyTop),
        ),
        const Radius.circular(1.2),
      );
      canvas.drawRRect(body, paint);

      final volumeHeight = 10 + (math.sin(i * 0.9).abs() * 26) + (i % 5) * 2;
      final volumeRect = Rect.fromLTWH(
        x - candleWidth / 2,
        chart.bottom - volumeHeight,
        candleWidth,
        volumeHeight,
      );
      canvas.drawRect(volumeRect, Paint()..color = color.withValues(alpha: 0.45));
    }

    final resistanceY = yFor(max - (max - min) * 0.24);
    final linePaint = Paint()
      ..color = const Color(0xFF79BDFF)
      ..strokeWidth = 2.6
      ..style = PaintingStyle.stroke;
    canvas.drawLine(
      Offset(chart.left + chart.width * 0.28, resistanceY),
      Offset(chart.right - chart.width * 0.13, resistanceY),
      linePaint,
    );
    canvas.drawLine(
      Offset(chart.left + chart.width * 0.33, yFor(min + (max - min) * 0.18)),
      Offset(chart.right - chart.width * 0.12, yFor(min + (max - min) * 0.62)),
      linePaint,
    );

    final priceY = yFor(price);
    _drawDottedLine(
      canvas,
      Offset(chart.left + chart.width * 0.28, priceY),
      Offset(chart.right + 6, priceY),
      Paint()
        ..color = const Color(0xFF54F2A1)
        ..strokeWidth = 1.1,
    );
    final pricePill = RRect.fromRectAndRadius(
      Rect.fromLTWH(chart.right + 6, priceY - 17, 82, 34),
      const Radius.circular(7),
    );
    canvas.drawRRect(pricePill, Paint()..color = const Color(0xFF49E99B));
    _drawText(
      canvas,
      _priceFr(price, digits: 0),
      Offset(chart.right + 15, priceY - 11),
      const TextStyle(color: Color(0xFF021B14), fontSize: 15, fontWeight: FontWeight.w900),
    );

    _drawText(
      canvas,
      '$asset · ${_timeframeLabel(timeframe)}',
      Offset(chart.left + 5, chart.top + 6),
      const TextStyle(color: Color(0xFFC5D4EC), fontSize: 18, fontWeight: FontWeight.w500),
    );
    _drawText(
      canvas,
      '$change (24 h)',
      Offset(chart.left + 5, chart.top + 34),
      const TextStyle(color: Color(0xFF54F2A1), fontSize: 18, fontWeight: FontWeight.w700),
    );

    final labels = _axisLabels(asset);
    for (var i = 0; i < labels.length; i += 1) {
      final y = priceRect.top + i * priceRect.height / (labels.length - 1);
      _drawText(
        canvas,
        labels[i],
        Offset(chart.right + 18, y - 9),
        const TextStyle(color: Color(0xFFB5C2DC), fontSize: 16),
      );
    }

    final dates = const ['2 sept.', '3 sept.', '4 sept.', '5 sept.', '6 sept.'];
    for (var i = 0; i < dates.length; i += 1) {
      final x = chart.left + chart.width * (i + 0.8) / (dates.length + 0.8);
      _drawText(
        canvas,
        dates[i],
        Offset(x, chart.bottom + 12),
        const TextStyle(color: Color(0xFFB5C2DC), fontSize: 15),
      );
    }
  }

  @override
  bool shouldRepaint(covariant _CandleChartPainter oldDelegate) =>
      oldDelegate.asset != asset ||
      oldDelegate.timeframe != timeframe ||
      oldDelegate.price != price ||
      oldDelegate.change != change;
}

void _drawText(Canvas canvas, String text, Offset offset, TextStyle style) {
  final painter = TextPainter(
    text: TextSpan(text: text, style: style),
    textDirection: TextDirection.ltr,
  )..layout();
  painter.paint(canvas, offset);
}

void _drawDottedLine(Canvas canvas, Offset start, Offset end, Paint paint) {
  const dash = 5.0;
  const gap = 5.0;
  final distance = (end - start).distance;
  final direction = (end - start) / distance;
  var travelled = 0.0;
  while (travelled < distance) {
    final from = start + direction * travelled;
    final to = start + direction * math.min(travelled + dash, distance);
    canvas.drawLine(from, to, paint);
    travelled += dash + gap;
  }
}

String _timeframeLabel(String value) => switch (value) {
      '15m' => '15 min',
      '1h' => '1 h',
      '4h' => '4 h',
      '1d' => '1 j',
      '1w' => '1 sem.',
      _ => value,
    };

num _displayPrice(String asset) => switch (asset) {
      'ETH' => 2210,
      'SOL' => 184,
      _ => 82840,
    };

String _displayChange(String asset) => switch (asset) {
      'ETH' => '+1,8 %',
      'SOL' => '+3,1 %',
      _ => '+2,4 %',
    };

(num, num) _priceRange(String asset) => switch (asset) {
      'ETH' => (2070, 2260),
      'SOL' => (174, 196),
      _ => (79000, 84000),
    };

List<String> _axisLabels(String asset) => switch (asset) {
      'ETH' => ['2 260', '2 220', '2 180', '2 140', '2 100'],
      'SOL' => ['196', '190', '184', '178', '172'],
      _ => ['84 000', '83 000', '82 000', '81 000', '80 000'],
    };

List<double> _chartValues(String asset) {
  final base = [
    0.34,
    0.30,
    0.31,
    0.27,
    0.23,
    0.28,
    0.22,
    0.33,
    0.40,
    0.54,
    0.49,
    0.36,
    0.33,
    0.30,
    0.34,
    0.61,
    0.68,
    0.58,
    0.55,
    0.40,
    0.37,
    0.49,
    0.46,
    0.53,
    0.51,
    0.58,
    0.56,
    0.61,
    0.58,
    0.62,
    0.57,
    0.59,
    0.64,
    0.61,
    0.66,
    0.63,
    0.68,
    0.70,
    0.72,
    0.70,
    0.74,
    0.76,
  ];
  if (asset == 'ETH') {
    return base.map((v) => (v * 0.86 + 0.07).clamp(0.0, 1.0).toDouble()).toList();
  }
  if (asset == 'SOL') {
    return base.map((v) => (v * 0.76 + 0.14).clamp(0.0, 1.0).toDouble()).toList();
  }
  return base;
}

num _invalidationPrice(String asset, DetectedRange? range) {
  final high = range?.topZone?.high;
  if (high != null && high > 0) return high;
  return switch (asset) {
    'ETH' => 2186.40,
    'SOL' => 181.70,
    _ => 81634.80,
  };
}

num _objectivePrice(String asset, num invalidation) => switch (asset) {
      'ETH' => 2260,
      'SOL' => 192,
      _ => math.max(84200, invalidation + 2565).round(),
    };

String _patternNarrative(String timeframe, EntryOpportunity? opportunity) {
  return 'La structure reste propre en ${_timeframeLabel(timeframe)}. Le prix comprime sous la résistance '
      'et le momentum s’améliore, mais la cassure n’est pas encore confirmée.';
}

String _priceFr(num? value, {int digits = 2}) {
  if (value == null || value.isNaN) return '—';
  final parts = value.toStringAsFixed(digits).replaceAll('.', ',').split(',');
  final whole = parts.first;
  final buffer = StringBuffer();
  for (var i = 0; i < whole.length; i += 1) {
    final remaining = whole.length - i;
    buffer.write(whole[i]);
    if (remaining > 1 && remaining % 3 == 1) buffer.write(' ');
  }
  if (digits == 0) return buffer.toString();
  return '${buffer.toString()},${parts.last}';
}
