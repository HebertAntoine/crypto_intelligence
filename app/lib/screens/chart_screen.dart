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
import '../chart/candle_chart.dart';
import '../chart/chart_layers.dart';
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
  late Future<_ChartData> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<_ChartData> _load() async {
    Future<T?> safe<T>(Future<T> request) async {
      try {
        return await request;
      } catch (_) {
        return null;
      }
    }

    final structure =
        await widget.client.structure(_asset, timeframe: _timeframe);
    final opportunity = await safe(
        widget.client.entryOpportunity(_asset, timeframe: _timeframe));
    final chart = await safe(widget.client.chart(
      _asset,
      timeframe: _timeframe,
      period: _periodForTimeframe(_timeframe),
    ));
    final today = await safe(widget.client.today(_asset));
    return _ChartData(
      structure: structure,
      opportunity: opportunity,
      chart: chart,
      today: today,
    );
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
        child: FutureBuilder<_ChartData>(
          future: _future,
          builder: (context, snapshot) {
            return MobileScrollView(
              padding: const EdgeInsets.fromLTRB(30, 30, 30, 260),
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
                  const SizedBox(
                      height: 560,
                      child: LoadingView(what: 'lecture graphique'))
                else if (snapshot.hasError)
                  SizedBox(
                    height: 560,
                    child: ErrorView(error: snapshot.error!, onRetry: _reload),
                  )
                else ...[
                  _VisualChartPanel(
                    asset: _asset,
                    timeframe: _timeframe,
                    data: snapshot.data!,
                  ),
                  const SizedBox(height: 16),
                  _PatternDetectedPanel(
                    asset: _asset,
                    timeframe: _timeframe,
                    data: snapshot.data!,
                  ),
                  const SizedBox(height: 16),
                  _ConfluencePanel(data: snapshot.data!),
                  const SizedBox(height: 16),
                  _HistoryPanel(
                    asset: _asset,
                    data: snapshot.data!,
                  ),
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

class _ChartData {
  final StructureRead structure;
  final EntryOpportunity? opportunity;
  final ChartRead? chart;
  final TodayRead? today;

  const _ChartData({
    required this.structure,
    required this.opportunity,
    required this.chart,
    required this.today,
  });

  double? get price => chart?.lastPrice ?? structure.location.price;

  double? get changePct => chart?.changePct;

  DetectedPattern? get primaryPattern =>
      structure.patterns.isEmpty ? null : structure.patterns.first;
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
                color: selected
                    ? const Color(0xFF208DFF)
                    : const Color(0xFF334B66),
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
                            fontWeight: selected == timeframe
                                ? FontWeight.w800
                                : FontWeight.w500,
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

class _VisualChartPanel extends StatefulWidget {
  final String asset;
  final String timeframe;
  final _ChartData data;

  const _VisualChartPanel({
    required this.asset,
    required this.timeframe,
    required this.data,
  });

  @override
  State<_VisualChartPanel> createState() => _VisualChartPanelState();
}

class _VisualChartPanelState extends State<_VisualChartPanel> {
  ChartLayerSet _layers = ChartLayerSet.initial();

  @override
  Widget build(BuildContext context) {
    final candles = widget.data.chart?.candles ?? const <CandlePoint>[];
    return GlassPanel(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 13),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // §5: le graphique est la priorité visuelle. Il occupait 320 px
          // fixes; il prend maintenant une hauteur proportionnée à l'écran,
          // bornée pour rester utilisable en paysage.
          LayoutBuilder(
            builder: (context, constraints) {
              final height = math.max(
                360.0,
                math.min(MediaQuery.sizeOf(context).height * 0.58, 640.0),
              );
              return SizedBox(
                height: height,
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(12),
                  child: CandleChart(
                    // La clé force une fenêtre neuve au changement d'actif ou
                    // d'unité: garder la précédente montrerait un intervalle
                    // qui n'existe pas dans le nouveau jeu.
                    key: ValueKey('${widget.asset}-${widget.timeframe}'),
                    candles: candles,
                    timeframe: widget.timeframe,
                    layers: _layers,
                  ),
                ),
              );
            },
          ),
          const SizedBox(height: 10),
          _LayerBar(
            layers: _layers,
            onToggle: (layer) =>
                setState(() => _layers = _layers.toggled(layer)),
          ),
          const SizedBox(height: 11),
          _IndicatorStrip(data: widget.data),
        ],
      ),
    );
  }
}

/// La barre de calques. Chaque bouton est un interrupteur, rien de plus:
/// aucun d'eux ne modifie les données, seulement ce qui est peint.
class _LayerBar extends StatelessWidget {
  final ChartLayerSet layers;
  final void Function(ChartLayer) onToggle;

  const _LayerBar({required this.layers, required this.onToggle});

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: [
            for (final layer in ChartLayerSet.toggleable)
              Padding(
                padding: const EdgeInsets.only(right: 7),
                child: _LayerChip(
                  label: layer.label,
                  active: layers.isVisible(layer),
                  onTap: () => onToggle(layer),
                ),
              ),
          ],
        ),
      );
}

