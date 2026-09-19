/// "Voir l'analyse complète": the gated decision, its six families and their
/// measures - with values, changes, dates, sources and freshness.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/future_models.dart';
import '../live_prices/live_price_service.dart';
import '../widgets/live_price_builder.dart';
import '../widgets/mobile_kit.dart';

const _green = Color(0xFF55DD8B);
const _red = Color(0xFFFF6676);
const _orange = Color(0xFFFF9A4D);
const _amber = Color(0xFFFFB34F);

Color familyStateColor(String state) => switch (state) {
      'VERY_POSITIVE' || 'POSITIVE' || 'SLIGHTLY_POSITIVE' => _green,
      'SLIGHTLY_NEGATIVE' => _orange,
      'NEGATIVE' || 'VERY_NEGATIVE' => _red,
      'NEUTRAL' || 'MIXED' => _amber,
      _ => mobileMuted,
    };

Color metricStateColor(String state) => switch (state) {
      'FAVORABLE' => _green,
      'UNFAVORABLE' => _red,
      'NEUTRAL' => _amber,
      _ => mobileMuted,
    };

String metricStateLabel(AnalysisMetricRead metric) {
  if (metric.status == 'STALE') return 'Périmée';
  if (metric.status == 'NOT_APPLICABLE') return 'Non applicable';
  if (metric.status != 'AVAILABLE') return 'Indisponible';
  return switch (metric.state) {
    'FAVORABLE' => 'Favorable',
    'UNFAVORABLE' => 'Défavorable',
    'NEUTRAL' => 'Neutre',
    _ => 'Contexte',
  };
}

({String emoji, String label, Color color}) actionStyle(String action) =>
    switch (action) {
      'BUY' => (emoji: '🟢', label: 'ACHETER', color: _green),
      'SELL' => (emoji: '🔴', label: 'VENDRE', color: _red),
      'INSUFFICIENT_DATA' => (
          emoji: '⚪',
          label: 'DONNÉES INSUFFISANTES',
          color: mobileMuted
        ),
      _ => (emoji: '🟠', label: 'ATTENDRE', color: _amber),
    };

String freshnessLabel(DateTime? when) {
  if (when == null) return 'inconnue';
  final age = DateTime.now().difference(when);
  if (age.inMinutes < 1) return 'à l’instant';
  if (age.inMinutes < 60) return 'il y a ${age.inMinutes} min';
  if (age.inHours < 48) return 'il y a ${age.inHours} h';
  return 'il y a ${age.inDays} j';
}

String dateLabel(DateTime? when) {
  if (when == null) return '—';
  String two(int v) => v.toString().padLeft(2, '0');
  final hasTime = when.hour != 0 || when.minute != 0;
  return '${two(when.day)}/${two(when.month)}'
      '${hasTime ? ' ${two(when.hour)}:${two(when.minute)}' : ''}';
}

String _assetName(String asset) => switch (asset) {
      'BTC' => 'Bitcoin',
      'ETH' => 'Ethereum',
      'SOL' => 'Solana',
      _ => asset,
    };

class FullAnalysisPage extends StatefulWidget {
  final ApiClient client;
  final String asset;
  final String initialHorizon;
  final LivePriceSource? livePrices;
  final double? fallbackPrice;
  final double? fallbackChange24h;

  /// Scenarios and the older per-family sheet, still reachable.
  final VoidCallback? onTechnicalDetails;

  const FullAnalysisPage({
    super.key,
    required this.client,
    required this.asset,
    required this.initialHorizon,
    this.livePrices,
    this.fallbackPrice,
    this.fallbackChange24h,
    this.onTechnicalDetails,
  });

  @override
  State<FullAnalysisPage> createState() => _FullAnalysisPageState();
}

class _FullAnalysisPageState extends State<FullAnalysisPage> {
  late String _horizon = widget.initialHorizon;
  late Future<FutureDecisionRead> _future = _load();

  Future<FutureDecisionRead> _load() =>
      widget.client.futureDecision(widget.asset, horizon: _horizon);

