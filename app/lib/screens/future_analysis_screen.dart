/// Future-first analysis for BTC, ETH and SOL.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/future_models.dart';
import '../live_prices/live_price_service.dart';
import '../theme/app_theme.dart';
import '../widgets/live_price_builder.dart';
import '../widgets/mobile_kit.dart';

class FutureAnalysisScreen extends StatefulWidget {
  final ApiClient client;
  final LivePriceSource? livePrices;
  final String initialAsset;

  const FutureAnalysisScreen({
    super.key,
    required this.client,
    required this.initialAsset,
    this.livePrices,
  });

  @override
  State<FutureAnalysisScreen> createState() => _FutureAnalysisScreenState();
}

class _FutureAnalysisScreenState extends State<FutureAnalysisScreen> {
  static const _assets = ['BTC', 'ETH', 'SOL'];
  static const _horizons = ['24h', '7d', '30d'];
  late String _asset;
  var _horizon = '7d';
  late Future<_FutureBundle> _future;

  @override
  void initState() {
    super.initState();
    _asset =
        _assets.contains(widget.initialAsset) ? widget.initialAsset : 'BTC';
    _future = _load();
  }

  @override
  void didUpdateWidget(covariant FutureAnalysisScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.initialAsset != widget.initialAsset &&
        _assets.contains(widget.initialAsset)) {
      _asset = widget.initialAsset;
      _future = _load();
    }
  }

  Future<_FutureBundle> _load() async {
    final responses = await Future.wait([
      widget.client.futureDecision(_asset, horizon: _horizon),
      widget.client.futureTimeline(_asset),
    ]);
    return _FutureBundle(
      decision: responses[0] as FutureDecisionRead,
      timeline: responses[1] as FutureTimelineRead,
    );
  }

  void _selectAsset(String value) {
    if (value == _asset) return;
    setState(() {
      _asset = value;
      _future = _load();
    });
  }

  void _selectHorizon(String value) {
    if (value == _horizon) return;
    setState(() {
      _horizon = value;
      _future = _load();
    });
  }

  void _reload() => setState(() => _future = _load());

  @override
  Widget build(BuildContext context) {
    return MobileGradientFrame(
      child: RefreshIndicator(
        onRefresh: () async => _reload(),
        child: FutureBuilder<_FutureBundle>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snapshot.hasError) {
              return ListView(
                padding: const EdgeInsets.all(30),
                children: [
                  Text('Analyse indisponible : ${snapshot.error}'),
                  const SizedBox(height: 12),
                  FilledButton(
                      onPressed: _reload, child: const Text('Réessayer')),
                ],
              );
            }
            final bundle = snapshot.data!;
            final decision = bundle.decision;
            return MobileScrollView(
              padding: const EdgeInsets.fromLTRB(24, 26, 24, 170),
              children: [
                MobileHeader(
                  title: 'Analyse',
                  subtitle: 'Catalyseurs futurs et décision sourcée',
                ),
                const SizedBox(height: 18),
                _Selector(
                  values: _assets,
                  selected: _asset,
                  onSelected: _selectAsset,
                ),
                const SizedBox(height: 14),
                _LiveHeader(
                  asset: _asset,
                  source: widget.livePrices,
                  asOf: decision.asOf,
                ),
                const SizedBox(height: 14),
                _DecisionCard(
                  decision: decision,
                  horizon: _horizon,
                  onWhy: () => _showWhy(context, decision),
                ),
                const SizedBox(height: 12),
                _Selector(
                  values: _horizons,
                  selected: _horizon,
                  onSelected: _selectHorizon,
                ),
                const SizedBox(height: 18),
                _NextEvent(event: decision.nextEvent),
                const SizedBox(height: 18),
                _Families(decision: decision),
                const SizedBox(height: 18),
                _Timeline(events: bundle.timeline.events),
                const SizedBox(height: 18),
                _Scenarios(scenarios: decision.scenarios),
              ],
            );
          },
        ),
      ),
    );
  }

  void _showWhy(BuildContext context, FutureDecisionRead decision) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: mobilePanel,
      builder: (context) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: .72,
        minChildSize: .4,
        maxChildSize: .94,
        builder: (context, controller) => ListView(
          controller: controller,
          padding: const EdgeInsets.all(24),
          children: [
            Text(
              'Pourquoi ${_decisionLabel(decision.decision).toLowerCase()} ?',
              style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 18),
            for (final reason in decision.reasons) ...[
              Text(reason.title,
                  style: const TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 4),
              Text(reason.explanation,
                  style: const TextStyle(color: mobileMuted, height: 1.35)),
              const SizedBox(height: 4),
              Text(
                [
                  reason.source,
                  reason.dateTime == null ? null : _date(reason.dateTime)
                ].whereType<String>().join(' · '),
                style:
                    const TextStyle(color: AppColors.textMuted, fontSize: 12),
              ),
              const Divider(height: 24),
            ],
            const Text('CE QUI POURRAIT CHANGER LA DÉCISION',
                style: TextStyle(fontWeight: FontWeight.w800)),
            const SizedBox(height: 8),
            for (final change in decision.changes)
              Padding(
                padding: const EdgeInsets.only(bottom: 7),
                child: Text('• $change',
                    style: const TextStyle(color: mobileMuted)),
              ),
          ],
        ),
      ),
    );
  }
}

