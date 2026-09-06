/// Intelligence graphique: lecture structurelle et opportunite d'entree.
library;

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
              padding: const EdgeInsets.fromLTRB(28, 28, 28, 24),
              children: [
                MobileHeader(
                  title: 'Intelligence graphique',
                  onInfo: () => _showInfo(context),
                ),
                const SizedBox(height: 28),
                _AssetSelector(
                  assets: _assets,
                  selected: _asset,
                  onSelected: _selectAsset,
                ),
                const SizedBox(height: 24),
                _TimeframeSelector(
                  timeframes: _timeframes,
                  selected: _timeframe,
                  onSelected: _selectTimeframe,
                ),
                const SizedBox(height: 26),
                if (snapshot.connectionState == ConnectionState.waiting)
                  const SizedBox(height: 360, child: LoadingView(what: 'structure graphique'))
                else if (snapshot.hasError)
                  SizedBox(
                    height: 360,
                    child: ErrorView(error: snapshot.error!, onRetry: _reload),
                  )
                else ...[
                  _OpportunityPanel(
                    opportunity: snapshot.data!.$2,
                    asset: _asset,
                    timeframe: _timeframe,
                  ),
                  const SizedBox(height: 24),
                  _RangePanel(location: snapshot.data!.$1.location),
                  const SizedBox(height: 24),
                  _StructurePanel(structure: snapshot.data!.$1.marketStructure),
                  const SizedBox(height: 24),
                  _PatternsPanel(patterns: snapshot.data!.$1.patterns),
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
          'Cet onglet affiche la structure detectee, le contexte d’entree et '
          'l’edge mesure separement. Une configuration lisible ne devient pas '
          'automatiquement une recommandation.',
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
        final compact = constraints.maxWidth < 650;
        return Wrap(
          spacing: 18,
          runSpacing: 14,
          children: [
            for (final asset in assets)
              _AssetChoice(
                asset: asset,
                selected: selected == asset,
                width: compact ? (constraints.maxWidth - 18) / 2 : 205,
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
      width: width.clamp(142, 215),
      height: 88,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(15),
          onTap: onTap,
          child: Ink(
            decoration: BoxDecoration(
              color: selected
                  ? const Color(0xFF173B66).withValues(alpha: 0.88)
                  : mobilePanel.withValues(alpha: 0.70),
              borderRadius: BorderRadius.circular(15),
              border: Border.all(
                color: selected ? mobileBlue : const Color(0xFF334660),
                width: selected ? 1.55 : 1.25,
              ),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                CryptoLogo(asset: asset, size: 54),
                const SizedBox(width: 18),
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
    return Wrap(
      spacing: 18,
      runSpacing: 14,
      children: [
        for (final timeframe in timeframes)
          SizedBox(
            width: 150,
            height: 74,
            child: Material(
              color: Colors.transparent,
              child: InkWell(
                borderRadius: BorderRadius.circular(13),
                onTap: () => onSelected(timeframe),
                child: Ink(
                  decoration: BoxDecoration(
                    color: selected == timeframe
                        ? const Color(0xFF194B80).withValues(alpha: 0.85)
                        : mobilePanel.withValues(alpha: 0.70),
                    borderRadius: BorderRadius.circular(13),
                    border: Border.all(
                      color: selected == timeframe ? mobileBlue : const Color(0xFF334660),
                      width: selected == timeframe ? 1.55 : 1.25,
                    ),
                  ),
                  child: Center(
                    child: Text(
                      _timeframeLabel(timeframe),
                      style: TextStyle(
                        color: selected == timeframe ? const Color(0xFF9CCBFF) : AppColors.text,
                        fontSize: 26,
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
  }
}

class _OpportunityPanel extends StatelessWidget {
  final EntryOpportunity? opportunity;
  final String asset;
  final String timeframe;

  const _OpportunityPanel({
    required this.opportunity,
    required this.asset,
    required this.timeframe,
  });

  @override
  Widget build(BuildContext context) {
    final item = opportunity;
    if (item == null) {
      return const GlassPanel(
        child: Text(
          'Opportunite d’entree indisponible pour cette selection.',
          style: TextStyle(color: mobileMuted, fontSize: 18),
        ),
      );
    }

    return GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Expanded(
                child: Text(
                  'OPPORTUNITÉ D’ENTRÉE',
                  style: TextStyle(
                    color: Color(0xFFBFC9E4),
                    fontSize: 25,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0,
                  ),
                ),
              ),
              const SizedBox(width: 10),
              MobilePill(label: _edgeLabel(item.measuredEdge), color: AppColors.warn),
            ],
          ),
          const SizedBox(height: 22),
          Row(
            children: [
              MobilePill(label: _opportunityState(item.state), color: mobileBlue, filled: true),
              const SizedBox(width: 16),
              Text(
                _scoreText(item.score),
                style: const TextStyle(color: AppColors.text, fontSize: 23),
              ),
            ],
          ),
          if (item.invalidation.isNotEmpty) ...[
            const SizedBox(height: 24),
            Container(
              padding: const EdgeInsets.only(left: 20),
              decoration: const BoxDecoration(
                border: Border(left: BorderSide(color: AppColors.warn, width: 6)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Ce qui invaliderait ce scénario',
                    style: TextStyle(
                      color: Color(0xFFFFC63B),
                      fontSize: 23,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    _translateEntryText(item.invalidation, timeframe),
                    style: const TextStyle(color: AppColors.text, fontSize: 22, height: 1.28),
                  ),
                ],
              ),
            ),
          ],
          if (item.whyNow.isNotEmpty) ...[
            const SizedBox(height: 28),
            const Text(
              'Pourquoi maintenant',
              style: TextStyle(
                color: Color(0xFFBFC9E4),
                fontSize: 23,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 12),
            for (final reason in item.whyNow)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(
                  '• ${_translateEntryText(reason, timeframe)}',
                  style: const TextStyle(color: AppColors.text, fontSize: 20, height: 1.32),
                ),
              ),
          ],
          const SizedBox(height: 24),
          Text(
            _entryDisclaimer(item.disclaimer),
            style: const TextStyle(
              color: Color(0xFF99A8C0),
              fontSize: 18,
              fontStyle: FontStyle.italic,
              height: 1.35,
            ),
          ),
        ],
      ),
    );
  }
}

class _RangePanel extends StatelessWidget {
  final StructuralLocation location;

  const _RangePanel({required this.location});

  @override
  Widget build(BuildContext context) {
    final range = location.range;
    return GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Expanded(
                child: Text(
                  'ZONE & POSITION',
                  style: TextStyle(
                    color: Color(0xFFBFC9E4),
                    fontSize: 25,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
              const SizedBox(width: 10),
              MobilePill(label: _locationLabel(location.state), color: mobileBlue),
            ],
          ),
          const SizedBox(height: 22),
          if (range == null || !range.valid)
            Text(
              location.rangeSummary.isNotEmpty
                  ? location.rangeSummary
                  : 'Aucun range valide sur cette unite de temps.',
              style: const TextStyle(color: mobileMuted, fontSize: 20, height: 1.35),
            )
          else ...[
            Text(
              _rangeSummary(range),
              style: const TextStyle(color: AppColors.text, fontSize: 22, height: 1.36),
            ),
            const SizedBox(height: 18),
            _RangeMetricRow(
              left: 'Position',
              right: fmtFr(location.relativePosition, digits: 3),
            ),
            _RangeMetricRow(
              left: 'Distance au haut',
              right: '${fmtFr(location.distanceToTopAtr, digits: 2)} ATR',
            ),
            _RangeMetricRow(
              left: 'Distance au bas',
              right: '${fmtFr(location.distanceToBottomAtr, digits: 2)} ATR',
            ),
            _RangeMetricRow(
              left: 'Confiance',
              right: '${fmtFr(range.confidence, digits: 0)}/100',
            ),
          ],
        ],
      ),
    );
  }
}

class _RangeMetricRow extends StatelessWidget {
  final String left;
  final String right;

  const _RangeMetricRow({required this.left, required this.right});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          Expanded(
            child: Text(left, style: const TextStyle(color: mobileMuted, fontSize: 17)),
          ),
          Text(right, style: const TextStyle(color: AppColors.text, fontSize: 17)),
        ],
      ),
    );
  }
}

class _StructurePanel extends StatelessWidget {
  final MarketStructure structure;

  const _StructurePanel({required this.structure});

  @override
  Widget build(BuildContext context) {
    return GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: Text(
                  'STRUCTURE DES SWINGS',
                  style: TextStyle(color: Color(0xFFBFC9E4), fontSize: 24, fontWeight: FontWeight.w800),
                ),
              ),
              MobilePill(label: _structureLabel(structure.state), color: mobileBlue),
            ],
          ),
          const SizedBox(height: 18),
          Text(
            _translateStructureText(structure.interpretation),
            style: const TextStyle(color: AppColors.text, fontSize: 18, height: 1.35),
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final label in structure.labels)
                MobilePill(label: label, color: const Color(0xFF7DAFFF), dense: true),
            ],
          ),
        ],
      ),
    );
  }
}