  void _select(String horizon) {
    if (horizon == _horizon) return;
    setState(() {
      _horizon = horizon;
      _future = _load();
    });
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: const Color(0xFF040C18),
        body: SafeArea(
          bottom: false,
          child: FutureBuilder<FutureDecisionRead>(
            future: _future,
            builder: (context, snapshot) {
              final analysis = snapshot.data?.analysis;
              // The way back stays on screen however far the page scrolls.
              return Column(
                children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(8, 4, 18, 0),
                    child: Row(
                      children: [
                        IconButton(
                          key: const ValueKey('full-analysis-back'),
                          tooltip: 'Retour',
                          onPressed: () => Navigator.of(context).maybePop(),
                          icon: const Icon(Icons.arrow_back_ios_new_rounded,
                              color: Colors.white),
                        ),
                        const Text(
                          'Analyse complète',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 18,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Expanded(
                    child: ListView(
                      key: const ValueKey('full-analysis'),
                      padding: const EdgeInsets.fromLTRB(18, 8, 18, 120),
                      children: [
                        _PriceHeader(
                          asset: widget.asset,
                          source: widget.livePrices,
                          fallbackPrice: widget.fallbackPrice,
                          fallbackChange: widget.fallbackChange24h,
                        ),
                        const SizedBox(height: 14),
                        _HorizonTabs(selected: _horizon, onSelect: _select),
                        const SizedBox(height: 14),
                        if (snapshot.connectionState != ConnectionState.done)
                          const Padding(
                            padding: EdgeInsets.all(40),
                            child: Center(child: CircularProgressIndicator()),
                          )
                        else if (analysis == null)
                          const GlassPanel(
                            child: Text(
                              'Analyse détaillée indisponible pour cet horizon.',
                              style: TextStyle(color: mobileMuted),
                            ),
                          )
                        else ...[
                          _DecisionCard(analysis: analysis),
                          const SizedBox(height: 14),
                          _ListCard(
                            key: const ValueKey('analysis-why'),
                            title: '🔎 Pourquoi ?',
                            lines: analysis.reasons,
                          ),
                          if (analysis.toBuy.isNotEmpty) ...[
                            const SizedBox(height: 14),
                            _ListCard(
                              key: const ValueKey('analysis-to-buy'),
                              title: analysis.action == 'SELL'
                                  ? '✅ Ce qui ferait repasser à ATTENDRE'
                                  : '✅ Ce qui ferait passer à ACHETER',
                              lines: analysis.toBuy,
                              bullet: '•',
                            ),
                          ],
                          if (analysis.toWorsen.isNotEmpty) ...[
                            const SizedBox(height: 14),
                            _ListCard(
                              key: const ValueKey('analysis-to-worsen'),
                              title: analysis.action == 'BUY'
                                  ? '❌ Ce qui invaliderait l’achat'
                                  : '❌ Ce qui dégraderait encore le scénario',
                              lines: analysis.toWorsen,
                              bullet: '•',
                            ),
                          ],
                          const SizedBox(height: 18),
                          const _SectionLabel('Familles d’analyse'),
                          const SizedBox(height: 8),
                          for (final family in analysis.families) ...[
                            FamilyCard(
                              family: family,
                              onTap: () => Navigator.of(context).push(
                                MaterialPageRoute<void>(
                                  builder: (_) => FamilyDetailPage(
                                    family: family,
                                    asset: widget.asset,
                                    horizon: _horizon,
                                  ),
                                ),
                              ),
                            ),
                            const SizedBox(height: 10),
                          ],
                          const SizedBox(height: 8),
                          _GatesCard(gates: analysis.gates),
                          if (widget.onTechnicalDetails != null) ...[
                            const SizedBox(height: 10),
                            TextButton(
                              key: const ValueKey('technical-details'),
                              onPressed: widget.onTechnicalDetails,
                              child:
                                  const Text('Scénarios et détails techniques'),
                            ),
                          ],
                        ],
                      ],
                    ),
                  ),
                ],
              );
            },
          ),
        ),
      );
}

class _PriceHeader extends StatelessWidget {
  final String asset;
  final LivePriceSource? source;
  final double? fallbackPrice;
  final double? fallbackChange;

  const _PriceHeader({
    required this.asset,
    required this.source,
    required this.fallbackPrice,
    required this.fallbackChange,
  });

  @override
  Widget build(BuildContext context) => LivePriceBuilder(
        source: source,
        asset: asset,
        builder: (context, tick, connection) {
          final price = tick?.priceEur ?? fallbackPrice;
          final change = tick?.change24hPct ?? fallbackChange;
          return Row(
            children: [
              CryptoLogo(asset: asset, size: 44),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  _assetName(asset),
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 22,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    price == null ? '—' : _euros(price),
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 18,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  if (change != null)
                    Text(
                      '${change >= 0 ? '+' : ''}${change.toStringAsFixed(2).replaceAll('.', ',')} % (24 h)',
                      style: TextStyle(
                        color: change >= 0 ? _green : _red,
                        fontSize: 12.5,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                ],
              ),
            ],
          );
        },
      );
}

String _euros(double value) {
  final parts = value.toStringAsFixed(2).split('.');
  final digits = parts.first;
  final buffer = StringBuffer();
  for (var i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 == 0) buffer.write(' ');
    buffer.write(digits[i]);
  }
  return '$buffer,${parts.last} €';
}

class _HorizonTabs extends StatelessWidget {
  final String selected;
  final ValueChanged<String> onSelect;