class _LayerChip extends StatelessWidget {
  final String label;
  final bool active;
  final VoidCallback onTap;

  const _LayerChip({
    required this.label,
    required this.active,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) => Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(9),
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
            decoration: BoxDecoration(
              color: active ? const Color(0xFF11477B) : const Color(0xFF091B2B),
              borderRadius: BorderRadius.circular(9),
              border: Border.all(
                color: active
                    ? const Color(0xFF199CFF)
                    : const Color(0xFF284A68),
              ),
            ),
            child: Text(
              label,
              style: TextStyle(
                color: active
                    ? const Color(0xFF8DCAFF)
                    : const Color(0xFFC2CEE0),
                fontSize: 12.5,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ),
      );
}

class _IndicatorStrip extends StatelessWidget {
  final _ChartData data;

  const _IndicatorStrip({required this.data});

  @override
  Widget build(BuildContext context) {
    final signals = _indicatorSignals(data);
    return Container(
      height: 82,
      decoration: BoxDecoration(
        color: const Color(0xFF0B1624).withValues(alpha: 0.78),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF294969), width: 1.25),
      ),
      child: Row(
        children: [
          for (var i = 0; i < signals.length; i += 1) ...[
            Expanded(
              child: _SignalChip(
                icon: signals[i].icon,
                label: signals[i].label,
                state: signals[i].state,
                color: signals[i].color,
                filled: signals[i].filled,
              ),
            ),
            if (i != signals.length - 1) const _VerticalDivider(),
          ],
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
                MobilePill(
                    label: state, color: color, dense: true, filled: filled),
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
  final _ChartData data;

  const _PatternDetectedPanel({
    required this.asset,
    required this.timeframe,
    required this.data,
  });

  @override
  Widget build(BuildContext context) {
    final structure = data.structure;
    final opportunity = data.opportunity;
    final pattern = data.primaryPattern;
    final title = pattern == null ? 'Structure détectée' : 'Pattern détecté';
    final name = pattern == null
        ? _structureName(structure)
        : _patternName(pattern.name);
    final direction = _patternDirection(pattern, structure, opportunity);
    final directionColor = _directionTone(direction);
    final confidence = _recognitionScore(pattern, structure);
    final invalidation = _extractPrice(opportunity?.invalidation) ??
        _extractPrice(pattern?.invalidationRule) ??
        _levelValue(pattern?.keyLevels, const ['invalidation', 'neckline']) ??
        _rangeInvalidation(structure.location);
    final objective =
        _levelValue(pattern?.keyLevels, const ['objective', 'target']);
    final breakout = _breakoutLabel(pattern, opportunity);

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
                    Text(
                      title,
                      style: TextStyle(
                        color: AppColors.text,
                        fontSize: 26,
                        fontWeight: FontWeight.w800,
                        height: 1.0,
                      ),
                    ),
                    const SizedBox(height: 7),
                    Text(
                      name,
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
                padding:
                    const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                decoration: BoxDecoration(
                  color: directionColor.withValues(alpha: 0.22),
                  borderRadius: BorderRadius.circular(30),
                  border: Border.all(color: directionColor, width: 1.4),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(_directionIcon(direction),
                        color: directionColor, size: 23),
                    const SizedBox(width: 8),
                    Text(
                      _directionShortLabel(direction),
                      style: TextStyle(
                        color: directionColor,
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
            breakout: breakout,
            invalidation: invalidation,
            objective: objective,
          ),
          const SizedBox(height: 16),
          Text(
            _patternNarrative(timeframe, structure, pattern, opportunity),
            style: const TextStyle(
                color: AppColors.text, fontSize: 20, height: 1.32),
          ),
        ],
      ),
    );
  }
}

class _PatternMetricGrid extends StatelessWidget {
  final int confidence;
  final String breakout;
  final num? invalidation;
  final num? objective;

  const _PatternMetricGrid({
    required this.confidence,
    required this.breakout,
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
          final width = compact
              ? (constraints.maxWidth - 12) / 2
              : (constraints.maxWidth - 36) / 4;
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
                value: breakout,
                color: const Color(0xFFFFD447),
              ),
              _PatternMetric(
                width: width,
                label: 'Invalidation :',
                value: _priceOrUnavailable(invalidation),
              ),
              _PatternMetric(
                width: width,
                label: 'Objectif :',
                value: _priceOrUnavailable(objective, digits: 0),
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
            style: TextStyle(
                color: color, fontSize: 22, fontWeight: FontWeight.w800),
          ),
        ],
      ),
    );
  }
}