class _PatternsPanel extends StatelessWidget {
  final List<DetectedPattern> patterns;

  const _PatternsPanel({required this.patterns});

  @override
  Widget build(BuildContext context) {
    return GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'FIGURES DÉTECTÉES (${patterns.length})',
            style: const TextStyle(color: Color(0xFFBFC9E4), fontSize: 24, fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 14),
          if (patterns.isEmpty)
            const Text(
              'Aucune figure detectee sur cette selection.',
              style: TextStyle(color: mobileMuted, fontSize: 18),
            )
          else
            for (final pattern in patterns)
              _PatternRow(pattern: pattern),
        ],
      ),
    );
  }
}

class _PatternRow extends StatelessWidget {
  final DetectedPattern pattern;

  const _PatternRow({required this.pattern});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 12),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: Color(0xFF20344C))),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _patternLabel(pattern.name),
                  style: const TextStyle(color: AppColors.text, fontSize: 19, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 4),
                Text(
                  '${_patternState(pattern.state)} · reconnaissance ${fmtFr(pattern.recognitionConfidence, digits: 0)}/100',
                  style: const TextStyle(color: mobileMuted, fontSize: 15),
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          MobilePill(label: _edgeLabel(pattern.edgeState), color: _edgeColor(pattern.edgeState), dense: true),
        ],
      ),
    );
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