  const _HorizonTabs({required this.selected, required this.onSelect});

  @override
  Widget build(BuildContext context) => Row(
        children: [
          for (final (value, label) in const [
            ('24h', '24 H'),
            ('7d', '7 J'),
            ('30d', '30 J'),
          ]) ...[
            if (value != '24h') const SizedBox(width: 8),
            Expanded(
              child: InkWell(
                key: ValueKey('analysis-horizon-$value'),
                onTap: () => onSelect(value),
                borderRadius: BorderRadius.circular(12),
                child: Container(
                  height: 40,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: selected == value
                        ? const Color(0xFF123E6B)
                        : const Color(0xFF0A1726),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: selected == value
                          ? mobileBlue
                          : const Color(0xFF26405E),
                    ),
                  ),
                  child: Text(
                    label,
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
              ),
            ),
          ],
        ],
      );
}

class _DecisionCard extends StatelessWidget {
  final FutureAnalysisRead analysis;

  const _DecisionCard({required this.analysis});

  @override
  Widget build(BuildContext context) {
    final style = actionStyle(analysis.action);
    return GlassPanel(
      key: const ValueKey('analysis-decision'),
      borderColor: style.color.withValues(alpha: .6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${style.emoji} ${style.label}',
            style: TextStyle(
              color: style.color,
              fontSize: 28,
              fontWeight: FontWeight.w900,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            analysis.subtitle,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            analysis.headline,
            style: const TextStyle(
                color: Color(0xFFD5E1F2), fontSize: 13.5, height: 1.35),
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 18,
            runSpacing: 8,
            children: [
              _Figure(
                key: const ValueKey('analysis-confidence'),
                label: 'Confiance',
                value: '${analysis.confidence} %',
              ),
              _Figure(
                key: const ValueKey('analysis-quality'),
                label: 'Qualité des données',
                value: '${analysis.dataQuality} %',
              ),
              _Figure(
                key: const ValueKey('analysis-freshness'),
                label: 'Dernière donnée',
                value: freshnessLabel(analysis.newestData),
              ),
            ],
          ),
          const SizedBox(height: 10),
          const Text(
            'La confiance mesure la qualité et la cohérence des données. Ce n’est '
            'pas une probabilité de hausse ou de baisse.',
            key: ValueKey('confidence-disclaimer'),
            style: TextStyle(color: mobileMuted, fontSize: 11, height: 1.3),
          ),
        ],
      ),
    );
  }
}

class _Figure extends StatelessWidget {
  final String label;
  final String value;

  const _Figure({super.key, required this.label, required this.value});

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(color: mobileMuted, fontSize: 11)),
          Text(
            value,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.w800,
            ),
          ),
        ],
      );
}

class _SectionLabel extends StatelessWidget {
  final String text;

  const _SectionLabel(this.text);

  @override
  Widget build(BuildContext context) => Text(
        text.toUpperCase(),
        style: const TextStyle(
          color: Color(0xFF8FA8C4),
          fontSize: 12,
          letterSpacing: .8,
          fontWeight: FontWeight.w900,
        ),
      );
}