class _Selector extends StatelessWidget {
  final List<String> values;
  final String selected;
  final ValueChanged<String> onSelected;

  const _Selector(
      {required this.values, required this.selected, required this.onSelected});

  @override
  Widget build(BuildContext context) => Wrap(
        spacing: 8,
        children: [
          for (final value in values)
            ChoiceChip(
              selected: value == selected,
              label: Text(value),
              onSelected: (_) => onSelected(value),
            ),
        ],
      );
}

class _LiveHeader extends StatelessWidget {
  final String asset;
  final LivePriceSource? source;
  final DateTime? asOf;

  const _LiveHeader(
      {required this.asset, required this.source, required this.asOf});

  @override
  Widget build(BuildContext context) => LivePriceBuilder(
        source: source,
        asset: asset,
        builder: (context, tick, connection) => GlassPanel(
          child: Row(
            children: [
              CryptoLogo(asset: asset, size: 54),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(asset,
                        style: const TextStyle(
                            fontSize: 22, fontWeight: FontWeight.w800)),
                    Text(
                      tick == null
                          ? 'Prix live indisponible'
                          : '${tick.priceEur.toStringAsFixed(2)} €',
                      style: const TextStyle(
                          fontSize: 24, fontWeight: FontWeight.w700),
                    ),
                  ],
                ),
              ),
              Text(
                tick == null
                    ? _date(asOf?.toIso8601String())
                    : '${tick.change24hPct >= 0 ? '+' : ''}${tick.change24hPct.toStringAsFixed(2)} %',
                style: TextStyle(
                  color: tick == null
                      ? AppColors.textMuted
                      : tick.change24hPct >= 0
                          ? AppColors.measured
                          : AppColors.bad,
                ),
              ),
            ],
          ),
        ),
      );
}

class _DecisionCard extends StatelessWidget {
  final FutureDecisionRead decision;
  final String horizon;
  final VoidCallback onWhy;

  const _DecisionCard(
      {required this.decision, required this.horizon, required this.onWhy});

  @override
  Widget build(BuildContext context) {
    final tone = _decisionColor(decision.decision);
    return GlassPanel(
      borderColor: tone,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('EST-CE LE BON MOMENT POUR ACHETER ?',
              style: TextStyle(
                  color: mobileMuted,
                  fontSize: 12,
                  fontWeight: FontWeight.w700)),
          const SizedBox(height: 7),
          Text(_decisionLabel(decision.decision),
              style: TextStyle(
                  color: tone, fontSize: 34, fontWeight: FontWeight.w900)),
          if (decision.reasons.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(decision.reasons.first.explanation,
                style: const TextStyle(color: mobileMuted, height: 1.3)),
          ],
          const SizedBox(height: 16),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              MobilePill(
                  label: 'Risque ${decision.eventRisk}',
                  color: AppColors.warn,
                  dense: true),
              MobilePill(
                  label: 'Horizon $horizon', color: mobileBlue, dense: true),
              MobilePill(
                  label: 'Amplitude ${decision.movement}',
                  color: mobileBlue,
                  dense: true),
              MobilePill(
                  label: 'Confiance ${(decision.confidence * 100).round()} %',
                  color: mobileBlue,
                  dense: true),
            ],
          ),
          const SizedBox(height: 14),
          OutlinedButton(
              onPressed: onWhy,
              child: Text(
                  'Pourquoi ${_decisionLabel(decision.decision).toLowerCase()} ?')),
        ],
      ),
    );
  }
}

class _NextEvent extends StatelessWidget {
  final FutureEventRead? event;

  const _NextEvent({required this.event});

  @override
  Widget build(BuildContext context) => GlassPanel(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('PROCHAIN CATALYSEUR',
                style:
                    TextStyle(color: mobileMuted, fontWeight: FontWeight.w700)),
            const SizedBox(height: 9),
            if (event == null)
              const Text('Aucun événement sourcé dans cet horizon.',
                  style: TextStyle(color: AppColors.textMuted))
            else ...[
              Text(event!.title,
                  style: const TextStyle(
                      fontSize: 20, fontWeight: FontWeight.w800)),
              const SizedBox(height: 5),
              Text(
                  '${_date(event!.scheduledAt?.toIso8601String())} · ${_countdown(event!.countdownSeconds)} · ${event!.importance}',
                  style: const TextStyle(color: mobileMuted)),
              Text(event!.source,
                  style: const TextStyle(
                      color: AppColors.textMuted, fontSize: 12)),
            ],
          ],
        ),
      );
}

class _Families extends StatelessWidget {
  final FutureDecisionRead decision;

  const _Families({required this.decision});