String _opportunityState(String value) => switch (value.toUpperCase()) {
      'NEUTRAL' => 'NEUTRE',
      'FAVOURABLE' || 'FAVORABLE' => 'FAVORABLE',
      'UNFAVOURABLE' || 'UNFAVORABLE' => 'DÉFAVORABLE',
      'INSUFFICIENT_DATA' => 'DONNÉES INSUFFISANTES',
      _ => readableLabel(value),
    };

String _scoreText(num? score) {
  if (score == null) return '—';
  return score.toStringAsFixed(0).replaceAll('+', '');
}

String _edgeLabel(EdgeState state) => switch (state) {
      EdgeState.positiveEdge => 'EDGE MESURABLE',
      EdgeState.negativeEdge => 'EDGE DÉFAVORABLE',
      EdgeState.noMeasurableEdge => 'AUCUN EDGE MESURABLE',
      EdgeState.unstable => 'INSTABLE',
      EdgeState.insufficientData => 'DONNÉES INSUFFISANTES',
      EdgeState.notYetTested => 'PAS ENCORE TESTÉ',
      EdgeState.unknown => 'INCONNU',
    };

Color _edgeColor(EdgeState state) => switch (state) {
      EdgeState.positiveEdge => AppColors.measured,
      EdgeState.negativeEdge => AppColors.bad,
      EdgeState.noMeasurableEdge || EdgeState.unstable => AppColors.warn,
      _ => mobileMuted,
    };

String _locationLabel(String value) => switch (value.toUpperCase()) {
      'NEAR_RANGE_TOP' => 'PROCHE DU HAUT DU RANGE',
      'NEAR_RANGE_BOTTOM' => 'PROCHE DU BAS DU RANGE',
      'MID_RANGE' => 'MILIEU DU RANGE',
      'ABOVE_RANGE' => 'AU-DESSUS DU RANGE',
      'BELOW_RANGE' => 'SOUS LE RANGE',
      'NO_VALID_RANGE' => 'AUCUN RANGE VALIDE',
      _ => readableLabel(value),
    };