class _ListCard extends StatelessWidget {
  final String title;
  final List<String> lines;
  final String? bullet;

  const _ListCard(
      {super.key, required this.title, required this.lines, this.bullet});

  @override
  Widget build(BuildContext context) => GlassPanel(
        borderColor: const Color(0xFF2B669B),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 17,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 10),
            for (final line in lines) ...[
              Text(
                bullet == null ? line : '$bullet $line',
                style: const TextStyle(
                    color: Color(0xFFE6EEF9), fontSize: 13.5, height: 1.4),
              ),
              const SizedBox(height: 7),
            ],
          ],
        ),
      );
}

/// One family on the full page: state, two or three figures, one sentence.
class FamilyCard extends StatelessWidget {
  final AnalysisFamilyRead family;
  final VoidCallback onTap;

  const FamilyCard({super.key, required this.family, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final color = familyStateColor(family.state);
    final unavailable = !family.usable;
    return InkWell(
      key: ValueKey('family-${family.family}'),
      onTap: onTap,
      borderRadius: BorderRadius.circular(18),
      child: GlassPanel(
        padding: const EdgeInsets.all(16),
        borderColor: const Color(0xFF245E90),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(family.emoji, style: const TextStyle(fontSize: 20)),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    family.label,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 15.5,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                Text(
                  unavailable
                      ? (family.status == 'STALE' ? 'Périmé' : 'Indisponible')
                      : family.stateLabel,
                  style: TextStyle(color: color, fontWeight: FontWeight.w800),
                ),
                const Icon(Icons.chevron_right_rounded,
                    color: Color(0xFF55749B)),
              ],
            ),
            const SizedBox(height: 8),
            if (unavailable)
              Text(
                family.unavailableReason.isEmpty
                    ? family.headline
                    : family.unavailableReason,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                    color: mobileMuted, fontSize: 12.5, height: 1.3),
              )
            else ...[
              for (final metric in family.keyMetrics)
                Padding(
                  padding: const EdgeInsets.only(bottom: 3),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          metric.label,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              color: mobileMuted, fontSize: 12.5),
                        ),
                      ),
                      Text(
                        metric.displayValue,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      if (metric.deltaLabel.isNotEmpty) ...[
                        const SizedBox(width: 8),
                        Flexible(
                          child: Text(
                            metric.deltaLabel,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              color: metricStateColor(metric.state),
                              fontSize: 11.5,
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              const SizedBox(height: 6),
              Text(
                '« ${family.headline} »',
                style: const TextStyle(
                  color: Color(0xFFD5E1F2),
                  fontSize: 12.5,
                  fontStyle: FontStyle.italic,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _GatesCard extends StatelessWidget {
  final List<AnalysisGateRead> gates;

  const _GatesCard({required this.gates});

  @override
  Widget build(BuildContext context) => GlassPanel(
        key: const ValueKey('analysis-gates'),
        borderColor: const Color(0xFF26405E),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              '🛡️ Garde-fous avant décision',
              style: TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 10),
            for (final gate in gates)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(gate.blocks ? '⛔' : '✅',
                        style: const TextStyle(fontSize: 14)),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        '${gate.label} — ${gate.detail}',
                        style: TextStyle(
                          color: gate.blocks ? Colors.white : mobileMuted,
                          fontSize: 12.5,
                          height: 1.3,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      );
}

/// Every measure of one family: value, change, state, date, source, and why
/// it matters.
class FamilyDetailPage extends StatelessWidget {
  final AnalysisFamilyRead family;
  final String asset;
  final String horizon;

  const FamilyDetailPage({
    super.key,
    required this.family,
    required this.asset,
    required this.horizon,
  });

  @override
  Widget build(BuildContext context) {
    final color = familyStateColor(family.state);
    final regime = family.extra['regime_label']?.toString();
    final crowding = family.extra['crowding_label']?.toString();
    final structure = family.extra['structure_label']?.toString();
    return Scaffold(
      backgroundColor: const Color(0xFF040C18),
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(8, 4, 18, 0),
              child: Row(
                children: [
                  IconButton(
                    key: const ValueKey('family-detail-back'),
                    tooltip: 'Retour',
                    onPressed: () => Navigator.of(context).maybePop(),
                    icon: const Icon(Icons.arrow_back_ios_new_rounded,
                        color: Colors.white),
                  ),
                  Expanded(
                    child: Text(
                      '${family.emoji} ${family.label}',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 19,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: ListView(
                key: ValueKey('family-detail-${family.family}'),
                padding: const EdgeInsets.fromLTRB(18, 8, 18, 120),
                children: [
                  GlassPanel(
                    borderColor: color.withValues(alpha: .6),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          family.usable ? family.stateLabel : 'Indisponible',
                          style: TextStyle(
                              color: color,
                              fontSize: 22,
                              fontWeight: FontWeight.w900),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          family.usable
                              ? family.headline
                              : family.unavailableReason,
                          style: const TextStyle(
                              color: Color(0xFFD5E1F2), height: 1.35),
                        ),
                        if (family.usable) ...[
                          const SizedBox(height: 10),
                          Text(
                            'Score ${family.score!.round()} / 100 · confiance ${family.confidence} % · '
                            'qualité des données ${family.dataQuality} % · horizon ${horizon.replaceAll('d', ' j').replaceAll('h', ' h')}',
                            style: const TextStyle(
                                color: mobileMuted, fontSize: 11.5),
                          ),
                        ],
                        for (final line in [
                          if (regime != null)
                            '💵 Régime de liquidité : $regime',
                          if (crowding != null)
                            '📈 Levier face au prix : $crowding',
                          if (structure != null) '🧱 Structure : $structure',
                        ])
                          Padding(
                            padding: const EdgeInsets.only(top: 6),
                            child: Text(line,
                                style: const TextStyle(color: Colors.white)),
                          ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 14),
                  for (final metric in family.metrics) ...[
                    MetricTile(metric: metric),
                    const SizedBox(height: 10),
                  ],
                  if (family.reasons.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    _ListCard(title: '🔎 Lecture', lines: family.reasons),
                  ],
                  if (family.contradictions.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    _ListCard(
                        title: '⚖️ Contradictions',
                        lines: family.contradictions),
                  ],
                  if (family.invalidationConditions.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    _ListCard(
                      title: '❌ Ce qui changerait la lecture',
                      lines: family.invalidationConditions,
                      bullet: '•',
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class MetricTile extends StatelessWidget {
  final AnalysisMetricRead metric;

  const MetricTile({super.key, required this.metric});

  @override
  Widget build(BuildContext context) {
    final color = metric.usable ? metricStateColor(metric.state) : mobileMuted;
    return GlassPanel(
      key: ValueKey('metric-${metric.key}'),
      padding: const EdgeInsets.all(16),
      borderColor: const Color(0xFF1F3A57),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(metric.emoji, style: const TextStyle(fontSize: 18)),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  metric.label,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 14.5,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
              Text(
                metricStateLabel(metric),
                style: TextStyle(
                    color: color, fontSize: 12, fontWeight: FontWeight.w800),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            metric.displayValue,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 20,
              fontWeight: FontWeight.w900,
            ),
          ),
          if (metric.deltaLabel.isNotEmpty)
            Text(metric.deltaLabel,
                style: TextStyle(color: color, fontSize: 12.5)),
          const SizedBox(height: 6),
          Text(
            [
              if (metric.timestamp != null)
                'Mise à jour ${dateLabel(metric.timestamp)}',
              if (metric.source.isNotEmpty) metric.source,
            ].join(' · '),
            style: const TextStyle(color: mobileMuted, fontSize: 11),
          ),
          if (metric.note.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              metric.note,
              style:
                  const TextStyle(color: _amber, fontSize: 11.5, height: 1.3),
            ),
          ],
          if (metric.why.isNotEmpty) ...[
            const SizedBox(height: 8),
            const Text(
              '💡 Pourquoi ça compte',
              style: TextStyle(
                  color: Color(0xFF8FA8C4),
                  fontSize: 11.5,
                  fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 3),
            Text(
              metric.why,
              maxLines: 5,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                  color: Color(0xFFD5E1F2), fontSize: 12.5, height: 1.35),
            ),
          ],
        ],
      ),
    );
  }
}
