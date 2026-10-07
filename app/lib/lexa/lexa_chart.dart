/// Interactive market chart for one external-analysis plan.
///
/// Candles and annotations arrive in the same private plan response. The
/// widget only filters and draws them: it never derives a level from price.
library;

import 'package:flutter/material.dart';

import '../api/models.dart';
import '../chart/candle_chart.dart';
import '../chart/chart_layers.dart';
import '../widgets/mobile_kit.dart';
import 'lexa_models.dart';
import 'lexa_ui.dart';

const _buy = Color(0xFF32DF98);
const _confirm = Color(0xFF5DA9FF);
const _info = Color(0xFFE7EEF8);
const _target = Color(0xFFF5C451);
const _danger = Color(0xFFFF6673);
const _wait = Color(0xFFFFD45C);
const _history = Color(0xFF8C9AAD);

class LexaPlanChart extends StatefulWidget {
  final Map<String, dynamic> plan;

  const LexaPlanChart({super.key, required this.plan});

  @override
  State<LexaPlanChart> createState() => _LexaPlanChartState();
}

class _LexaPlanChartState extends State<LexaPlanChart> {
  bool _historyVisible = false;
  final Set<String> _categories = {
    'ORDERS',
    'STRUCTURE',
    'CONFIRMATION',
    'TARGETS',
    'INVALIDATION',
  };

  static const _layers = ChartLayerSet({
    ChartLayer.grid,
    ChartLayer.candles,
    ChartLayer.levels,
    ChartLayer.eventMarkers,
    ChartLayer.labels,
    ChartLayer.currentPrice,
    ChartLayer.crosshair,
  });

  Map<String, dynamic> get _chart =>
      ((widget.plan['chart'] as Map?) ?? const {}).cast<String, dynamic>();

  List<Map<String, dynamic>> _maps(Object? value) => [
        for (final item in (value as List? ?? const []))
          (item as Map).cast<String, dynamic>(),
      ];

  String _category(String kind) => switch (kind) {
        'BUY_ZONE' || 'REINFORCEMENT' || 'SELL' => 'ORDERS',
        'CONFIRMATION' || 'BREAKOUT' => 'CONFIRMATION',
        'TARGET' || 'TAKE_PROFIT' => 'TARGETS',
        'INVALIDATION' => 'INVALIDATION',
        _ => 'STRUCTURE',
      };

  Color _colour(String kind, bool historical) {
    if (historical) return _history;
    return switch (kind) {
      'BUY_ZONE' || 'REINFORCEMENT' => _buy,
      'CONFIRMATION' || 'BREAKOUT' => _confirm,
      'TARGET' || 'TAKE_PROFIT' => _target,
      'SELL' || 'INVALIDATION' => _danger,
      'WAIT' || 'WATCH' => _wait,
      _ => _info,
    };
  }

  List<ChartPriceAnnotation> get _levels {
    final out = <ChartPriceAnnotation>[];
    for (final row in _maps(_chart['levels'])) {
      final selected = row['selected'] == true;
      if (!selected && !_historyVisible) continue;
      final kind = '${row['kind']}';
      if (!_categories.contains(_category(kind))) continue;
      final low = (row['low'] as num?)?.toDouble();
      final high = (row['high'] as num?)?.toDouble();
      if (low == null || low <= 0) continue;
      final state = (row['state'] as Map?)?.cast<String, dynamic>();
      final amount = (row['amount_eur'] as num?)?.toDouble();
      final pct = (row['allocation_pct'] as num?)?.toDouble();
      final details = <String>[
        if (amount != null) fmtEur(amount),
        if (pct != null) '${pct.toStringAsFixed(0)} %',
        if (state?['label'] != null) '${state!['label']}',
      ];
      out.add(ChartPriceAnnotation(
        id: '${row['analysis_id']}-${row['level_id']}',
        label:
            selected ? '${row['label']}' : '#${row['version']} ${row['label']}',
        low: low,
        high: high,
        color: _colour(kind, !selected),
        detail: details.join(' · '),
        historical: !selected,
      ));
    }
    return out;
  }

  List<ChartTimeAnnotation> get _events => [
        for (final row in _maps(_chart['analyses']))
          if (row['selected'] == true || _historyVisible)
            if (DateTime.tryParse('${row['published_at']}') case final time?)
              ChartTimeAnnotation(
                id: 'analysis-${row['analysis_id']}',
                time: time,
                label: 'ANALYSE #${row['version']}',
                color: row['selected'] == true ? _confirm : _history,
                historical: row['selected'] != true,
              ),
      ];

  List<CandlePoint> get _candles => [
        for (final row in _maps(_chart['candles'])) CandlePoint.fromJson(row),
      ].where((candle) => candle.low > 0 && candle.high > 0).toList();

  void _toggle(String category) => setState(() {
        if (!_categories.remove(category)) _categories.add(category);
      });

  @override
  Widget build(BuildContext context) {
    final candles = _candles;
    if (_chart.isEmpty) return const SizedBox.shrink();
    return GlassPanel(
      key: const ValueKey('lexa-market-chart'),
      padding: const EdgeInsets.all(10),
      borderColor: _confirm.withValues(alpha: .7),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Padding(
            padding: EdgeInsets.fromLTRB(6, 4, 6, 8),
            child: LexaSectionTitle(emoji: '📈', text: 'Graphique du plan'),
          ),
          if (candles.isEmpty)
            const Padding(
              padding: EdgeInsets.all(18),
              child: Text(
                'Bougies indisponibles pour cette crypto : aucun graphique n’est inventé.',
                style: TextStyle(color: lexaMuted, height: 1.35),
              ),
            )
          else ...[
            LayoutBuilder(builder: (context, constraints) {
              final height = (constraints.maxWidth * .88).clamp(330.0, 410.0);
              return SizedBox(
                height: height,
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(12),
                  child: CandleChart(
                    key: ValueKey(
                        '${widget.plan['analysis_id']}-${_historyVisible ? 'history' : 'current'}-${_categories.join()}'),
                    candles: candles,
                    timeframe: '${_chart['timeframe'] ?? '4h'}',
                    layers: _layers,
                    pair: '${_chart['pair'] ?? widget.plan['asset']}',
                    source: '${_chart['source'] ?? ''}',
                    priceAnnotations: _levels,
                    timeAnnotations: _events,
                  ),
                ),
              );
            }),
            const SizedBox(height: 8),
            lexaNote(
              'Pincer pour zoomer · glisser pour remonter le temps · appui long pour lire une bougie.',
            ),
          ],
          const SizedBox(height: 8),
          Wrap(
            spacing: 7,
            runSpacing: 7,
            children: [
              FilterChip(
                selected: _historyVisible,
                label: const Text('Anciennes analyses'),
                onSelected: (value) => setState(() => _historyVisible = value),
              ),
              for (final item in const {
                'ORDERS': 'Ordres',
                'STRUCTURE': 'Supports / résistances',
                'CONFIRMATION': 'Confirmations',
                'TARGETS': 'TP',
                'INVALIDATION': 'Invalidations',
              }.entries)
                FilterChip(
                  selected: _categories.contains(item.key),
                  label: Text(item.value),
                  onSelected: (_) => _toggle(item.key),
                ),
            ],
          ),
          const SizedBox(height: 6),
          lexaNote(
            'Traits pleins : analyse affichée · pointillés gris : historique. '
            'Une bande correspond à une zone réellement donnée par la source.',
          ),
        ],
      ),
    );
  }
}