String _structureLabel(String value) => switch (value.toUpperCase()) {
      'TRANSITION' => 'TRANSITION',
      'BULLISH' => 'HAUSSIER',
      'BEARISH' => 'BAISSIER',
      'RANGE' => 'RANGE',
      'UNCLEAR' => 'INCERTAIN',
      _ => readableLabel(value),
    };

String _patternState(String value) => switch (value.toUpperCase()) {
      'CONFIRMED' => 'confirmée',
      'CANDIDATE' => 'candidate',
      _ => readableLabel(value).toLowerCase(),
    };

String _patternLabel(String value) => switch (value) {
      'double_top' => 'Double sommet',
      'double_bottom' => 'Double creux',
      'triple_top' => 'Triple sommet',
      'triple_bottom' => 'Triple creux',
      'head_and_shoulders' => 'Tête et épaules',
      'inverse_head_and_shoulders' => 'Tête et épaules inversée',
      'ascending_triangle' => 'Triangle ascendant',
      'descending_triangle' => 'Triangle descendant',
      'rising_wedge' => 'Biseau ascendant',
      'falling_wedge' => 'Biseau descendant',
      _ => readableLabel(value),
    };

String _rangeSummary(DetectedRange range) {
  final bottom = range.bottomZone;
  final top = range.topZone;
  if (bottom == null || top == null) return readableLabel(range.rangeType);
  return '${range.rangeType} entre ${_priceFr(bottom.low)}–${_priceFr(bottom.high)} et '
      '${_priceFr(top.low)}–${_priceFr(top.high)}, largeur de '
      '${fmtFr(range.widthAtr, digits: 1)} ATR, maintenu pendant '
      '${range.durationBars} bougies avec ${range.bottomTouches} touches basses '
      'et ${range.topTouches} touches hautes.';
}

String _priceFr(num? value) {
  if (value == null || value.isNaN) return '—';
  final parts = value.toStringAsFixed(2).replaceAll('.', ',').split(',');
  final whole = parts.first;
  final buffer = StringBuffer();
  for (var i = 0; i < whole.length; i += 1) {
    final remaining = whole.length - i;
    buffer.write(whole[i]);
    if (remaining > 1 && remaining % 3 == 1) buffer.write(' ');
  }
  return '${buffer.toString()},${parts.last}';
}

String _translateEntryText(String raw, String timeframe) {
  var text = raw;
  text = text.replaceAll('$timeframe close above', 'clôture $timeframe au-dessus de');
  text = text.replaceAll('A clôture', 'Une clôture');
  text = text.replaceAll('would break the range top zone and invalidate the current range reading', 'casserait la zone haute du range et invaliderait la lecture actuelle du range');
  text = text.replaceAll('$timeframe price is near range top, zone quality', 'Le prix en $timeframe est proche du haut du range, qualité de zone');
  text = text.replaceAll('1d structure is bullish', 'La structure 1 j est haussière');
  text = text.replaceAll('funding is mid-range at the', 'le funding est au milieu de sa fourchette, au');
  text = text.replaceAll('volatility LOW at the', 'la volatilité est FAIBLE, au');
  text = text.replaceAll('th percentile - moves are small, which cuts both ways', 'e percentile : les mouvements sont limités, dans les deux sens');
  text = text.replaceAll('th percentile', 'e percentile');
  return text.replaceAll('.', ',');
}

String _entryDisclaimer(String raw) {
  if (raw.isEmpty) {
    return 'L’opportunité d’entrée décrit la configuration actuelle. Elle doit être lue avec l’edge mesurable affiché séparément.';
  }
  return 'L’opportunité d’entrée décrit comment la configuration actuelle se compare aux conditions normales. '
      'Ce n’est ni l’affirmation que le prix est intéressant, ni une recommandation d’agir. '
      'À lire avec l’edge mesurable, affiché séparément, qui est le plus souvent : AUCUN EDGE MESURABLE.';
}

String _translateStructureText(String raw) {
  if (raw.isEmpty) return 'Structure indisponible.';
  return raw
      .replaceAll('TRANSITION from the confirmed swing sequence', 'Transition depuis la sequence de swings confirmes')
      .replaceAll('across', 'sur')
      .replaceAll('confirmed pivots', 'pivots confirmes')
      .replaceAll('Structural events', 'Evenements structurels');
}