  @override
  Widget build(BuildContext context) => GlassPanel(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('5 FAMILLES',
                    style: TextStyle(
                        color: mobileMuted, fontWeight: FontWeight.w700)),
                Text(decision.coverage,
                    style: const TextStyle(fontWeight: FontWeight.w800)),
              ],
            ),
            const SizedBox(height: 10),
            for (final family in decision.families)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 7),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                        family.available
                            ? Icons.check_circle_outline
                            : Icons.remove_circle_outline,
                        color:
                            family.available ? mobileBlue : AppColors.textMuted,
                        size: 18),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(family.label,
                              style:
                                  const TextStyle(fontWeight: FontWeight.w700)),
                          Text(
                            family.available
                                ? '${_directionLabel(family.direction)} · ${family.summary}'
                                : family.unavailableReason ?? 'Indisponible',
                            style: const TextStyle(
                                color: mobileMuted, fontSize: 12),
                          ),
                        ],
                      ),
                    ),
                    Text(family.freshness,
                        style: const TextStyle(
                            color: AppColors.textMuted, fontSize: 10)),
                  ],
                ),
              ),
          ],
        ),
      );
}

class _Timeline extends StatelessWidget {
  final List<FutureEventRead> events;

  const _Timeline({required this.events});

  @override
  Widget build(BuildContext context) => GlassPanel(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('CE QUI ARRIVE',
                style:
                    TextStyle(color: mobileMuted, fontWeight: FontWeight.w700)),
            const SizedBox(height: 10),
            if (events.isEmpty)
              const Text('Aucun événement sourcé dans les 30 prochains jours.',
                  style: TextStyle(color: AppColors.textMuted))
            else
              for (final event in events) ...[
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                        width: 78,
                        child: Text(_date(event.scheduledAt?.toIso8601String()),
                            style: const TextStyle(
                                color: mobileBlue, fontSize: 12))),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(event.title,
                              style:
                                  const TextStyle(fontWeight: FontWeight.w700)),
                          Text(
                              '${_countdown(event.countdownSeconds)} · ${event.importance} · ${event.source}',
                              style: const TextStyle(
                                  color: mobileMuted, fontSize: 11)),
                        ],
                      ),
                    ),
                  ],
                ),
                const Divider(height: 20),
              ],
          ],
        ),
      );
}

class _Scenarios extends StatelessWidget {
  final List<FutureScenarioRead> scenarios;

  const _Scenarios({required this.scenarios});

  @override
  Widget build(BuildContext context) => GlassPanel(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('SCÉNARIOS',
                style:
                    TextStyle(color: mobileMuted, fontWeight: FontWeight.w700)),
            const SizedBox(height: 10),
            for (final scenario in scenarios) ...[
              Text(_scenarioLabel(scenario.id),
                  style: const TextStyle(fontWeight: FontWeight.w800)),
              Text(
                  '${_directionLabel(scenario.direction)} · amplitude ${scenario.movement}',
                  style: const TextStyle(color: mobileMuted)),
              Text(scenario.eventChain.join(' → '),
                  style: const TextStyle(
                      color: AppColors.textMuted, fontSize: 12)),
              Text(
                scenario.probability == null
                    ? 'Probabilité non défendable · confiance ${(scenario.confidence * 100).round()} %'
                    : 'Probabilité ${(scenario.probability! * 100).round()} % · ${scenario.probabilitySource}',
                style:
                    const TextStyle(color: AppColors.textMuted, fontSize: 11),
              ),
              const Divider(height: 22),
            ],
          ],
        ),
      );
}

class _FutureBundle {
  final FutureDecisionRead decision;
  final FutureTimelineRead timeline;

  const _FutureBundle({required this.decision, required this.timeline});
}

String _decisionLabel(String value) => switch (value) {
      'BUY' => 'ACHETER',
      'WAIT' => 'ATTENDRE',
      'SELL' => 'VENDRE',
      _ => 'DONNÉES INSUFFISANTES',
    };

Color _decisionColor(String value) => switch (value) {
      'BUY' => AppColors.measured,
      'SELL' => AppColors.bad,
      'WAIT' => AppColors.warn,
      _ => AppColors.textMuted,
    };

String _directionLabel(String? value) => switch (value) {
      'STRONGLY_BULLISH' => 'Fortement haussier',
      'BULLISH' => 'Haussier',
      'BEARISH' => 'Baissier',
      'STRONGLY_BEARISH' => 'Fortement baissier',
      null => 'Indisponible',
      _ => 'Neutre',
    };

String _scenarioLabel(String value) => switch (value) {
      'base_case' => 'Scénario central',
      'bullish_case' => 'Scénario haussier',
      'bearish_case' => 'Scénario baissier',
      'tail_risk_case' => 'Risque extrême',
      _ => value,
    };

String _date(String? value) {
  final parsed = value == null ? null : DateTime.tryParse(value)?.toLocal();
  if (parsed == null) return 'Date indisponible';
  return '${parsed.day.toString().padLeft(2, '0')}/${parsed.month.toString().padLeft(2, '0')} ${parsed.hour.toString().padLeft(2, '0')}:${parsed.minute.toString().padLeft(2, '0')}';
}

String _countdown(int? seconds) {
  if (seconds == null) return 'non planifié';
  final hours = seconds < 0 ? 0 : seconds ~/ 3600;
  return hours < 48 ? 'dans $hours h' : 'dans ${hours ~/ 24} j';
}