class _ConfluencePanel extends StatelessWidget {
  final _ChartData data;

  const _ConfluencePanel({required this.data});

  @override
  Widget build(BuildContext context) {
    final values = _confluenceItems(data);
    final score = values.isEmpty
        ? 0
        : (values.map((item) => item.value).reduce((a, b) => a + b) /
                values.length)
            .round();

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
                      style: TextStyle(
                          color: AppColors.text,
                          fontSize: 26,
                          fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 12),
                    if (values.isEmpty)
                      const Text(
                        'Aucune famille de données exploitable pour cette combinaison.',
                        style: TextStyle(color: mobileMuted, fontSize: 17),
                      )
                    else
                      for (final item in values)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 9),
                          child: _ConfluenceRow(
                              label: item.label,
                              value: item.value,
                              color: item.color),
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
                  padding:
                      const EdgeInsets.symmetric(horizontal: 22, vertical: 12),
                  decoration: BoxDecoration(
                    color: const Color(0xFF093322).withValues(alpha: 0.86),
                    borderRadius: BorderRadius.circular(12),
                    border:
                        Border.all(color: const Color(0xFF22C878), width: 1.35),
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
                Text(
                  'Données disponibles : ${values.length} familles sur 5',
                  textAlign: TextAlign.right,
                  style: const TextStyle(color: mobileMuted, fontSize: 17),
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
          child: Text(label,
              style: const TextStyle(color: AppColors.text, fontSize: 20)),
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
  final _ChartData data;

  const _HistoryPanel({required this.asset, required this.data});

  @override
  Widget build(BuildContext context) {
    final count = _historyCount(data);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(17),
        onTap: () => _showHistorySheet(context, asset, data),
        child: GlassPanel(
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
                child: const Icon(Icons.history_rounded,
                    color: Color(0xFF69B3FF), size: 37),
              ),
              const SizedBox(width: 22),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Voir les occurrences historiques',
                      style: TextStyle(
                          color: AppColors.text,
                          fontSize: 22,
                          fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'Analyse de $count éléments similaires disponibles',
                      style: const TextStyle(color: mobileMuted, fontSize: 18),
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right_rounded,
                  color: AppColors.text, size: 42),
            ],
          ),
        ),
      ),
    );
  }

  void _showHistorySheet(
    BuildContext context,
    String asset,
    _ChartData data,
  ) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: mobilePanel,
      builder: (context) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.72,
        minChildSize: 0.36,
        maxChildSize: 0.92,
        builder: (context, controller) => ListView(
          controller: controller,
          padding: const EdgeInsets.fromLTRB(22, 18, 22, 32),
          children: [
            Row(
              children: [
                CryptoLogo(asset: asset, size: 52),
                const SizedBox(width: 14),
                Expanded(
                  child: Text(
                    '$asset · historique',
                    style: const TextStyle(
                      color: AppColors.text,
                      fontSize: 24,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 18),
            _SheetLine(
              label: 'Bougies',
              value: data.chart?.available == true
                  ? '${data.chart!.bars} barres ${data.chart!.timeframe}'
                  : 'chart non disponible, lecture structurelle affichée',
            ),
            _SheetLine(
              label: 'Structure',
              value: _structureName(data.structure),
            ),
            _SheetLine(
              label: 'Confiance',
              value:
                  '${_recognitionScore(data.primaryPattern, data.structure)} / 100',
            ),
            if (data.structure.location.explanation.isNotEmpty) ...[
              const SizedBox(height: 14),
              const Text(
                'Éléments de lecture',
                style: TextStyle(
                  color: AppColors.text,
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 8),
              for (final line in data.structure.location.explanation.take(8))
                Text(
                  '• ${_translateSentence(line)}',
                  style: const TextStyle(
                    color: mobileMuted,
                    fontSize: 15,
                    height: 1.35,
                  ),
                ),
            ],
            if (data.structure.marketStructure.events.isNotEmpty) ...[
              const SizedBox(height: 16),
              const Text(
                'Évènements détectés',
                style: TextStyle(
                  color: AppColors.text,
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 8),
              for (final event in data.structure.marketStructure.events.take(8))
                Text(
                  '${event.kind} ${_directionShortLabel(event.direction)} · '
                  '${_priceFr(event.level, digits: 0)}',
                  style: const TextStyle(
                    color: mobileMuted,
                    fontSize: 15,
                    height: 1.35,
                  ),
                ),
            ],
            const SizedBox(height: 18),
            if (data.opportunity?.measuredEdge != null)
              MobilePill(
                label: _edgeLabel(data.opportunity!.measuredEdge),
                color: _edgeTone(data.opportunity!.measuredEdge),
              ),
          ],
        ),
      ),
    );
  }
}

class _SheetLine extends StatelessWidget {
  final String label;
  final String value;

  const _SheetLine({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 118,
            child: Text(
              label,
              style: const TextStyle(color: mobileMuted, fontSize: 15),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(
                color: AppColors.text,
                fontSize: 15,
                fontWeight: FontWeight.w600,
                height: 1.25,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ConfluenceItem {
  final String label;
  final int value;
  final Color color;

  const _ConfluenceItem(this.label, this.value, this.color);
}

class _IndicatorState {
  final IconData icon;
  final String label;
  final String state;
  final Color color;
  final bool filled;

  const _IndicatorState({
    required this.icon,
    required this.label,
    required this.state,
    required this.color,
    this.filled = false,
  });
}

/// Le libellé court d'une unité de temps dans le sélecteur.
String _timeframeLabel(String timeframe) => switch (timeframe) {
      '15m' => '15 min',
      '1h' => '1 h',
      '4h' => '4 h',
      '1d' => '1 j',
      '1w' => '1 sem.',
      _ => timeframe,
    };

/// La profondeur demandée à l'API pour une unité donnée.
///
/// Une vue hebdomadaire sur sept jours ne montrerait qu'une bougie: la période
/// suit l'unité plutôt qu'une constante unique.
String _periodForTimeframe(String timeframe) => switch (timeframe) {
      '15m' => '7d',
      '1h' => '30d',
      '4h' => '3m',
      '1d' => '1y',
      '1w' => 'max',
      _ => '3m',
    };

List<_IndicatorState> _indicatorSignals(_ChartData data) {
  final pattern = data.primaryPattern;
  final patternDirection =
      _patternDirection(pattern, data.structure, data.opportunity);
  final rsi = _lastNumeric(data.chart?.panels['rsi']);
  final volumeState = _volumeState(data.chart?.candles);
  return [
    _IndicatorState(
      icon: Icons.trending_up_rounded,
      label: pattern == null ? 'Structure' : 'Pattern',
      state: _directionShortLabel(patternDirection).toUpperCase(),
      color: _directionTone(patternDirection),
      filled: _directionTone(patternDirection) == AppColors.measured,
    ),
    _IndicatorState(
      icon: Icons.show_chart_rounded,
      label: 'RSI',
      state: _rsiLabel(rsi),
      color: _rsiColor(rsi),
    ),
    _IndicatorState(
      icon: Icons.bar_chart_rounded,
      label: 'Volume',
      state: volumeState.$1,
      color: volumeState.$2,
      filled: volumeState.$2 == AppColors.measured,
    ),
    _IndicatorState(
      icon: Icons.monetization_on_rounded,
      label: 'Funding',
      state: _fundingLabel(data.today?.fundingBand),
      color: const Color(0xFFB9C5DD),
    ),
  ];
}

List<_ConfluenceItem> _confluenceItems(_ChartData data) {
  final items = <_ConfluenceItem>[];
  items.add(_ConfluenceItem(
    data.primaryPattern == null ? 'Structure' : 'Pattern',
    _recognitionScore(data.primaryPattern, data.structure),
    const Color(0xFF42E892),
  ));

  final directionConfidence =
      double.tryParse(data.today?.summary.directionConfidence ?? '');
  if (directionConfidence != null) {
    items.add(_ConfluenceItem(
      'Direction',
      directionConfidence.clamp(0, 100).round(),
      const Color(0xFF8BCDFF),
    ));
  }

  if (data.opportunity?.score != null) {
    final score = (50 + data.opportunity!.score!).clamp(0, 100).round();
    items.add(_ConfluenceItem(
      'Entrée',
      score,
      data.opportunity!.score! >= 0 ? AppColors.measured : AppColors.warn,
    ));
  }

  if (data.today != null) {
    items.add(_ConfluenceItem(
      'Dérivés',
      _derivativesScore(data.today!),
      const Color(0xFFFFD84F),
    ));
    items.add(_ConfluenceItem(
      'Volatilité',
      _volatilityScore(data.today!.volatilityRegime),
      const Color(0xFFBFD0FF),
    ));
  }
  return items;
}

String _structureName(StructureRead structure) {
  final range = structure.location.range;
  if (range != null && range.valid) {
    return switch (range.rangeType) {
      'BROAD_RANGE' => 'Range large',
      'TIGHT_RANGE' => 'Range serré',
      _ => readableLabel(range.rangeType).toLowerCase(),
    };
  }
  return _locationLabel(structure.location.state);
}

String _patternName(String name) => switch (name) {
      'double_top' => 'Double sommet',
      'double_bottom' => 'Double creux',
      'triple_top' => 'Triple sommet',
      'triple_bottom' => 'Triple creux',
      'head_and_shoulders' => 'Tête et épaules',
      'inverse_head_and_shoulders' => 'Tête et épaules inversée',
      'ascending_triangle' => 'Triangle ascendant',
      'descending_triangle' => 'Triangle descendant',
      _ => readableLabel(name),
    };

String _locationLabel(String value) => switch (value) {
      'NEAR_RANGE_TOP' => 'Proche du haut du range',
      'NEAR_RANGE_BOTTOM' => 'Proche du bas du range',
      'MID_RANGE' => 'Milieu du range',
      'ABOVE_RANGE' => 'Au-dessus du range',
      'BELOW_RANGE' => 'Sous le range',
      'NO_VALID_RANGE' => 'Aucun range valide',
      _ => readableLabel(value).toLowerCase(),
    };

String _patternDirection(
  DetectedPattern? pattern,
  StructureRead structure,
  EntryOpportunity? opportunity,
) {
  if (pattern != null && pattern.directionIfTextbook.isNotEmpty) {
    return pattern.directionIfTextbook;
  }
  final state = opportunity?.state.toUpperCase() ?? '';
  if (state.contains('LONG') || state.contains('BULL')) return 'BULLISH';
  if (state.contains('SHORT') || state.contains('BEAR')) return 'BEARISH';
  final location = structure.location.state;
  if (location == 'NEAR_RANGE_TOP') return 'NEUTRAL';
  if (location == 'NEAR_RANGE_BOTTOM') return 'NEUTRAL';
  return structure.marketStructure.state;
}

Color _directionTone(String value) {
  final upper = value.toUpperCase();
  if (upper.contains('BULL') || upper.contains('UP')) return AppColors.measured;
  if (upper.contains('BEAR') || upper.contains('DOWN')) return AppColors.bad;
  return mobileBlue;
}

IconData _directionIcon(String value) {
  final upper = value.toUpperCase();
  if (upper.contains('BEAR') || upper.contains('DOWN')) {
    return Icons.trending_down_rounded;
  }
  if (upper.contains('BULL') || upper.contains('UP')) {
    return Icons.trending_up_rounded;
  }
  return Icons.horizontal_rule_rounded;
}

String _directionShortLabel(String value) {
  final upper = value.toUpperCase();
  if (upper.contains('STRONGLY_BULLISH')) return 'Fort haussier';
  if (upper.contains('BULL') || upper.contains('UP')) return 'Haussier';
  if (upper.contains('STRONGLY_BEARISH')) return 'Fort baissier';
  if (upper.contains('BEAR') || upper.contains('DOWN')) return 'Baissier';
  if (upper.contains('TRANSITION')) return 'Transition';
  if (upper.contains('RANGE')) return 'Range';
  return 'Neutre';
}

int _recognitionScore(DetectedPattern? pattern, StructureRead structure) {
  final raw = pattern?.recognitionConfidence ??
      structure.location.range?.confidence ??
      structure.location.range?.topZone?.quality.score ??
      0;
  final score = raw <= 1 ? raw * 100 : raw;
  return score.clamp(0, 100).round();
}

String _breakoutLabel(DetectedPattern? pattern, EntryOpportunity? opportunity) {
  final state = (pattern?.state ?? opportunity?.state ?? '').toUpperCase();
  if (state.contains('CONFIRM')) return 'confirmé';
  if (state.contains('INVALID')) return 'invalidé';
  if (state.contains('NEUTRAL')) return 'neutre';
  if (state.contains('PENDING')) return 'en attente';
  return 'en attente';
}

double? _extractPrice(String? value) {
  if (value == null) return null;
  final compact = value.replaceAll(RegExp(r'(?<=\d)\s+(?=\d)'), '');
  final candidates = RegExp(r'([0-9]+(?:[.,][0-9]+)?)')
      .allMatches(compact)
      .map((match) => double.tryParse(match.group(1)!.replaceAll(',', '.')))
      .whereType<double>()
      .where((number) => number > 10)
      .toList();
  if (candidates.isEmpty) return null;
  candidates.sort();
  return candidates.last;
}

double? _levelValue(Map<String, double>? levels, List<String> keys) {
  if (levels == null) return null;
  for (final key in keys) {
    final exact = levels[key];
    if (exact != null && exact > 0) return exact;
    for (final entry in levels.entries) {
      if (entry.key.toLowerCase().contains(key) && entry.value > 0) {
        return entry.value;
      }
    }
  }
  return null;
}

double? _rangeInvalidation(StructuralLocation location) {
  final range = location.range;
  if (range == null || !range.valid) return null;
  if (location.state == 'NEAR_RANGE_BOTTOM' ||
      location.state == 'BELOW_RANGE') {
    return range.bottomZone?.low;
  }
  return range.topZone?.high;
}

String _priceOrUnavailable(num? value, {int digits = 2}) {
  if (value == null || value.isNaN) return 'INDISPONIBLE';
  return '${_priceFr(value, digits: digits)} USD';
}

String _patternNarrative(
  String timeframe,
  StructureRead structure,
  DetectedPattern? pattern,
  EntryOpportunity? opportunity,
) {
  if (opportunity?.statement.isNotEmpty == true) {
    return _translateOpportunityStatement(opportunity!.statement);
  }
  if (pattern?.notes.isNotEmpty == true) {
    return _translateSentence(pattern!.notes);
  }
  final location = _locationLabel(structure.location.state).toLowerCase();
  return 'La lecture en ${_timeframeLabel(timeframe)} signale $location. '
      'Cette configuration décrit le contexte visuel, mais elle reste séparée '
      'du verdict d’edge mesurable.';
}

double? _lastNumeric(List<double?>? values) {
  if (values == null) return null;
  for (var i = values.length - 1; i >= 0; i -= 1) {
    final value = values[i];
    if (value != null && !value.isNaN) return value;
  }
  return null;
}

String _rsiLabel(double? value) {
  if (value == null) return 'N/A';
  if (value >= 70) return 'ÉLEVÉ';
  if (value <= 30) return 'FAIBLE';
  return 'NEUTRE';
}

Color _rsiColor(double? value) {
  if (value == null) return const Color(0xFF8EA2BE);
  if (value >= 70 || value <= 30) return AppColors.warn;
  return const Color(0xFFB9C5DD);
}

(String, Color) _volumeState(List<CandlePoint>? candles) {
  if (candles == null || candles.length < 6) {
    return ('N/A', const Color(0xFF8EA2BE));
  }
  final tail =
      candles.length > 24 ? candles.sublist(candles.length - 24) : candles;
  final average =
      tail.map((candle) => candle.volume).reduce((a, b) => a + b) / tail.length;
  final current = tail.last.volume;
  if (average <= 0) return ('N/A', const Color(0xFF8EA2BE));
  if (current >= average * 1.18) return ('HAUSSIER', AppColors.measured);
  if (current <= average * 0.72) return ('FAIBLE', AppColors.warn);
  return ('NORMAL', const Color(0xFFB9C5DD));
}

String _fundingLabel(String? raw) => switch ((raw ?? '').toUpperCase()) {
      'NEUTRAL' => 'NEUTRE',
      'LOW' => 'FAIBLE',
      'HIGH' => 'ÉLEVÉ',
      'NEGATIVE' => 'NÉGATIF',
      'POSITIVE' => 'POSITIF',
      '' => 'N/A',
      _ => readableLabel(raw!),
    };

int _derivativesScore(TodayRead read) {
  final funding = read.fundingPercentile;
  final crowding = read.crowdingScore;
  final fundingScore =
      funding == null ? 50 : (100 - (funding - 50).abs() * 2).clamp(0, 100);
  final crowdingScore = crowding?.clamp(0, 100) ?? 50;
  return ((fundingScore + crowdingScore) / 2).round();
}

int _volatilityScore(String regime) => switch (regime.toUpperCase()) {
      'VERY_LOW' => 54,
      'LOW' => 68,
      'NORMAL' => 62,
      'MODERATE' => 50,
      'HIGH' => 38,
      'EXTREME' => 24,
      _ => 45,
    };

String _edgeLabel(EdgeState state) => switch (state) {
      EdgeState.positiveEdge => 'EDGE MESURABLE',
      EdgeState.negativeEdge => 'EDGE DÉFAVORABLE',
      EdgeState.noMeasurableEdge => 'AUCUN EDGE MESURABLE',
      EdgeState.unstable => 'INSTABLE',
      EdgeState.insufficientData => 'DONNÉES INSUFFISANTES',
      EdgeState.notYetTested => 'PAS ENCORE TESTÉ',
      EdgeState.unknown => 'INCONNU',
    };

Color _edgeTone(EdgeState state) => switch (state) {
      EdgeState.positiveEdge => AppColors.measured,
      EdgeState.negativeEdge => AppColors.bad,
      EdgeState.noMeasurableEdge || EdgeState.unstable => AppColors.warn,
      _ => mobileMuted,
    };

int _historyCount(_ChartData data) {
  final events = data.structure.marketStructure.events.length;
  final candles = data.chart?.bars ?? 0;
  final explanations = data.structure.location.explanation.length;
  return math.max(events + explanations, candles);
}

String _translateOpportunityStatement(String value) {
  final state =
      RegExp(r'configuration is ([A-Z_]+) \(([-0-9.]+)\)').firstMatch(value);
  final edge = RegExp(r'Measured edge: ([A-Z_]+)').firstMatch(value);
  if (state != null) {
    return 'La configuration est ${_entryStateLabel(state.group(1)!)} '
        '(${state.group(2)}). Edge mesuré : '
        '${_edgeLabel(EdgeState.parse(edge?.group(1)))}. '
        'La lecture décrit le contexte, pas une recommandation d’agir.';
  }
  return _translateSentence(value);
}

String _entryStateLabel(String value) => switch (value.toUpperCase()) {
      'LONG_OPPORTUNITY' => 'opportunité long',
      'SHORT_OPPORTUNITY' => 'opportunité short',
      'NEUTRAL' => 'neutre',
      'WAIT' => 'attente',
      'INSUFFICIENT_DATA' => 'insuffisante',
      _ => readableLabel(value).toLowerCase(),
    };

String _translateSentence(String value) {
  return value
      .replaceAll('resistance zone tested', 'zone de résistance testée')
      .replaceAll('support zone tested', 'zone de support testée')
      .replaceAll('touches agree within', 'touches regroupés dans')
      .replaceAll(
          'median reaction from the zone', 'réaction médiane depuis la zone')
      .replaceAll('close(s) through the zone', 'clôture(s) à travers la zone')
      .replaceAll('last tested', 'dernier test il y a')
      .replaceAll('range active for', 'range actif depuis')
      .replaceAll('deviation(s) recorded', 'déviation(s) enregistrée(s)')
      .replaceAll('of which reversed back through the range',
          'réintégrée(s) dans le range')
      .replaceAll('bars ago', 'barres')
      .replaceAll('bars', 'barres')
      .replaceAll(
          'price is near range top', 'le prix est proche du haut du range')
      .replaceAll(
          'price is near range bottom', 'le prix est proche du bas du range')
      .replaceAll('funding is mid-range', 'le funding est dans sa zone médiane')
      .replaceAll('volatility LOW', 'la volatilité est faible')
      .replaceAll('moves are small', 'les mouvements sont limités')
      .replaceAll('which cuts both ways', 'dans les deux sens');
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
