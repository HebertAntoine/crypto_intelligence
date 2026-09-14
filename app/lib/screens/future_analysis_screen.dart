/// Future-first analysis for BTC, ETH and SOL.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/future_models.dart';
import '../api/models.dart';
import '../live_prices/live_price_service.dart';
import '../theme/app_theme.dart';
import '../widgets/color_emoji.dart';
import '../widgets/live_price_builder.dart';
import '../widgets/mobile_kit.dart';

class FutureAnalysisScreen extends StatefulWidget {
  final ApiClient client;
  final LivePriceSource? livePrices;
  final String initialAsset;
  final bool lockAsset;

  const FutureAnalysisScreen({
    super.key,
    required this.client,
    required this.initialAsset,
    this.livePrices,
    this.lockAsset = false,
  });

  @override
  State<FutureAnalysisScreen> createState() => _FutureAnalysisScreenState();
}

class _FutureAnalysisScreenState extends State<FutureAnalysisScreen> {
  static const _assets = ['BTC', 'ETH', 'SOL'];
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
    Future<T?> safe<T>(Future<T> request) async {
      try {
        return await request;
      } catch (_) {
        return null;
      }
    }

    final responses = await Future.wait([
      widget.client.futureDecision(_asset, horizon: _horizon),
      safe(widget.client.futureTimeline(_asset)),
      safe(widget.client.today(_asset)),
      safe(widget.client.multiTimeframeRead(_asset)),
      safe(widget.client.impliedVolatility(_asset)),
    ]);
    return _FutureBundle(
      decision: responses[0] as FutureDecisionRead,
      timeline: responses[1] as FutureTimelineRead?,
      market: responses[2] as TodayRead?,
      timeframes: responses[3] as MultiTimeframeRead?,
      impliedVolatility: responses[4] as ImpliedVolatilityRead?,
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

  Future<void> _chooseHorizon() async {
    final selected = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: const Color(0xFF081727),
      builder: (sheetContext) => SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(22, 20, 22, 26),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Choisir l’horizon',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900),
              ),
              const SizedBox(height: 16),
              _HorizonSelector(
                selected: _horizon,
                onSelected: (value) => Navigator.of(sheetContext).pop(value),
              ),
            ],
          ),
        ),
      ),
    );
    if (selected != null) _selectHorizon(selected);
  }

  /// Everything that left the main page. Nothing is removed from the app: the
  /// scenarios, the per-timeframe reading, implied volatility and the five
  /// families all live here, one tap away.
  Future<void> _showFullDetails(
    FutureDecisionRead decision,
    _FutureBundle bundle,
  ) =>
      showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        backgroundColor: const Color(0xFF061525),
        builder: (sheetContext) => SafeArea(
          top: false,
          child: DraggableScrollableSheet(
            expand: false,
            initialChildSize: .86,
            maxChildSize: .96,
            builder: (context, controller) => ListView(
              controller: controller,
              padding: const EdgeInsets.fromLTRB(18, 18, 18, 28),
              children: [
                const Text(
                  'Détails complets',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 21,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                const SizedBox(height: 14),
                _Scenarios(
                  scenarios: decision.scenarios,
                  horizon: decision.horizon,
                ),
                if (bundle.market != null ||
                    bundle.timeframes != null ||
                    bundle.impliedVolatility != null) ...[
                  const SizedBox(height: 14),
                  _MarketContextCard(
                    market: bundle.market,
                    timeframes: bundle.timeframes,
                    impliedVolatility: bundle.impliedVolatility,
                  ),
                ],
                const SizedBox(height: 14),
                _Families(decision: decision),
              ],
            ),
          ),
        ),
      );

  Future<void> _showReasonDetails(
    FutureDecisionRead decision,
    _FutureBundle bundle,
  ) =>
      showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        backgroundColor: const Color(0xFF061525),
        builder: (sheetContext) {
          final reasons = _decisionFactors(decision, bundle);
          return DraggableScrollableSheet(
            expand: false,
            initialChildSize: .72,
            maxChildSize: .92,
            builder: (context, controller) => SafeArea(
              top: false,
              child: ListView(
                controller: controller,
                padding: const EdgeInsets.fromLTRB(20, 18, 20, 28),
                children: [
                  Row(
                    children: [
                      const Expanded(
                        child: Text(
                          'Détails des facteurs',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 21,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                      ),
                      IconButton(
                        tooltip: 'Fermer',
                        onPressed: () => Navigator.of(sheetContext).pop(),
                        icon: const Icon(Icons.close_rounded),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  for (var index = 0; index < reasons.length; index++) ...[
                    _ReasonRow(index: index, reason: reasons[index]),
                    if (index < reasons.length - 1)
                      const Divider(height: 1, color: Color(0xFF1D3853)),
                  ],
                ],
              ),
            ),
          );
        },
      );

  @override
  Widget build(BuildContext context) {
    return _FutureVisualFrame(
      asset: _asset,
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
              padding: const EdgeInsets.fromLTRB(18, 18, 18, 170),
              children: [
                if (!widget.lockAsset) ...[
                  _Selector(
                    values: _assets,
                    selected: _asset,
                    onSelected: _selectAsset,
                  ),
                  const SizedBox(height: 14),
                ],
                _AssetHeader(
                  asset: _asset,
                  source: widget.livePrices,
                  asOf: decision.asOf,
                  market: bundle.market?.marketData,
                ),
                const SizedBox(height: 15),
                _HorizonSelector(
                  selected: _horizon,
                  onSelected: _selectHorizon,
                ),
                const SizedBox(height: 16),
                _DecisionCard(
                  decision: decision,
                  bundle: bundle,
                  horizon: _horizon,
                  onHorizonTap: _chooseHorizon,
                ),
                // Section 18: the synthesis leads, then the evidence for it,
                // then the evidence against, then what would settle it.
                if (decision.synthesis != null) ...[
                  const SizedBox(height: 12),
                  _MarketStateCard(synthesis: decision.synthesis!),
                  const SizedBox(height: 12),
                  _EvidenceListCard(
                    key: const ValueKey('why-now-card'),
                    title: '⚠️ POURQUOI MAINTENANT ?',
                    tone: const Color(0xFFFFB34F),
                    items: decision.synthesis!.whyNow,
                    emptyText: 'Aucun facteur défavorable mesuré.',
                  ),
                  const SizedBox(height: 12),
                  _EvidenceListCard(
                    key: const ValueKey('counter-evidence-card'),
                    title: '🛡️ POURQUOI CE N’EST PAS ENCORE CONFIRMÉ',
                    tone: const Color(0xFF55DD8B),
                    items: decision.synthesis!.counterEvidence,
                  ),
                  if (decision.synthesis!.upcomingEvents.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    _CatalystListCard(
                      events: decision.synthesis!.upcomingEvents,
                    ),
                  ],
                  const SizedBox(height: 12),
                  _ConditionListCard(
                    key: const ValueKey('confirmation-card'),
                    title: '🚨 CE QUI CONFIRMERAIT',
                    tone: const Color(0xFFFF6676),
                    conditions: decision.synthesis!.confirmationConditions,
                    counter: decision.synthesis!.confirmationMet,
                  ),
                  const SizedBox(height: 12),
                  _ConditionListCard(
                    key: const ValueKey('invalidation-card'),
                    title: '🟢 CE QUI INVALIDERAIT',
                    tone: const Color(0xFF55DD8B),
                    conditions: decision.synthesis!.invalidationConditions,
                  ),
                  const SizedBox(height: 12),
                  _ScenarioPairCard(synthesis: decision.synthesis!),
                ],
                if (_coherenceNote(decision) != null) ...[
                  const SizedBox(height: 10),
                  _CoherenceNote(text: _coherenceNote(decision)!),
                ],
                const SizedBox(height: 14),
                _WhyDecisionCard(
                  decision: decision,
                  bundle: bundle,
                  onSeeAll: () => _showReasonDetails(decision, bundle),
                ),
                const SizedBox(height: 14),
                _ChangeAndRiskSection(decision: decision),
                const SizedBox(height: 14),
                _UpcomingEventsCard(
                  events: bundle.timeline?.events ?? const [],
                ),
                const SizedBox(height: 14),
                _SeeDetailsButton(
                  onTap: () => _showFullDetails(decision, bundle),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _FutureVisualFrame extends StatelessWidget {
  final String asset;
  final Widget child;

  const _FutureVisualFrame({required this.asset, required this.child});

  @override
  Widget build(BuildContext context) {
    final tint = switch (asset) {
      'ETH' => const Color(0xFF4645A9),
      'SOL' => const Color(0xFF087D7E),
      _ => const Color(0xFF0756A5),
    };
    return Stack(
      fit: StackFit.expand,
      children: [
        const ColoredBox(color: Color(0xFF020B18)),
        Opacity(
          opacity: .84,
          child: Image.asset(
            'assets/visuals/today_background.png',
            key: ValueKey('future-background-$asset'),
            fit: BoxFit.cover,
            alignment: Alignment.topCenter,
            color: tint.withValues(alpha: .16),
            colorBlendMode: BlendMode.screen,
            filterQuality: FilterQuality.high,
          ),
        ),
        const DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              stops: [0, .24, .58, 1],
              colors: [
                Color(0x24000512),
                Color(0x74040F20),
                Color(0xE8040D1A),
                Color(0xFF020912),
              ],
            ),
          ),
        ),
        SafeArea(
          bottom: false,
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 900),
              child: child,
            ),
          ),
        ),
      ],
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

class _HorizonSelector extends StatelessWidget {
  static const _values = ['24h', '7d', '30d'];
  final String selected;
  final ValueChanged<String> onSelected;

  const _HorizonSelector({required this.selected, required this.onSelected});

  @override
  Widget build(BuildContext context) => Row(
        children: [
          for (var index = 0; index < _values.length; index++) ...[
            if (index > 0) const SizedBox(width: 9),
            Expanded(
              child: _HorizonButton(
                value: _values[index],
                selected: selected == _values[index],
                onTap: () => onSelected(_values[index]),
              ),
            ),
          ],
        ],
      );
}

class _HorizonButton extends StatelessWidget {
  final String value;
  final bool selected;
  final VoidCallback onTap;

  const _HorizonButton({
    required this.value,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) => Material(
        color: Colors.transparent,
        child: InkWell(
          key: ValueKey('horizon-$value'),
          onTap: onTap,
          borderRadius: BorderRadius.circular(18),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 180),
            height: 42,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: selected
                  ? const Color(0xFF123E71).withValues(alpha: .72)
                  : const Color(0xFF0B1727).withValues(alpha: .72),
              borderRadius: BorderRadius.circular(18),
              border: Border.all(
                color: selected
                    ? const Color(0xFF61A8FF)
                    : const Color(0xFF46617F),
                width: selected ? 1.6 : 1,
              ),
              boxShadow: selected
                  ? [
                      BoxShadow(
                        color: mobileBlue.withValues(alpha: .22),
                        blurRadius: 14,
                      ),
                    ]
                  : null,
            ),
            child: Text(
              _horizonLabel(value),
              style: TextStyle(
                color: selected ? Colors.white : mobileMuted,
                fontSize: 15,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
        ),
      );
}

class _AssetHeader extends StatelessWidget {
  final String asset;
  final LivePriceSource? source;
  final DateTime? asOf;
  final MarketPriceRead? market;

  const _AssetHeader({
    required this.asset,
    required this.source,
    required this.asOf,
    required this.market,
  });

  @override
  Widget build(BuildContext context) => LivePriceBuilder(
        source: source,
        asset: asset,
        builder: (context, tick, connection) {
          final price = tick?.priceEur ?? market?.displayPrice;
          final unit = tick != null ? 'EUR' : market?.displayUnit;
          final change = tick?.change24hPct ?? market?.change24hPct;
          final isLive = tick != null && connection == LivePriceConnection.live;
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  CryptoLogo(asset: asset, size: 68),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          _assetName(asset),
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 30,
                            height: 1,
                            fontWeight: FontWeight.w900,
                            letterSpacing: -.7,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          asset,
                          style: const TextStyle(
                            color: mobileMuted,
                            fontSize: 16,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 7,
                        ),
                        decoration: BoxDecoration(
                          color: const Color(0xB9050B13),
                          borderRadius: BorderRadius.circular(22),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              width: 9,
                              height: 9,
                              decoration: BoxDecoration(
                                color: isLive
                                    ? const Color(0xFF55E592)
                                    : AppColors.warn,
                                shape: BoxShape.circle,
                              ),
                            ),
                            const SizedBox(width: 6),
                            Text(
                              isLive ? 'Live' : 'Analyse',
                              style: const TextStyle(
                                color: Color(0xFFEAF2FF),
                                fontSize: 12,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 5),
                      // The badge above describes the price feed; this line
                      // describes the analysis, which is refreshed far less
                      // often. Labelling both 'MAJ' made a live price look
                      // stale by however long the analysis had been running.
                      Text(
                        'Analyse du ${_dateCompact(asOf)}',
                        style: const TextStyle(
                          color: mobileMuted,
                          fontSize: 9.5,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
              const SizedBox(height: 15),
              Text(
                _priceLabel(price, unit),
                key: ValueKey('asset-price-$asset'),
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 32,
                  height: 1,
                  fontWeight: FontWeight.w900,
                  letterSpacing: .4,
                ),
              ),
              const SizedBox(height: 9),
              Row(
                children: [
                  Text(
                    _changeLabel(change),
                    style: TextStyle(
                      color: change == null
                          ? mobileMuted
                          : change >= 0
                              ? AppColors.measured
                              : AppColors.bad,
                      fontSize: 19,
                      height: 1,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(width: 6),
                  const Text(
                    '(24 h)',
                    style: TextStyle(color: mobileMuted, fontSize: 12),
                  ),
                ],
              ),
            ],
          );
        },
      );
}

class _DecisionCard extends StatelessWidget {
  final FutureDecisionRead decision;
  final _FutureBundle bundle;
  final String horizon;
  final VoidCallback onHorizonTap;

  const _DecisionCard({
    required this.decision,
    required this.bundle,
    required this.horizon,
    required this.onHorizonTap,
  });

  @override
  Widget build(BuildContext context) {
    final visual = _decisionVisual(decision.decision);
    return ClipRRect(
      key: const ValueKey('decision-card'),
      borderRadius: BorderRadius.circular(22),
      child: Stack(
        children: [
          Positioned.fill(
            child: Transform.scale(
              // The supplied visual already contains its luminous frame and
              // a transparent export margin. Stretching the full artwork,
              // then cropping only that margin, prevents both the former
              // nested-card effect and the horizontal crop caused by cover.
              alignment: const Alignment(0, -.18),
              scaleX: 1.045,
              scaleY: 1.155,
              child: Image.asset(
                visual.asset,
                key: ValueKey(visual.asset),
                fit: BoxFit.fill,
                filterQuality: FilterQuality.high,
              ),
            ),
          ),
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.centerLeft,
                  end: Alignment.centerRight,
                  stops: const [0, .6, 1],
                  colors: [
                    const Color(0xFF061121).withValues(alpha: .95),
                    const Color(0xFF071426).withValues(alpha: .68),
                    visual.overlay.withValues(alpha: .1),
                  ],
                ),
              ),
            ),
          ),
          Container(
            height: 250,
            padding: const EdgeInsets.fromLTRB(17, 18, 17, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'EST-CE LE BON MOMENT POUR ACHETER ?',
                  style: TextStyle(
                    color: Color(0xFFE7F0FF),
                    fontSize: 12.5,
                    height: 1.25,
                    fontWeight: FontWeight.w800,
                    letterSpacing: .2,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  _decisionLabel(decision.decision),
                  style: TextStyle(
                    color: visual.accent,
                    fontSize: 40,
                    height: .95,
                    fontWeight: FontWeight.w900,
                    letterSpacing: -.8,
                    shadows: [
                      Shadow(
                        color: visual.glow.withValues(alpha: .55),
                        blurRadius: 14,
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 8),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 300),
                  child: Text(
                    _decisionHeadline(decision, bundle),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: Color(0xFFF4F8FF),
                      fontSize: 15.5,
                      height: 1.25,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                const Spacer(),
                Row(
                  children: [
                    Expanded(
                      child: _DecisionMetric(
                        icon: Icons.shield_outlined,
                        label: 'Risque',
                        value: _riskLevelLabel(decision.eventRisk),
                        tone: _impactColor(decision.eventRisk),
                      ),
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: _DecisionMetric(
                        key: const ValueKey('decision-horizon'),
                        icon: Icons.schedule_rounded,
                        label: 'Horizon',
                        value: _horizonLongLabel(horizon),
                        tone: mobileBlue,
                        onTap: onHorizonTap,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: _DecisionMetric(
                        icon: Icons.show_chart_rounded,
                        label: 'Mouvement',
                        value: _expectedMovementLabel(decision.movement),
                        tone: visual.accent,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: _DecisionMetric(
                        icon: Icons.bar_chart_rounded,
                        label: 'Confiance',
                        value: _confidenceLevelLabel(decision.confidence),
                        tone: mobileBlue,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _DecisionMetric extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Color tone;
  final VoidCallback? onTap;

  const _DecisionMetric({
    super.key,
    required this.icon,
    required this.label,
    required this.value,
    required this.tone,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) => Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: Container(
            height: 64,
            padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 8),
            decoration: BoxDecoration(
              color: const Color(0xC20A1726),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: const Color(0xFF314861)),
            ),
            child: Row(
              children: [
                Icon(icon, color: tone, size: 19),
                const SizedBox(width: 5),
                Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        label,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(color: mobileMuted, fontSize: 9),
                      ),
                      const SizedBox(height: 2),
                      FittedBox(
                        fit: BoxFit.scaleDown,
                        alignment: Alignment.centerLeft,
                        child: Text(
                          value,
                          maxLines: 1,
                          style: TextStyle(
                            color: tone,
                            fontSize: 13,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      );
}

class _WhyDecisionCard extends StatelessWidget {
  final FutureDecisionRead decision;
  final _FutureBundle bundle;
  final VoidCallback onSeeAll;

  const _WhyDecisionCard({
    required this.decision,
    required this.bundle,
    required this.onSeeAll,
  });

  @override
  Widget build(BuildContext context) {
    final reasons = _decisionFactors(decision, bundle);
    // Section 13: a factor pointing against the decision is not a reason for
    // it. Listing "tendance court terme porteuse" under "Pourquoi attendre ?"
    // asked the reader to accept an argument that argues the other way.
    final supporting =
        reasons.where((item) => _supportsDecision(item, decision)).toList();
    final counter =
        reasons.where((item) => !_supportsDecision(item, decision)).toList();
    return GlassPanel(
      borderColor: const Color(0xFF2B669B),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  'Pourquoi ${_decisionLabel(decision.decision).toLowerCase()} ?',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 20,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
              TextButton(
                key: const ValueKey('why-see-all'),
                onPressed: onSeeAll,
                style: TextButton.styleFrom(
                  foregroundColor: mobileBlue,
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  minimumSize: const Size(0, 36),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text('Voir tout'),
                    Icon(Icons.chevron_right_rounded, size: 20),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          for (var index = 0; index < supporting.length; index++) ...[
            _ReasonRow(index: index, reason: supporting[index]),
            if (index < supporting.length - 1)
              const Divider(height: 1, color: Color(0xFF1D3853)),
          ],
          if (counter.isNotEmpty) ...[
            const SizedBox(height: 14),
            const Divider(height: 1, color: Color(0xFF1D3853)),
            const SizedBox(height: 12),
            const Text(
              'CE QUI RESTE FAVORABLE',
              style: TextStyle(
                color: Color(0xFF55DD8B),
                fontSize: 11,
                letterSpacing: .8,
                fontWeight: FontWeight.w900,
              ),
            ),
            for (var index = 0; index < counter.length; index++)
              _ReasonRow(
                index: supporting.length + index,
                reason: counter[index],
              ),
          ],
        ],
      ),
    );
  }
}

class _ReasonRow extends StatelessWidget {
  final int index;
  final _DecisionFactor reason;

  const _ReasonRow({required this.index, required this.reason});

  @override
  Widget build(BuildContext context) {
    final tone = _reasonTone(index);
    return InkWell(
      key: ValueKey('decision-reason-${index + 1}'),
      onTap: () => _showReasonDetail(context, reason),
      borderRadius: BorderRadius.circular(10),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 31,
              height: 31,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [tone, tone.withValues(alpha: .64)],
                ),
                boxShadow: [
                  BoxShadow(
                    color: tone.withValues(alpha: .26),
                    blurRadius: 10,
                  ),
                ],
              ),
              child: Text(
                '${index + 1}',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 14,
                  fontWeight: FontWeight.w900,
                ),
              ),
            ),
            const SizedBox(width: 9),
            SizedBox(
              width: 30,
              child: Center(child: ColorEmoji(emoji: reason.emoji, size: 23)),
            ),
            const SizedBox(width: 9),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    reason.title,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 14,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    reason.description,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: mobileMuted,
                      fontSize: 11.5,
                      height: 1.28,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 7),
            Container(
              constraints: const BoxConstraints(minWidth: 58, maxWidth: 72),
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
              decoration: BoxDecoration(
                color: tone.withValues(alpha: .1),
                borderRadius: BorderRadius.circular(9),
                border: Border.all(color: tone.withValues(alpha: .34)),
              ),
              child: Column(
                children: [
                  if (reason.when.isNotEmpty)
                    Text(
                      reason.when,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: tone,
                        fontSize: 8.5,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  Text(
                    reason.impactOnDirection == 'NONE'
                        ? 'DIRECTION INCERTAINE'
                        : _reasonImpactLabel(reason.direction),
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: _reasonImpactColor(reason.direction),
                      fontSize: 8.5,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                  if (_trendLabelFr(reason.trend) != null &&
                      reason.trend != 'STABLE')
                    Text(
                      _trendLabelFr(reason.trend)!,
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        color: Color(0xFFFFB34F),
                        fontSize: 7.5,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  Text(
                    'IMPACT ${reason.impact}',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: tone,
                      fontSize: 7.5,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ),
            const Icon(
              Icons.chevron_right_rounded,
              size: 18,
              color: Color(0xFF55749B),
            ),
          ],
        ),
      ),
    );
  }
}

/// One factor, explained end to end: what it is, what the market had priced,
/// why it transmits to the price, what it may cause, and what would reverse it.
void _showReasonDetail(BuildContext context, _DecisionFactor reason) {
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: const Color(0xFF061525),
    builder: (sheetContext) => SafeArea(
      top: false,
      child: DraggableScrollableSheet(
        expand: false,
        initialChildSize: .74,
        maxChildSize: .94,
        builder: (context, controller) => ListView(
          controller: controller,
          padding: const EdgeInsets.fromLTRB(22, 20, 22, 28),
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ColorEmoji(emoji: reason.emoji, size: 26),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    reason.title,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 20,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 7),
              decoration: BoxDecoration(
                color:
                    _reasonImpactColor(reason.direction).withValues(alpha: .12),
                borderRadius: BorderRadius.circular(9),
                border: Border.all(
                  color: _reasonImpactColor(reason.direction)
                      .withValues(alpha: .36),
                ),
              ),
              child: Text(
                'STATUT · ${_reasonImpactLabel(reason.direction)}',
                style: TextStyle(
                  color: _reasonImpactColor(reason.direction),
                  fontSize: 11,
                  fontWeight: FontWeight.w900,
                ),
              ),
            ),
            if (reason.kind == _FactorKind.futureCatalyst)
              _ReasonDetailBlock(
                title: '📅 CE QUI VA SE PASSER',
                body: reason.description,
              )
            else
              // An already-measured signal is not something that "arrives".
              _ReasonDetailBlock(
                title: '🔍 CE QU’ON OBSERVE',
                body: reason.observation,
              ),
            if (reason.kind == _FactorKind.futureCatalyst)
              _ReasonDetailBlock(
                title: '🎯 CE QUE LE MARCHÉ ATTEND',
                body: reason.marketExpectation ??
                    'Anticipations actuellement indisponibles.',
                muted: reason.marketExpectation == null,
              ),
            _ReasonDetailBlock(
              title: '💡 POURQUOI CELA COMPTE',
              body: reason.whyItMatters,
            ),
            if (reason.caveat.isNotEmpty)
              _ReasonDetailBlock(
                  title: '⚠️ À GARDER EN TÊTE', body: reason.caveat),
            _ReasonDetailBlock(
              title: '📈 CE QUE ÇA PEUT ENGENDRER',
              body: reason.consequence,
            ),
            if (reason.kind == _FactorKind.futureCatalyst) ...[
              _ReasonDetailBlock(
                title: '🟢 SI LE RÉSULTAT EST PLUS POSITIF QUE PRÉVU',
                body: reason.upsideCase,
              ),
              _ReasonDetailBlock(
                title: '🔴 SI LE RÉSULTAT EST PLUS NÉGATIF QUE PRÉVU',
                body: reason.downsideCase,
              ),
            ] else
              _ReasonDetailBlock(
                title: '🔄 CE QUI INVALIDERAIT CE SIGNAL',
                body: reason.invalidation,
              ),
            const SizedBox(height: 18),
            const Divider(height: 1, color: Color(0xFF16304A)),
            const SizedBox(height: 12),
            Text(
              '🔗 SOURCE',
              style: TextStyle(
                color: mobileMuted.withValues(alpha: .8),
                fontSize: 10,
                letterSpacing: .8,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 5),
            Text(
              [
                if (reason.source != null && reason.source!.isNotEmpty)
                  reason.source!,
                if (reason.when.isNotEmpty) reason.when,
              ].join(' · '),
              style: const TextStyle(
                color: Color(0xFF7E93AD),
                fontSize: 11,
                height: 1.35,
              ),
            ),
            if (reason.sourceUrl != null && reason.sourceUrl!.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  reason.sourceUrl!,
                  style: const TextStyle(
                    color: Color(0xFF5C7A9C),
                    fontSize: 10.5,
                  ),
                ),
              ),
          ],
        ),
      ),
    ),
  );
}

class _ReasonDetailBlock extends StatelessWidget {
  final String title;
  final String body;
  final bool muted;

  const _ReasonDetailBlock({
    required this.title,
    required this.body,
    this.muted = false,
  });

  @override
  Widget build(BuildContext context) {
    // An empty section is noise: the heading promises content that is not
    // there. Nothing is rendered rather than an empty block.
    if (body.trim().isEmpty) return const SizedBox.shrink();
    final separator = title.indexOf(' ');
    final emoji = separator > 0 ? title.substring(0, separator) : null;
    final label = separator > 0 ? title.substring(separator + 1) : title;
    return Padding(
      padding: const EdgeInsets.only(top: 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              if (emoji != null) ...[
                ColorEmoji(emoji: emoji, size: 13),
                const SizedBox(width: 6),
              ],
              Expanded(
                child: Text(
                  label,
                  style: TextStyle(
                    color: mobileMuted.withValues(alpha: .85),
                    fontSize: 10.5,
                    letterSpacing: .9,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            body,
            style: TextStyle(
              color: muted ? const Color(0xFF8FA4BD) : const Color(0xFFE6EEFA),
              fontSize: 13.5,
              height: 1.42,
              fontStyle: muted ? FontStyle.italic : FontStyle.normal,
            ),
          ),
        ],
      ),
    );
  }
}

/// Explain a decision that disagrees with the underlying reading.
///
/// Showing "ATTENDRE" next to a bullish bias without a word of explanation
/// reads as a contradiction. The sentence is built from the payload only, so it
/// states why the two differ and never invents a third opinion.
String? _coherenceNote(FutureDecisionRead decision) {
  final bullish = decision.direction.contains('BULLISH');
  final bearish = decision.direction.contains('BEARISH');
  final horizon = _horizonLongLabel(decision.horizon);

  if (decision.decision == 'WAIT' && decision.eventRiskActive) {
    final event = decision.nextEvent?.title;
    final trigger =
        event == null ? 'un événement majeur non encore publié' : '« $event »';
    if (bullish) {
      return 'La lecture de fond reste haussière, mais $trigger tombe dans les '
          '$horizon et son issue n’est pas connue : l’analyse préfère ne pas '
          's’engager par-dessus.';
    }
    if (bearish) {
      return 'La lecture de fond est baissière, mais $trigger tombe dans les '
          '$horizon : vendre maintenant reviendrait à parier sur une issue '
          'que l’analyse ne connaît pas.';
    }
    return 'Aucune direction ne se dégage et $trigger tombe dans les $horizon.';
  }
  if (decision.decision == 'SELL' && bullish) {
    return 'Le marché reste haussier sur le fond, mais les risques à court '
        'terme justifient actuellement VENDRE sur $horizon.';
  }
  if (decision.decision == 'BUY' && bearish) {
    return 'Le fond reste baissier, mais la configuration actuelle justifie '
        'ACHETER sur $horizon.';
  }
  return null;
}

class _CoherenceNote extends StatelessWidget {
  final String text;

  const _CoherenceNote({required this.text});

  @override
  Widget build(BuildContext context) => Container(
        key: const ValueKey('decision-coherence-note'),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
        decoration: BoxDecoration(
          color: const Color(0x22285F8C),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: const Color(0xFF24506F)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(
              Icons.info_outline_rounded,
              size: 17,
              color: Color(0xFF6FA8DA),
            ),
            const SizedBox(width: 9),
            Expanded(
              child: Text(
                text,
                style: const TextStyle(
                  color: Color(0xFFD7E5F6),
                  fontSize: 12.5,
                  height: 1.38,
                ),
              ),
            ),
          ],
        ),
      );
}

/// The market state, its headline and the two-line summary.
class _MarketStateCard extends StatelessWidget {
  final FutureSynthesisRead synthesis;

  const _MarketStateCard({required this.synthesis});

  @override
  Widget build(BuildContext context) => GlassPanel(
        key: const ValueKey('market-state-card'),
        borderColor: _stateColor(synthesis.state).withValues(alpha: .55),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Row(
                    children: [
                      ColorEmoji(emoji: _stateEmoji(synthesis.state), size: 15),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          _stateWords(synthesis.stateLabel),
                          style: TextStyle(
                            color: _stateColor(synthesis.state),
                            fontSize: 15,
                            letterSpacing: .4,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                if (synthesis.dataStatus == 'PARTIAL_DATA')
                  const _PartialDataChip(),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              synthesis.headline,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 17,
                height: 1.25,
                fontWeight: FontWeight.w800,
              ),
            ),
            if (synthesis.summary.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                synthesis.summary,
                style: const TextStyle(
                  color: Color(0xFFD3E0F0),
                  fontSize: 13,
                  height: 1.42,
                ),
              ),
            ],
            const SizedBox(height: 10),
            Text(
              'Incertitude ${_uncertaintyFr(synthesis.uncertainty)}',
              style: TextStyle(
                color: mobileMuted.withValues(alpha: .95),
                fontSize: 11,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
      );
}

/// Missing families are declared, never turned into a neutral stance.
class _PartialDataChip extends StatelessWidget {
  const _PartialDataChip();

  @override
  Widget build(BuildContext context) => Container(
        key: const ValueKey('partial-data-chip'),
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
        decoration: BoxDecoration(
          color: const Color(0x33FFB34F),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: const Color(0x66FFB34F)),
        ),
        child: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            ColorEmoji(emoji: '⚠️', size: 10),
            SizedBox(width: 4),
            Text(
              'ANALYSE PARTIELLE',
              style: TextStyle(
                color: Color(0xFFFFB34F),
                fontSize: 9,
                fontWeight: FontWeight.w900,
              ),
            ),
          ],
        ),
      );
}

/// One list of evidence entries: why now, or what argues against it.
class _EvidenceListCard extends StatelessWidget {
  final String title;
  final Color tone;
  final List<FutureEvidenceRead> items;
  final String emptyText;

  const _EvidenceListCard({
    super.key,
    required this.title,
    required this.tone,
    required this.items,
    this.emptyText = '',
  });

  @override
  Widget build(BuildContext context) => GlassPanel(
        borderColor: tone.withValues(alpha: .4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: TextStyle(
                color: tone,
                fontSize: 12.5,
                letterSpacing: .5,
                fontWeight: FontWeight.w900,
              ),
            ),
            const SizedBox(height: 10),
            if (items.isEmpty)
              Text(
                emptyText,
                style: const TextStyle(color: mobileMuted, fontSize: 12),
              ),
            for (final item in items)
              Padding(
                padding: const EdgeInsets.only(bottom: 11),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            item.label,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 13.5,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                        ),
                        Text(
                          '${_reasonImpactLabel(_normalisedDirection(item.direction))}'
                          ' · ${_impactLabelFr(item.impact)}',
                          style: TextStyle(
                            color: _reasonImpactColor(
                              _normalisedDirection(item.direction),
                            ),
                            fontSize: 8.5,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 3),
                    Text(
                      item.observation,
                      style: const TextStyle(
                        color: mobileMuted,
                        fontSize: 11.5,
                        height: 1.3,
                      ),
                    ),
                    if (item.whyItMatters.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 3),
                        child: Text(
                          '→ ${item.whyItMatters}',
                          style: const TextStyle(
                            color: Color(0xFF9FB6D0),
                            fontSize: 11,
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

/// Confirmation and invalidation, each condition with the weight it carries.
class _ConditionListCard extends StatelessWidget {
  final String title;
  final Color tone;
  final List<FutureConditionRead> conditions;
  final String? counter;

  const _ConditionListCard({
    super.key,
    required this.title,
    required this.tone,
    required this.conditions,
    this.counter,
  });

  @override
  Widget build(BuildContext context) => GlassPanel(
        borderColor: tone.withValues(alpha: .4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    title,
                    style: TextStyle(
                      color: tone,
                      fontSize: 12.5,
                      letterSpacing: .5,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                ),
                if (counter != null)
                  Text(
                    counter!,
                    style: TextStyle(
                      color: mobileMuted.withValues(alpha: .95),
                      fontSize: 11,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 9),
            for (final item in conditions)
              Padding(
                padding: const EdgeInsets.only(bottom: 7),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      item.met ? '✓' : '○',
                      style: TextStyle(
                        color: item.met ? tone : mobileMuted,
                        fontSize: 12,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        item.text,
                        style: TextStyle(
                          color: item.met
                              ? const Color(0xFFE6EEFA)
                              : const Color(0xFF9FB6D0),
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

/// The few catalysts worth watching, ranked by relevance to this asset.
class _CatalystListCard extends StatelessWidget {
  final List<FutureCatalystRead> events;

  const _CatalystListCard({required this.events});

  @override
  Widget build(BuildContext context) => GlassPanel(
        key: const ValueKey('upcoming-catalysts'),
        borderColor: const Color(0xFF245E90),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                ColorEmoji(emoji: '👀', size: 13),
                SizedBox(width: 6),
                Text(
                  'À SURVEILLER',
                  style: TextStyle(
                    color: Color(0xFF6FA8DA),
                    fontSize: 12.5,
                    letterSpacing: .5,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            for (final item in events)
              Padding(
                padding: const EdgeInsets.only(bottom: 9),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            _eventTitleFr(item.title),
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 13,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            '${_dateShort(DateTime.tryParse(item.scheduledAt ?? ''))}'
                            ' · ${item.source}',
                            style: const TextStyle(
                              color: mobileMuted,
                              fontSize: 10.5,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      'IMPACT ${_impactLabelFr(item.assetImpact)}',
                      style: const TextStyle(
                        color: Color(0xFFFFB34F),
                        fontSize: 8.5,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      );
}

/// Main and alternative scenario, always published together.
class _ScenarioPairCard extends StatelessWidget {
  final FutureSynthesisRead synthesis;

  const _ScenarioPairCard({required this.synthesis});

  Widget _row(String emoji, String title, FutureScenarioBriefRead? scenario) {
    if (scenario == null) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              ColorEmoji(emoji: emoji, size: 13),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  '$title — ${scenario.name}',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 3),
          Text(
            scenario.description,
            style: const TextStyle(
              color: mobileMuted,
              fontSize: 11.5,
              height: 1.32,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            'Plausibilité ${scenario.likelihood.toLowerCase()}',
            style: const TextStyle(color: Color(0xFF7E93AD), fontSize: 10.5),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) => GlassPanel(
        key: const ValueKey('scenario-pair'),
        borderColor: const Color(0xFF24506F),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _row('🎯', 'Scénario principal', synthesis.mainScenario),
            _row('🔄', 'Scénario alternatif', synthesis.alternativeScenario),
          ],
        ),
      );
}

Color _stateColor(String state) => switch (state) {
      'CORRECTION_CONFIRMED' => const Color(0xFFFF6676),
      'ELEVATED_RISK' => const Color(0xFFFFB34F),
      'MIXED' => const Color(0xFFEBD14F),
      'CONSTRUCTIVE' || 'CALM' => const Color(0xFF55DD8B),
      _ => const Color(0xFF94A8C2),
    };

/// The label ships with its marker; the emoji is rendered separately so the
/// canvas renderer can colour it.
String _stateEmoji(String state) => switch (state) {
      'CORRECTION_CONFIRMED' => '🔴',
      'ELEVATED_RISK' => '🟠',
      'MIXED' => '🟡',
      'CONSTRUCTIVE' || 'CALM' => '🟢',
      _ => '⚪',
    };

String _stateWords(String label) =>
    label.replaceAll(RegExp(r'^[^A-Za-zÀ-ÿ]+'), '').trim();

String _uncertaintyFr(String value) => switch (value) {
      'LOW' => 'faible',
      'HIGH' => 'élevée',
      'VERY_HIGH' => 'très élevée',
      _ => 'moyenne',
    };

class _SeeDetailsButton extends StatelessWidget {
  final VoidCallback onTap;

  const _SeeDetailsButton({required this.onTap});

  @override
  Widget build(BuildContext context) => GlassPanel(
        borderColor: const Color(0xFF24506F),
        child: InkWell(
          key: const ValueKey('see-full-details'),
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(
              children: [
                const Icon(Icons.tune_rounded, size: 20, color: mobileBlue),
                const SizedBox(width: 10),
                const Expanded(
                  child: Text(
                    'VOIR LES DÉTAILS',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 13.5,
                      letterSpacing: .6,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                ),
                Flexible(
                  child: Text(
                    'scénarios · familles',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    textAlign: TextAlign.end,
                    style: TextStyle(
                      color: mobileMuted.withValues(alpha: .9),
                      fontSize: 9.5,
                    ),
                  ),
                ),
                const Icon(
                  Icons.chevron_right_rounded,
                  size: 20,
                  color: Color(0xFF55749B),
                ),
              ],
            ),
          ),
        ),
      );
}

class _ChangeAndRiskSection extends StatelessWidget {
  final FutureDecisionRead decision;

  const _ChangeAndRiskSection({required this.decision});

  @override
  Widget build(BuildContext context) => IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(
              // Section 14: which way each condition pushes is part of the
              // information. One undifferentiated list made the reader work it
              // out for themselves.
              child: _SignalListCard(
                icon: '🟢',
                title: 'Pour passer à acheter',
                items: (decision.conditionsToBuy.isNotEmpty
                        ? decision.conditionsToBuy
                        : decision.changes)
                    .map(_frenchifyEventNames)
                    .toList(),
                tone: const Color(0xFF55DD8B),
                bullet: '✓',
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _SignalListCard(
                icon: '🔴',
                title: 'Pour passer à vendre',
                items: (decision.conditionsToSell.isNotEmpty
                        ? decision.conditionsToSell
                        : _decisionRisks(decision))
                    .map(_frenchifyEventNames)
                    .toList(),
                tone: const Color(0xFFFF6676),
                bullet: '!',
              ),
            ),
          ],
        ),
      );
}

class _SignalListCard extends StatelessWidget {
  final String icon;
  final String title;
  final List<String> items;
  final Color tone;
  final String bullet;

  const _SignalListCard({
    required this.icon,
    required this.title,
    required this.items,
    required this.tone,
    required this.bullet,
  });

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(13),
        decoration: BoxDecoration(
          color: const Color(0xD9091723),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: tone.withValues(alpha: .58)),
          boxShadow: [
            BoxShadow(
              color: tone.withValues(alpha: .08),
              blurRadius: 16,
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ColorEmoji(emoji: icon, size: 18),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    title,
                    style: TextStyle(
                      color: tone,
                      fontSize: 12,
                      height: 1.2,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 9),
            if (items.isEmpty)
              const Text(
                'Aucun élément supplémentaire sourcé.',
                style: TextStyle(
                  color: mobileMuted,
                  fontSize: 10.5,
                  height: 1.25,
                ),
              )
            else
              for (final item in items.take(4))
                Padding(
                  padding: const EdgeInsets.only(bottom: 7),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        width: 18,
                        height: 18,
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                          color: tone.withValues(alpha: .14),
                          shape: BoxShape.circle,
                        ),
                        child: Text(
                          bullet,
                          style: TextStyle(
                            color: tone,
                            fontSize: 11,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                      ),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          _cleanExplanation(item),
                          style: const TextStyle(
                            color: Color(0xFFD7E2F3),
                            fontSize: 10.5,
                            height: 1.25,
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

class _UpcomingEventsCard extends StatefulWidget {
  final List<FutureEventRead> events;

  const _UpcomingEventsCard({required this.events});

  @override
  State<_UpcomingEventsCard> createState() => _UpcomingEventsCardState();
}

class _UpcomingEventsCardState extends State<_UpcomingEventsCard> {
  var _expanded = false;

  @override
  Widget build(BuildContext context) {
    // Chronological order buried the FOMC behind three Treasury bill auctions.
    // The three shown are the three that matter most; expanding restores the
    // full calendar in date order.
    const rank = {'CRITICAL': 3, 'HIGH': 2, 'MEDIUM': 1, 'LOW': 0};
    final byImportance = [...widget.events]..sort((left, right) {
        final byRank = (rank[right.importance.toUpperCase()] ?? 0)
            .compareTo(rank[left.importance.toUpperCase()] ?? 0);
        if (byRank != 0) return byRank;
        return (left.countdownSeconds ?? 0)
            .compareTo(right.countdownSeconds ?? 0);
      });
    final displayed = _expanded ? widget.events : byImportance.take(3).toList();
    return GlassPanel(
      borderColor: const Color(0xFF245E90),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const ColorEmoji(emoji: '🗓️', size: 19),
              const SizedBox(width: 8),
              const Flexible(
                child: Text(
                  'À surveiller',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
              const Spacer(),
              if (widget.events.length > 3)
                TextButton(
                  key: const ValueKey('events-see-all'),
                  onPressed: () => setState(() => _expanded = !_expanded),
                  style: TextButton.styleFrom(
                    foregroundColor: mobileBlue,
                    padding: const EdgeInsets.symmetric(horizontal: 2),
                    minimumSize: const Size(0, 36),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Flexible(
                        child: Text(
                          _expanded ? 'Réduire' : 'Voir tous',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      Icon(
                        _expanded
                            ? Icons.expand_less_rounded
                            : Icons.chevron_right_rounded,
                        size: 19,
                      ),
                    ],
                  ),
                ),
            ],
          ),
          const SizedBox(height: 8),
          if (widget.events.isEmpty)
            const Text(
              'Aucun événement sourcé dans les 30 prochains jours.',
              style: TextStyle(color: mobileMuted),
            )
          else
            for (var index = 0; index < displayed.length; index++) ...[
              _UpcomingEventRow(event: displayed[index]),
              if (index < displayed.length - 1)
                const Divider(height: 1, color: Color(0xFF1D3853)),
            ],
        ],
      ),
    );
  }
}

class _UpcomingEventRow extends StatelessWidget {
  final FutureEventRead event;

  const _UpcomingEventRow({required this.event});

  @override
  Widget build(BuildContext context) {
    final tone = _impactColor(event.importance);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        key: ValueKey('event-${event.id}'),
        onTap: () => _showEventDetails(context, event),
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 9),
          child: Row(
            children: [
              Container(
                width: 52,
                padding: const EdgeInsets.symmetric(vertical: 7),
                decoration: BoxDecoration(
                  color: const Color(0xFF14243A),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: const Color(0xFF304C69)),
                ),
                child: Column(
                  children: [
                    Text(
                      '${event.scheduledAt?.day ?? '—'}',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 20,
                        height: 1,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      _monthLabel(event.scheduledAt),
                      style: const TextStyle(
                        color: mobileMuted,
                        fontSize: 9,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _eventTitleFr(event.title),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 13,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      '${_countdown(event.countdownSeconds)} · ${event.source}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style:
                          const TextStyle(color: mobileMuted, fontSize: 10.5),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                decoration: BoxDecoration(
                  color: tone.withValues(alpha: .13),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: tone.withValues(alpha: .35)),
                ),
                child: Text(
                  _impactLabel(event.importance),
                  style: TextStyle(
                    color: tone,
                    fontSize: 9,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
              const SizedBox(width: 2),
              const Icon(
                Icons.chevron_right_rounded,
                color: Color(0xFF6FA9E8),
                size: 17,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

Future<void> _showEventDetails(
  BuildContext context,
  FutureEventRead event,
) =>
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF061525),
      builder: (sheetContext) => SafeArea(
        top: false,
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(22, 20, 22, 28),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const ColorEmoji(emoji: '🗓️', size: 24),
                  const SizedBox(width: 9),
                  const Expanded(
                    child: Text(
                      'Détail de l’événement',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 20,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ),
                  IconButton(
                    tooltip: 'Fermer',
                    onPressed: () => Navigator.of(sheetContext).pop(),
                    icon: const Icon(Icons.close_rounded),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              Text(
                _eventTitleFr(event.title),
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  height: 1.25,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 16),
              _DetailLine(
                  label: 'Date', value: _dateCompact(event.scheduledAt)),
              _DetailLine(
                label: 'Échéance',
                value: _countdown(event.countdownSeconds),
              ),
              _DetailLine(
                label: 'Importance',
                value: _impactLabel(event.importance),
              ),
              _DetailLine(label: 'Statut', value: _plainLabel(event.status)),
              _DetailLine(
                label: 'Effet directionnel',
                value: _directionLabel(event.direction),
              ),
              _DetailLine(
                label: 'Mouvement attendu',
                value: _movementLabel(event.movement),
              ),
              _DetailLine(label: 'Fraîcheur', value: event.freshness),
              _DetailLine(label: 'Source', value: event.source),
              if (event.sourceUrl case final url?)
                _DetailLine(label: 'Lien source', value: url),
            ],
          ),
        ),
      ),
    );

class _DetailLine extends StatelessWidget {
  final String label;
  final String value;

  const _DetailLine({required this.label, required this.value});

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 112,
              child: Text(
                label,
                style: const TextStyle(
                  color: mobileMuted,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            Expanded(
              child: SelectableText(
                value,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 13,
                  height: 1.35,
                ),
              ),
            ),
          ],
        ),
      );
}

class _MarketContextCard extends StatelessWidget {
  final TodayRead? market;
  final MultiTimeframeRead? timeframes;
  final ImpliedVolatilityRead? impliedVolatility;

  const _MarketContextCard({
    required this.market,
    required this.timeframes,
    required this.impliedVolatility,
  });

  @override
  Widget build(BuildContext context) => GlassPanel(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'CONTEXTE ACTUEL',
              style: TextStyle(
                color: mobileMuted,
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
            if (market != null) ...[
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  MobilePill(
                    label: _directionLabel(market!.summary.marketDirection),
                    color: mobileBlue,
                    dense: true,
                  ),
                  MobilePill(
                    label: market!.edgeState.label,
                    color: market!.edgeState.isMeasured
                        ? AppColors.measured
                        : AppColors.warn,
                    dense: true,
                  ),
                  MobilePill(
                    label:
                        'Volatilité ${_plainLabel(market!.volatilityRegime)}',
                    color: mobileBlue,
                    dense: true,
                  ),
                ],
              ),
            ],
            if (timeframes != null) ...[
              const SizedBox(height: 16),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text(
                    'UNITÉS DE TEMPS',
                    style: TextStyle(
                      color: mobileMuted,
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  Text(
                    timeframes!.alignmentLabel,
                    style: const TextStyle(
                      color: mobileBlue,
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 9),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final frame in timeframes!.timeframes)
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 11,
                        vertical: 8,
                      ),
                      decoration: BoxDecoration(
                        color: mobileBlue.withValues(alpha: .06),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                          color: mobileBlue.withValues(alpha: .55),
                        ),
                      ),
                      child: Text(
                        frame.available
                            ? '${frame.timeframe} · ${frame.structureLabel}'
                            : '${frame.timeframe} · indisponible',
                        style: const TextStyle(
                          color: mobileMuted,
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                ],
              ),
            ],
            if (impliedVolatility != null) ...[
              const SizedBox(height: 16),
              const Text(
                'VOLATILITÉ IMPLICITE',
                style: TextStyle(
                  color: mobileMuted,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 7),
              Text(
                impliedVolatility!.available
                    ? _impliedVolatilitySentence(impliedVolatility!)
                    : (impliedVolatility!.unavailableReason.isEmpty
                        ? 'Indisponible pour cet actif.'
                        : impliedVolatility!.unavailableReason),
                style: const TextStyle(color: mobileMuted, height: 1.35),
              ),
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
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    decision.coverage,
                    maxLines: 2,
                    textAlign: TextAlign.end,
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                ),
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

class _Scenarios extends StatelessWidget {
  final List<FutureScenarioRead> scenarios;
  final String horizon;

  const _Scenarios({required this.scenarios, required this.horizon});

  @override
  Widget build(BuildContext context) {
    final visible = scenarios.take(4).toList();
    return GlassPanel(
      borderColor: const Color(0xFF245E90),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text('◐',
                  style: TextStyle(color: mobileBlue, fontSize: 22)),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Scénarios (${_horizonLongLabel(horizon)})',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
              TextButton(
                key: const ValueKey('scenarios-see-details'),
                onPressed: () => _showScenarioDetails(
                  context,
                  scenarios,
                  horizon,
                ),
                style: TextButton.styleFrom(
                  foregroundColor: mobileBlue,
                  padding: const EdgeInsets.symmetric(horizontal: 2),
                  minimumSize: const Size(0, 36),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text('Voir détails'),
                    Icon(Icons.chevron_right_rounded, size: 19),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          LayoutBuilder(
            builder: (context, constraints) {
              final width = (constraints.maxWidth - 9) / 2;
              return Wrap(
                spacing: 9,
                runSpacing: 9,
                children: [
                  for (final scenario in visible)
                    SizedBox(
                      width: width,
                      child: _ScenarioTile(
                        scenario: scenario,
                        onTap: () => _showScenarioDetails(
                          context,
                          [scenario],
                          horizon,
                        ),
                      ),
                    ),
                ],
              );
            },
          ),
          if (visible.any((scenario) => scenario.probability == null)) ...[
            const SizedBox(height: 10),
            const Text(
              'Les pourcentages de probabilité ne sont pas affichés quand '
              'ils ne sont pas défendables. La confiance décrit uniquement '
              'la solidité du scénario.',
              style: TextStyle(
                color: AppColors.textMuted,
                fontSize: 10.5,
                height: 1.3,
                fontStyle: FontStyle.italic,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _ScenarioTile extends StatelessWidget {
  final FutureScenarioRead scenario;
  final VoidCallback? onTap;

  const _ScenarioTile({required this.scenario, this.onTap});

  @override
  Widget build(BuildContext context) {
    final tone = _scenarioColor(scenario);
    final headline = scenario.probability == null
        ? 'Confiance ${(scenario.confidence * 100).round()} %'
        : '${(scenario.probability! * 100).round()} %';
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(13),
        child: Container(
          constraints: const BoxConstraints(minHeight: 128),
          padding: const EdgeInsets.all(11),
          decoration: BoxDecoration(
            color: tone.withValues(alpha: .08),
            borderRadius: BorderRadius.circular(13),
            border: Border.all(color: tone.withValues(alpha: .55)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                _scenarioLabel(scenario.id),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: tone,
                  fontSize: 11,
                  fontWeight: FontWeight.w900,
                ),
              ),
              const SizedBox(height: 7),
              Text(
                headline,
                style: TextStyle(
                  color: tone,
                  fontSize: 17,
                  fontWeight: FontWeight.w900,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                '${_directionLabel(scenario.direction)} · '
                '${_movementLabel(scenario.movement)}',
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: mobileMuted,
                  fontSize: 10.5,
                  height: 1.25,
                ),
              ),
              if (scenario.eventChain.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(
                  _cleanExplanation(scenario.eventChain.first),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: AppColors.textMuted,
                    fontSize: 9.5,
                    height: 1.2,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

Future<void> _showScenarioDetails(
  BuildContext context,
  List<FutureScenarioRead> scenarios,
  String horizon,
) =>
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF061525),
      builder: (sheetContext) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: .68,
        maxChildSize: .92,
        builder: (context, controller) => SafeArea(
          top: false,
          child: ListView(
            controller: controller,
            padding: const EdgeInsets.fromLTRB(20, 18, 20, 28),
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      'Scénarios · ${_horizonLongLabel(horizon)}',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 21,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ),
                  IconButton(
                    tooltip: 'Fermer',
                    onPressed: () => Navigator.of(sheetContext).pop(),
                    icon: const Icon(Icons.close_rounded),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              for (final scenario in scenarios) ...[
                _ScenarioDetailCard(scenario: scenario),
                const SizedBox(height: 10),
              ],
            ],
          ),
        ),
      ),
    );

class _ScenarioDetailCard extends StatelessWidget {
  final FutureScenarioRead scenario;

  const _ScenarioDetailCard({required this.scenario});

  @override
  Widget build(BuildContext context) {
    final tone = _scenarioColor(scenario);
    final probability = scenario.probability == null
        ? 'Non défendable — confiance ${(scenario.confidence * 100).round()} %'
        : '${(scenario.probability! * 100).round()} %';
    return Container(
      padding: const EdgeInsets.all(15),
      decoration: BoxDecoration(
        color: tone.withValues(alpha: .08),
        borderRadius: BorderRadius.circular(15),
        border: Border.all(color: tone.withValues(alpha: .5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            _scenarioLabel(scenario.id),
            style: TextStyle(
              color: tone,
              fontSize: 16,
              fontWeight: FontWeight.w900,
            ),
          ),
          const SizedBox(height: 10),
          _DetailLine(label: 'Probabilité', value: probability),
          _DetailLine(
            label: 'Direction',
            value: _directionLabel(scenario.direction),
          ),
          _DetailLine(
            label: 'Mouvement',
            value: _movementLabel(scenario.movement),
          ),
          if (scenario.probabilitySource case final source?)
            _DetailLine(label: 'Méthode', value: source),
          if (scenario.eventChain.isNotEmpty) ...[
            const Text(
              'Chaîne d’événements',
              style: TextStyle(
                color: mobileMuted,
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 8),
            for (final event in scenario.eventChain)
              Padding(
                padding: const EdgeInsets.only(bottom: 7),
                child: Text(
                  '• ${_cleanExplanation(event)}',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 13,
                    height: 1.3,
                  ),
                ),
              ),
          ],
        ],
      ),
    );
  }
}

class _FutureBundle {
  final FutureDecisionRead decision;
  final FutureTimelineRead? timeline;
  final TodayRead? market;
  final MultiTimeframeRead? timeframes;
  final ImpliedVolatilityRead? impliedVolatility;

  const _FutureBundle({
    required this.decision,
    required this.timeline,
    required this.market,
    required this.timeframes,
    required this.impliedVolatility,
  });
}

/// What kind of thing a factor is. The three are never interchangeable.
///
/// A family such as "Macro & liquidité" is an analytical grouping, not an event
/// and not an observation. Rendering one as "Macro & liquidité — le 13 sept. à
/// 17h39" invented an event that does not exist; the date was the analysis
/// timestamp. Catalysts are dated things that will happen; signals are things
/// already measured now.
enum _FactorKind { futureCatalyst, currentSignal }

class _DecisionFactor {
  final _FactorKind kind;

  /// A concrete thing, never a family name: "Décision de la Fed — 16 sept.",
  /// "Sorties nettes des ETF", "Compression de Bollinger".
  final String title;
  final String description;
  final String? direction;
  final String impact;
  final String emoji;
  final String when;

  /// How well the engine could measure this factor, in [0, 1].
  final double confidence;

  /// IMPROVING / STABLE / DETERIORATING / REVERSING / UNKNOWN.
  final String trend;

  /// "NONE" when the reading cannot speak about direction at all.
  final String impactOnDirection;

  /// Catalyst only.
  final DateTime? scheduledAt;
  final String? marketExpectation;
  final String upsideCase;
  final String downsideCase;

  /// Signal only.
  final String observation;
  final String invalidation;

  final String whyItMatters;
  final String caveat;
  final String consequence;
  final String? source;
  final String? sourceUrl;

  const _DecisionFactor({
    required this.kind,
    required this.title,
    required this.description,
    required this.direction,
    required this.impact,
    required this.emoji,
    required this.when,
    required this.whyItMatters,
    this.confidence = 1.0,
    this.trend = 'UNKNOWN',
    this.impactOnDirection = 'MEASURED',
    required this.consequence,
    this.scheduledAt,
    this.marketExpectation,
    this.upsideCase = '',
    this.downsideCase = '',
    this.observation = '',
    this.invalidation = '',
    this.caveat = '',
    this.source,
    this.sourceUrl,
  });
}

/// Event titles arrive in English from the official calendars.
String _eventTitleFr(String title) {
  final value = title.toLowerCase();
  if (value.contains('fomc') || value.contains('monetary policy')) {
    return 'Décision de la Fed sur les taux';
  }
  if (value.contains('personal income')) {
    return 'Revenus et dépenses des ménages américains';
  }
  if (value.contains('gdp')) return 'PIB américain';
  if (value.contains('cpi') || value.contains('consumer price')) {
    return 'Inflation américaine';
  }
  if (value.contains('employment') || value.contains('nonfarm')) {
    return 'Emploi américain';
  }
  if (value.contains('treasury auction')) {
    final match = RegExp(r'(\d+)[- ](week|year|month)').firstMatch(value);
    if (match == null) return 'Adjudication du Trésor américain';
    final unit = switch (match.group(2)) {
      'week' => 'semaines',
      'month' => 'mois',
      _ => 'ans',
    };
    return 'Adjudication du Trésor américain '
        '(${match.group(1)} $unit)';
  }
  if (value.contains('vote') || value.contains('markup')) {
    return 'Vote réglementaire crypto';
  }
  return title;
}

/// Replace official English event names inside a free-text sentence.
///
/// The engine embeds the official title in its change conditions, which is the
/// right thing to store and the wrong thing to show: section 10 keeps English
/// names for the Source line only.
String _frenchifyEventNames(String text) {
  var result = text;
  for (final pattern in const [
    r'FOMC monetary policy decision[^»\n]*',
    r'Personal Income and Outlays[^»\n]*',
    r'GDP \(Third Estimate\)[^»\n]*',
    r'[\w-]+ (?:Bill|Bond|Note) Treasury auction',
  ]) {
    result = result.replaceAllMapped(
      RegExp(pattern),
      (match) => _eventTitleFr(match.group(0)!),
    );
  }
  return result;
}

/// Does this factor argue *for* the decision that was taken?
///
/// Waiting is supported by anything negative or unresolved; it is not supported
/// by a healthy bullish reading, which is precisely the counter-argument.
bool _supportsDecision(_DecisionFactor factor, FutureDecisionRead decision) {
  final positive = factor.direction?.contains('BULLISH') ?? false;
  final negative = factor.direction?.contains('BEARISH') ?? false;
  return switch (decision.decision) {
    'BUY' => positive,
    'SELL' => negative,
    'WAIT' => !positive,
    _ => true,
  };
}

/// Match a family to its normalised reading, when the engine published one.
FutureFactorRead? _factorFor(FutureDecisionRead decision, String familyId) {
  const mapping = {
    'flows_whales': 'flows',
    'positioning_derivatives': 'positioning',
    'technical_volatility': 'technical',
  };
  final key = mapping[familyId];
  if (key == null) return null;
  for (final factor in decision.factors) {
    if (factor.key == key) return factor;
  }
  return null;
}

/// UNKNOWN is kept distinct from NEUTRAL all the way to the badge.
String? _normalisedDirection(String direction) => switch (direction) {
      'POSITIVE' => 'BULLISH',
      'NEGATIVE' => 'BEARISH',
      'NEUTRAL' => 'NEUTRAL',
      _ => null,
    };

String _impactLabelFr(String impact) => switch (impact) {
      'VERY_HIGH' => 'TRÈS ÉLEVÉ',
      'HIGH' => 'ÉLEVÉ',
      'MODERATE' => 'MODÉRÉ',
      'LOW' => 'FAIBLE',
      _ => 'MODÉRÉ',
    };

String? _trendLabelFr(String trend) => switch (trend) {
      'IMPROVING' => 'EN AMÉLIORATION',
      'DETERIORATING' => 'EN DÉGRADATION',
      'REVERSING' => 'EN RETOURNEMENT',
      'STABLE' => 'STABLE',
      _ => null,
    };

String _importanceImpact(String importance) =>
    switch (importance.toUpperCase()) {
      'CRITICAL' => 'TRÈS ÉLEVÉ',
      'HIGH' => 'ÉLEVÉ',
      'MEDIUM' => 'MODÉRÉ',
      'LOW' => 'FAIBLE',
      _ => 'MODÉRÉ',
    };

String _movementImpact(String? movement) => switch (movement?.toUpperCase()) {
      'EXTREME' => 'TRÈS ÉLEVÉ',
      'HIGH' => 'ÉLEVÉ',
      'NORMAL' => 'MODÉRÉ',
      'LOW' => 'FAIBLE',
      _ => 'MODÉRÉ',
    };

/// Plain-language mechanism for one family of factors.
///
/// These texts explain *how* a factor transmits to the price. They carry no
/// measured value, so they never state anything the data has not established;
/// the measured part always comes from the decision payload next to them.
class _TopicGuidance {
  final String why;
  final String caveat;

  const _TopicGuidance(this.why, [this.caveat = '']);
}

const _TopicGuidance _guidanceFallback = _TopicGuidance(
  'Ce facteur fait partie des éléments suivis par l’analyse pour cet horizon.',
);

/// Guidance indexed by the factor's own key.
///
/// Keying on the title made "Flux institutionnels & baleines" match the whale
/// branch before the ETF branch, so an ETF reading was explained with on-chain
/// wording. A key cannot be ambiguous the way a sentence can.
const _guidanceByKey = <String, _TopicGuidance>{
  'flows': _TopicGuidance(
    'Les ETF au comptant constituent une source de demande ou d’offre nette. '
    'Des entrées persistantes apportent du soutien; des sorties persistantes '
    'réduisent ce soutien.',
    'Les flux sont publiés avec un jour de décalage: ils décrivent les séances '
    'déjà passées.',
  ),
  'whales': _TopicGuidance(
    'Les gros portefeuilles peuvent modifier l’offre disponible à la vente.',
    'Un transfert vers une plateforme ne signifie pas qu’une vente aura lieu.',
  ),
  'positioning': _TopicGuidance(
    'Quand les positions à levier se ferment pendant que le prix recule, des '
    'acheteurs abandonnent: cela confirme une faiblesse à court terme.',
    'Le levier amplifie les mouvements dans les deux sens.',
  ),
  'derivatives': _TopicGuidance(
    'Le positionnement à levier amplifie les mouvements en cours.',
    'Il décrit une exposition, pas une intention.',
  ),
  'funding': _TopicGuidance(
    'Le coût pour rester positionné indique quel côté du marché paie.',
    'Un coût très bas accompagne souvent un marché faible: ce n’est pas un '
    'signal d’achat en soi.',
  ),
  'spot': _TopicGuidance(
    'L’équilibre entre acheteurs et vendeurs au comptant montre qui accepte de '
    'payer le prix demandé maintenant.',
    'Cette lecture est immédiate et peut changer vite.',
  ),
  'technical': _TopicGuidance(
    'Quand plusieurs échelles de temps racontent la même histoire, la lecture '
    'est plus fiable que lorsqu’elles se contredisent.',
    'Une seule échelle concordante reste une lecture isolée.',
  ),
  'volatility': _TopicGuidance(
    'Une période de faible volatilité précède parfois un mouvement beaucoup '
    'plus important.',
    'Cette lecture n’indique jamais la direction du mouvement à venir.',
  ),
  'rates': _TopicGuidance(
    'Des rendements plus élevés resserrent les conditions financières et pèsent '
    'sur la valorisation des actifs risqués.',
    'Ce qui compte est le mouvement, pas seulement le niveau.',
  ),
  'energy': _TopicGuidance(
    'Une hausse rapide de l’énergie alimente l’inflation anticipée, ce qui rend '
    'une détente monétaire moins probable.',
    'Un niveau élevé mais stable est déjà intégré dans les anticipations.',
  ),
  'credit': _TopicGuidance(
    'Les écarts de crédit montrent ce que le marché exige pour prêter aux '
    'entreprises: ils confirment, ou non, qu’une baisse devient un stress.',
    'Tant que le crédit reste calme, une baisse reste une correction.',
  ),
  'regulation': _TopicGuidance(
    'Une décision réglementaire modifie qui peut acheter, vendre ou conserver '
    'l’actif, et à quelles conditions.',
    'Une étape de procédure n’est pas une loi adoptée.',
  ),
  'implied_volatility': _TopicGuidance(
    'Le marché des options chiffre l’ampleur du mouvement qu’il anticipe.',
    'L’ampleur attendue ne dit rien du sens.',
  ),
};

/// Guidance for one family, by identifier rather than by wording.
///
/// Falling back to a keyword search on the label was the original defect and it
/// came back the moment a family had no normalised factor: "Flux institutionnels
/// & baleines" matched the whale branch and an ETF reading was explained with
/// on-chain vocabulary. Identifiers cannot be ambiguous, so the family id is
/// tried before any text is inspected.
const _guidanceByFamily = <String, String>{
  'flows_whales': 'flows',
  'positioning_derivatives': 'positioning',
  'technical_volatility': 'technical',
  'macro_liquidity': 'rates',
  'catalysts_regulation': 'regulation',
};

_TopicGuidance _guidanceForFactor(
  FutureFactorRead? factor,
  String familyId,
  String fallbackTitle,
) {
  final byFactor = _guidanceByKey[factor?.key];
  if (byFactor != null) return byFactor;
  final byFamily = _guidanceByKey[_guidanceByFamily[familyId]];
  if (byFamily != null) return byFamily;
  return _topicGuidance(fallbackTitle);
}

_TopicGuidance _topicGuidance(String title) {
  final value = title.toLowerCase();
  if (value.contains('fed') ||
      value.contains('fomc') ||
      value.contains('macro') ||
      value.contains('taux') ||
      value.contains('liquidité')) {
    return const _TopicGuidance(
      'Des taux plus élevés rendent le crédit plus cher, ce qui réduit la '
          'liquidité disponible, donc l’appétit pour les actifs risqués, et peut '
          'peser sur les cryptomonnaies.',
      'Le sens dépend de l’écart avec ce qui était déjà anticipé, pas de la '
          'décision elle-même.',
    );
  }
  if (value.contains('baleine') || value.contains('whale')) {
    return const _TopicGuidance(
      'Davantage de crypto disponible sur les plateformes d’échange peut '
          'augmenter la pression vendeuse.',
      'Un transfert ne signifie pas automatiquement qu’une vente aura lieu.',
    );
  }
  if (value.contains('flux') ||
      value.contains('etf') ||
      value.contains('institution')) {
    return const _TopicGuidance(
      'Une demande institutionnelle plus faible réduit une source importante '
          'd’achat régulier.',
      'Les flux sont publiés avec un jour de décalage : ils décrivent les '
          'séances passées.',
    );
  }
  if (value.contains('dériv') ||
      value.contains('position') ||
      value.contains('levier') ||
      value.contains('intérêt ouvert')) {
    return const _TopicGuidance(
      'Quand les positions à levier se ferment pendant que le prix recule, '
          'des acheteurs abandonnent : cela confirme une faiblesse à court terme.',
      'Le levier amplifie les mouvements dans les deux sens.',
    );
  }
  if (value.contains('volatil') ||
      value.contains('technique') ||
      value.contains('bollinger')) {
    return const _TopicGuidance(
      'Une période de faible volatilité précède parfois un mouvement beaucoup '
          'plus important.',
      'Cette lecture n’indique jamais la direction du mouvement à venir.',
    );
  }
  if (value.contains('réglement') || value.contains('regulat')) {
    return const _TopicGuidance(
      'Une décision réglementaire modifie qui peut acheter, vendre ou '
      'conserver l’actif, et à quelles conditions.',
    );
  }
  if (value.contains('unité')) {
    return const _TopicGuidance(
      'Quand les différentes échelles de temps racontent la même histoire, la '
      'lecture est plus fiable que lorsqu’elles se contredisent.',
    );
  }
  return _guidanceFallback;
}

class _DecisionVisual {
  final String asset;
  final Color accent;
  final Color glow;
  final Color overlay;

  const _DecisionVisual({
    required this.asset,
    required this.accent,
    required this.glow,
    required this.overlay,
  });
}

_DecisionVisual _decisionVisual(String decision) => switch (decision) {
      'BUY' => const _DecisionVisual(
          asset: 'assets/visuals/opportunity_favorable.png',
          accent: Color(0xFF5CF29A),
          glow: Color(0xFF16E98A),
          overlay: Color(0xFF08794F),
        ),
      'WAIT' => const _DecisionVisual(
          asset: 'assets/visuals/opportunity_wait.png',
          accent: Color(0xFFFFD35C),
          glow: Color(0xFFFFB72E),
          overlay: Color(0xFF8F6512),
        ),
      'SELL' => const _DecisionVisual(
          asset: 'assets/visuals/opportunity_unfavorable.png',
          accent: Color(0xFFFF6676),
          glow: Color(0xFFFF2E43),
          overlay: Color(0xFF8E0D22),
        ),
      _ => const _DecisionVisual(
          asset: 'assets/visuals/opportunity_insufficient.png',
          accent: Color(0xFF72C8FF),
          glow: Color(0xFF168EFF),
          overlay: Color(0xFF0759A5),
        ),
    };

/// Build at most five reasons, ordered by how much they carry the decision.
///
/// The payload already lists the gate reason first and the family that actually
/// set the direction next, so payload order is kept; families only fill the
/// remaining slots. Timeframes and implied volatility are no longer pushed into
/// the summary - they live behind "Voir les détails".
/// Rank the future catalysts that sit inside the decision horizon.
///
/// The backend ships `family.reasons` with the first three macro events in
/// chronological order, which surfaced three Treasury bill auctions and buried
/// the FOMC. Ranking happens here on importance first, proximity second.
List<FutureEventRead> _rankedCatalysts(
  FutureDecisionRead decision,
  _FutureBundle bundle,
) {
  const rank = {'CRITICAL': 3, 'HIGH': 2, 'MEDIUM': 1, 'LOW': 0};
  final window = switch (decision.horizon) {
    '24h' => const Duration(hours: 24),
    '30d' => const Duration(days: 30),
    _ => const Duration(days: 7),
  };
  final events = [
    ...?bundle.timeline?.events,
    if (decision.nextEvent != null) decision.nextEvent!,
  ];
  final seen = <String>{};
  final inWindow = <FutureEventRead>[];
  for (final event in events) {
    if (!seen.add(event.id)) continue;
    final seconds = event.countdownSeconds;
    if (seconds == null || seconds < 0) continue;
    if (Duration(seconds: seconds) > window) continue;
    inWindow.add(event);
  }
  inWindow.sort((left, right) {
    final byRank = (rank[right.importance.toUpperCase()] ?? 0)
        .compareTo(rank[left.importance.toUpperCase()] ?? 0);
    if (byRank != 0) return byRank;
    return (left.countdownSeconds ?? 0).compareTo(right.countdownSeconds ?? 0);
  });
  return inWindow;
}

/// A concrete, readable name for what one family is currently measuring.
///
/// "Flux institutionnels & baleines" is the family; "Sorties nettes des ETF" is
/// what a reader can actually picture.
String? _signalTitle(FutureFamilyRead family) {
  final summary = family.summary.toLowerCase();
  final bearish = family.direction?.contains('BEARISH') ?? false;
  switch (family.id) {
    case 'flows_whales':
      if (summary.contains('inversé') || summary.contains('sorties')) {
        return bearish
            ? 'Sorties nettes des ETF'
            : 'Flux ETF en train de s’inverser';
      }
      return bearish ? 'Sorties nettes des ETF' : 'Entrées nettes sur les ETF';
    case 'positioning_derivatives':
      if (summary.contains('recule') || summary.contains('baisse')) {
        return 'Positions à levier en baisse';
      }
      return 'Positionnement sur les dérivés';
    case 'technical_volatility':
      if (summary.contains('compression')) return 'Compression de Bollinger';
      return bearish
          ? 'Tendance court terme fragile'
          : 'Tendance court terme porteuse';
    case 'catalysts_regulation':
      return 'Contexte réglementaire';
    case 'macro_liquidity':
      // Its content is the dated events, which are surfaced as catalysts. A
      // neutral macro family has nothing of its own to show the reader.
      return family.direction == null || family.direction == 'NEUTRAL'
          ? null
          : 'Conditions de liquidité';
  }
  return family.label;
}

/// Build three to five concrete causes: dated catalysts and measured signals.
List<_DecisionFactor> _decisionFactors(
  FutureDecisionRead decision,
  _FutureBundle bundle,
) {
  final factors = <_DecisionFactor>[];
  final horizon = _horizonLongLabel(decision.horizon);
  final asset = _assetName(decision.asset);

  for (final event in _rankedCatalysts(decision, bundle).take(3)) {
    final guidance = _topicGuidance(event.title);
    // Section 6: either the engine can explain the mechanism, or the event does
    // not belong among the main factors. An ordinary bill auction carries no
    // bid-to-cover or yield data here, so it stays in "À surveiller" instead of
    // displacing a catalyst that can actually be explained.
    if (identical(guidance, _guidanceFallback)) continue;
    if (factors.length >= 2) break;
    final title = _eventTitleFr(event.title);
    factors.add(_DecisionFactor(
      kind: _FactorKind.futureCatalyst,
      title: '$title — ${_dateShort(event.scheduledAt)}',
      description: 'Publication prévue ${_dateSentence(
        event.scheduledAt?.toIso8601String(),
      )}. Son issue n’est pas encore connue.',
      // An unresolved event has no direction until it lands. Claiming one would
      // mean deciding that a hike is bearish, which the engine refuses to do.
      direction: 'UNCERTAIN',
      impact: _importanceImpact(event.importance),
      emoji: _reasonEmoji(event.title),
      when: _dateShort(event.scheduledAt),
      scheduledAt: event.scheduledAt,
      marketExpectation: decision.marketExpectation,
      upsideCase: 'Une issue plus favorable qu’anticipé peut soutenir $asset.',
      downsideCase:
          'Une issue moins favorable qu’anticipé peut peser sur $asset.',
      whyItMatters: guidance.why,
      caveat: guidance.caveat,
      consequence: 'Mouvement possible dans les deux sens sur $horizon; '
          'la direction dépend de l’écart avec ce qui était anticipé.',
      source: event.source,
      sourceUrl: event.sourceUrl,
    ));
  }

  for (final family in decision.families) {
    if (factors.length >= 5) break;
    if (!family.available) continue;
    final title = _signalTitle(family);
    if (title == null) continue;
    final summary = _cleanExplanation(family.summary);
    // Prefer the normalised reading when the engine published one: it keeps
    // direction, impact and trend apart, where the family carries a bias and an
    // amplitude that the screen used to conflate.
    final normalised = _factorFor(decision, family.id);
    final guidance = _guidanceForFactor(normalised, family.id, family.label);
    factors.add(_DecisionFactor(
      kind: _FactorKind.currentSignal,
      title: title,
      description: summary,
      direction: normalised != null
          ? _normalisedDirection(normalised.direction)
          : family.direction,
      impact: normalised != null
          ? _impactLabelFr(normalised.impact)
          : _movementImpact(family.movement),
      emoji: _reasonEmoji('${family.label} $title'),
      when: 'ACTUEL',
      confidence: normalised?.confidence ?? family.confidence,
      trend: normalised?.trend ?? 'UNKNOWN',
      impactOnDirection: normalised?.impactOnDirection ?? 'MEASURED',
      observation: normalised?.rationale.isNotEmpty == true
          ? normalised!.rationale
          : summary,
      invalidation: _signalInvalidation(family),
      // The mechanism comes from the engine's causal chain. Deriving it in the
      // UI from a keyword in the title served whale wording for an ETF factor,
      // because the family label "Flux institutionnels & baleines" matched the
      // whale branch first.
      whyItMatters: normalised != null && normalised.causalChain.length >= 3
          ? normalised.causalChain.last
          : guidance.why,
      caveat: guidance.caveat,
      consequence: _signalConsequence(family, horizon, asset),
      // The real upstream provider, not the analytical family it belongs to.
      source: normalised?.provider.isNotEmpty == true
          ? normalised!.provider
          : family.label,
      sourceUrl: normalised?.sourceUrl,
    ));
  }

  // Section 7: order by contribution to the decision, not by date. An event
  // whose direction is unknown can still rank first when it dominates the risk.
  factors.sort((left, right) =>
      _contribution(right, decision).compareTo(_contribution(left, decision)));
  return factors.take(5).toList();
}

/// How much one factor weighs on this decision, in [0, 1].
///
/// Amplitude and relevance count for both kinds. A catalyst adds the risk it
/// injects, which is why an unknown direction can still rank first. A signal
/// adds whether it actually points the way the decision went.
double _contribution(_DecisionFactor factor, FutureDecisionRead decision) {
  const impactWeight = {
    'TRÈS ÉLEVÉ': 1.0,
    'ÉLEVÉ': 0.75,
    'MODÉRÉ': 0.45,
    'FAIBLE': 0.2,
  };
  var score = impactWeight[factor.impact] ?? 0.45;

  if (factor.kind == _FactorKind.futureCatalyst) {
    final seconds = factor.scheduledAt
        ?.difference(DateTime.now())
        .inSeconds
        .clamp(0, 1 << 30);
    final window = switch (decision.horizon) {
      '24h' => 86400,
      '30d' => 2592000,
      _ => 604800,
    };
    // Closer means more decisive: a catalyst at the far edge of the window has
    // most of the horizon before it, not after it.
    final proximity =
        seconds == null ? 0.5 : 1.0 - (seconds / window).clamp(0.0, 1.0);
    score *= 0.6 + 0.4 * proximity;
    // Unresolved outcome is itself a contribution: it is what makes the
    // decision fragile, even though it points neither way.
    if (decision.eventRiskActive) score += 0.25;
    return score.clamp(0.0, 1.0);
  }

  final aligned = switch (decision.decision) {
    'BUY' => factor.direction?.contains('BULLISH') ?? false,
    'SELL' => factor.direction?.contains('BEARISH') ?? false,
    _ => false,
  };
  if (aligned) score += 0.2;
  // A reading with no measured direction contributes amplitude only.
  if (factor.direction == null || factor.direction == 'NEUTRAL') score *= 0.6;
  // Data quality is part of the contribution: a family the engine could barely
  // measure must not outrank an unresolved Tier-1 event.
  score *= 0.45 + 0.55 * factor.confidence.clamp(0.0, 1.0);
  return score.clamp(0.0, 1.0);
}

String _signalConsequence(
  FutureFamilyRead family,
  String horizon,
  String asset,
) {
  if (family.id == 'technical_volatility' &&
      family.summary.toLowerCase().contains('compression')) {
    return 'Mouvement potentiellement important sur $horizon, '
        'direction actuellement incertaine.';
  }
  return switch (family.direction?.toUpperCase()) {
    'STRONGLY_BULLISH' ||
    'BULLISH' =>
      'Soutien à la hausse pour $asset sur $horizon.',
    'BEARISH' ||
    'STRONGLY_BEARISH' =>
      'Pression à la baisse pour $asset sur $horizon.',
    _ => 'Pas d’effet directionnel mesuré sur $horizon.',
  };
}

String _signalInvalidation(FutureFamilyRead family) => switch (family.id) {
      'flows_whales' =>
        'Un retour durable des flux dans le sens inverse sur plusieurs séances.',
      'positioning_derivatives' =>
        'Une reprise durable des positions à levier accompagnée d’une reprise '
            'du prix.',
      'technical_volatility' =>
        'Une sortie de compression, qui donnerait enfin une direction.',
      'macro_liquidity' =>
        'Un changement des conditions de liquidité mesuré sur les séries '
            'officielles.',
      _ => 'Une donnée nouvelle qui renverserait cette lecture.',
    };

/// Short date badge: "16 sept.".
String _dateShort(DateTime? value) {
  if (value == null) return 'à venir';
  final local = value.toLocal();
  return '${local.day} ${_monthLabel(local).toLowerCase()}';
}

/// Turn an ISO timestamp into a readable French sentence fragment.
String _dateSentence(String? value) {
  final parsed = value == null ? null : DateTime.tryParse(value)?.toLocal();
  if (parsed == null) return 'à une date non planifiée';
  final month = _monthLabel(parsed).toLowerCase().replaceAll('.', '');
  return 'le ${parsed.day} $month à '
      '${parsed.hour.toString().padLeft(2, '0')} h '
      '${parsed.minute.toString().padLeft(2, '0')}';
}

List<String> _decisionRisks(FutureDecisionRead decision) {
  final risks = <String>[];
  void add(String value) {
    final cleaned = value.trim();
    if (cleaned.isNotEmpty && !risks.contains(cleaned)) risks.add(cleaned);
  }

  if (decision.eventRisk == 'HIGH' || decision.eventRisk == 'CRITICAL') {
    final event = decision.nextEvent;
    add(event == null
        ? 'Risque événementiel ${_impactLabel(decision.eventRisk).toLowerCase()}.'
        : '${_eventTitleFr(event.title)} : risque événementiel '
            '${_impactLabel(decision.eventRisk).toLowerCase()}.');
  }
  for (final signal in decision.counterSignals) {
    add(signal.explanation);
  }
  for (final family in decision.families) {
    if (family.direction == 'BEARISH' ||
        family.direction == 'STRONGLY_BEARISH') {
      add(family.summary);
    }
  }
  return risks.take(4).toList();
}

/// One concrete sentence under the decision word.
///
/// It used to echo the first payload reason, which on the macro family reads
/// "8 événement(s) macro/monétaire sourcé(s) dans la fenêtre." - a count of
/// rows, not something a reader can act on. It now names the single factor that
/// weighs most, or falls back to the reading itself.
String _decisionHeadline(FutureDecisionRead decision, _FutureBundle bundle) {
  final factors = _decisionFactors(decision, bundle);
  if (factors.isNotEmpty) {
    final top = factors.first;
    return top.kind == _FactorKind.futureCatalyst
        ? '${top.title} · issue encore inconnue.'
        : '${top.title} · ${_reasonImpactLabel(top.direction).toLowerCase()}.';
  }
  return '${_directionLabel(decision.direction)} · amplitude '
      '${_movementLabel(decision.movement).toLowerCase()}.';
}

String _assetName(String asset) => switch (asset) {
      'BTC' => 'Bitcoin',
      'ETH' => 'Ethereum',
      'SOL' => 'Solana',
      _ => asset,
    };

String _plainLabel(String value) => value
    .toLowerCase()
    .replaceAll('_', ' ')
    .replaceFirstMapped(RegExp(r'^.'), (match) => match[0]!.toUpperCase());

String _impliedVolatilitySentence(ImpliedVolatilityRead read) {
  final dvol = read.dvol?.toStringAsFixed(1) ?? '—';
  final realised = read.realisedVolAnnualised?.toStringAsFixed(1) ?? '—';
  final premium = read.variancePremium;
  final premiumLabel = premium == null
      ? 'prime indisponible'
      : 'prime ${premium >= 0 ? '+' : ''}${premium.toStringAsFixed(1)} pts';
  return 'DVOL $dvol contre $realised réalisé · $premiumLabel · '
      'options ${read.pricingLabel}.';
}

String _decisionLabel(String value) => switch (value) {
      'BUY' => 'ACHETER',
      'WAIT' => 'ATTENDRE',
      'SELL' => 'VENDRE',
      _ => 'DONNÉES INSUFFISANTES',
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

String _horizonLabel(String value) => switch (value) {
      '24h' => '24 h',
      '7d' => '7 j',
      '30d' => '30 j',
      _ => value,
    };

String _horizonLongLabel(String value) => switch (value) {
      '24h' => '24 heures',
      '7d' => '7 jours',
      '30d' => '30 jours',
      _ => value,
    };

String _movementLabel(String value) => switch (value.toUpperCase()) {
      'EXTREME' => 'EXTRÊME',
      'HIGH' => 'FORTE',
      'NORMAL' => 'NORMALE',
      'LOW' => 'FAIBLE',
      _ => _plainLabel(value).toUpperCase(),
    };

/// Risk is its own four-step scale; it is not the event-importance scale.
String _riskLevelLabel(String? value) => switch (value?.toUpperCase()) {
      'EXTREME' => 'CRITIQUE',
      'HIGH' => 'ÉLEVÉ',
      'MODERATE' || 'MEDIUM' => 'MODÉRÉ',
      'LOW' => 'FAIBLE',
      _ => 'INDISPONIBLE',
    };

/// Amplitude of the move. It says how much, never which way.
String _expectedMovementLabel(String? value) => switch (value?.toUpperCase()) {
      'EXTREME' => 'EXTRÊME',
      'HIGH' => 'ÉLEVÉ',
      'NORMAL' => 'NORMAL',
      'LOW' => 'FAIBLE',
      _ => 'INDISPONIBLE',
    };

/// Confidence is shown as a coarse level, never as a percentage.
///
/// The backend figure is a coverage-weighted average of family confidences. It
/// has never been calibrated against outcomes, so rendering it as "56 %" claims
/// a precision that does not exist. Three buckets carry what the number can
/// honestly support.
String _confidenceLevelLabel(double? value) {
  if (value == null) return 'INDISPONIBLE';
  if (value >= 0.66) return 'ÉLEVÉE';
  if (value >= 0.40) return 'MOYENNE';
  return 'FAIBLE';
}

/// Impact is the direction a factor pushes, not how large the move may be.
///
/// The previous badge reused the event-importance scale (CRITIQUE/ÉLEVÉ), which
/// answered "how big" under a label that promised "which way".
String _reasonImpactLabel(String? direction) =>
    switch (direction?.toUpperCase()) {
      'STRONGLY_BULLISH' => 'FORTEMENT POSITIF',
      'BULLISH' => 'POSITIF',
      'BEARISH' => 'NÉGATIF',
      'STRONGLY_BEARISH' => 'FORTEMENT NÉGATIF',
      'NEUTRAL' => 'NEUTRE',
      _ => 'DIRECTION INCONNUE',
    };

Color _reasonImpactColor(String? direction) =>
    switch (direction?.toUpperCase()) {
      'STRONGLY_BULLISH' || 'BULLISH' => const Color(0xFF55DD8B),
      'BEARISH' || 'STRONGLY_BEARISH' => const Color(0xFFFF6676),
      'NEUTRAL' => const Color(0xFF94A8C2),
      _ => const Color(0xFF94A8C2),
    };

String _impactLabel(String? value) => switch (value?.toUpperCase()) {
      'CRITICAL' => 'CRITIQUE',
      'HIGH' => 'ÉLEVÉ',
      'MEDIUM' || 'NORMAL' => 'MODÉRÉ',
      'LOW' => 'FAIBLE',
      _ => 'À SUIVRE',
    };

Color _impactColor(String? value) => switch (value?.toUpperCase()) {
      'CRITICAL' || 'HIGH' => const Color(0xFFFF6676),
      'MEDIUM' || 'NORMAL' => const Color(0xFFFFB34F),
      'LOW' => mobileBlue,
      _ => const Color(0xFF94A8C2),
    };

Color _reasonTone(int index) => switch (index) {
      0 => const Color(0xFFE14D59),
      1 => const Color(0xFFF27C36),
      2 || 3 => const Color(0xFFEBAA32),
      _ => const Color(0xFF4D9CF2),
    };

String _reasonEmoji(String title) {
  final value = title.toLowerCase();
  if (value.contains('macro') ||
      value.contains('fed') ||
      value.contains('fomc') ||
      value.contains('taux') ||
      value.contains('trésor') ||
      value.contains('treasury') ||
      value.contains('pib') ||
      value.contains('gdp') ||
      value.contains('liquidité')) {
    return '🏦';
  }
  if (value.contains('inflation') || value.contains('cpi')) return '📉';
  if (value.contains('revenus') || value.contains('emploi')) return '👥';
  if (value.contains('pétrole') || value.contains('inflation')) return '🛢️';
  if (value.contains('baleine') || value.contains('whale')) return '🐋';
  if (value.contains('flux') ||
      value.contains('etf') ||
      value.contains('institution')) {
    return '📈';
  }
  if (value.contains('dériv') ||
      value.contains('position') ||
      value.contains('levier')) {
    return '🪙';
  }
  if (value.contains('volatil') || value.contains('technique')) return '📊';
  if (value.contains('réglement') || value.contains('regulat')) return '⚖️';
  return '🔎';
}

/// Turn engine wording into plain French for the summary.
///
/// The technical values are not lost: they stay visible in "Voir les détails".
/// What is removed here is vocabulary the reader cannot act on - percentile
/// ranks, index names and raw flags that read as noise on the main page.
String _cleanExplanation(String value) {
  var cleaned = value
      .replaceAllMapped(
        RegExp(r'Structure \w+\s*:?\s*haussière sur (\d+) unité\(s\),?\s*'
            r'baissière sur (\d+)'),
        (match) => 'Tendance haussière sur ${match.group(1)} échelle(s) de '
            'temps contre ${match.group(2)}',
      )
      .replaceAllMapped(
        RegExp(r'\bp(\d{1,3})\b'),
        (match) => 'niveau ${match.group(1)} sur 100 de son historique',
      )
      .replaceAllMapped(
        RegExp(r'(\d{1,3})(?:e|th|ème)? percentile'),
        (match) => 'niveau ${match.group(1)} sur 100 de son historique',
      )
      .replaceAll('traversent le spread', 'acceptent de payer le prix demandé')
      .replaceAll('spread crossing', 'ordres qui paient le prix demandé')
      .replaceAll("L'open interest", 'Le nombre de positions à levier')
      .replaceAll('open interest', 'positions à levier ouvertes')
      .replaceAll('upper third', 'tiers haut de sa zone')
      .replaceAll('mid range', 'milieu de sa zone')
      .replaceAll('des longs sortent', 'des acheteurs ferment leurs positions')
      .replaceAll('DVOL', 'volatilité attendue par le marché des options')
      .replaceAll('basis', 'écart au comptant')
      .replaceAll('edge mesurable', 'avantage statistique démontré')
      .replaceAll('strong_inflow', 'entrées nettes fortes')
      .replaceAll('strong_outflow', 'sorties nettes fortes')
      .replaceAll('inflow', 'entrées nettes')
      .replaceAll('outflow', 'sorties nettes')
      .replaceAll('Bollinger squeeze=True', 'compression de Bollinger active')
      .replaceAll('Bollinger squeeze=False', 'pas de compression de Bollinger')
      .replaceAll('volatilité very_low', 'volatilité très faible')
      .replaceAll('volatilité low', 'volatilité faible')
      .replaceAll(';', ' ')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();
  cleaned = cleaned.replaceAllMapped(
    RegExp(r'(-?\d+\.\d{2})\d+'),
    (match) => match.group(1)!,
  );
  return cleaned;
}

String _priceLabel(double? price, String? unit) {
  if (price == null) return 'Prix indisponible';
  final parts = price.toStringAsFixed(price >= 1000 ? 2 : 2).split('.');
  final digits = parts.first;
  final buffer = StringBuffer();
  for (var index = 0; index < digits.length; index++) {
    if (index > 0 && (digits.length - index) % 3 == 0) buffer.write(' ');
    buffer.write(digits[index]);
  }
  final number = '$buffer,${parts.last}';
  return unit == 'USD' ? r'$' '$number' : '$number €';
}

String _changeLabel(double? value) {
  if (value == null) return '—';
  final sign = value > 0 ? '+' : '';
  return '$sign${value.toStringAsFixed(2).replaceAll('.', ',')} %';
}

String _dateCompact(DateTime? value) {
  if (value == null) return 'indisponible';
  final local = value.toLocal();
  return '${local.day.toString().padLeft(2, '0')}/'
      '${local.month.toString().padLeft(2, '0')}/'
      '${local.year} '
      '${local.hour.toString().padLeft(2, '0')}:'
      '${local.minute.toString().padLeft(2, '0')}';
}

String _monthLabel(DateTime? value) {
  const months = [
    'JANV.',
    'FÉVR.',
    'MARS',
    'AVR.',
    'MAI',
    'JUIN',
    'JUIL.',
    'AOÛT',
    'SEPT.',
    'OCT.',
    'NOV.',
    'DÉC.',
  ];
  if (value == null) return 'DATE';
  return months[value.month - 1];
}

Color _scenarioColor(FutureScenarioRead scenario) {
  if (scenario.id == 'bullish_case' || scenario.direction.contains('BULLISH')) {
    return const Color(0xFF55DD8B);
  }
  if (scenario.id == 'bearish_case' ||
      scenario.id == 'tail_risk_case' ||
      scenario.direction.contains('BEARISH')) {
    return const Color(0xFFFF6676);
  }
  return mobileBlue;
}

String _countdown(int? seconds) {
  if (seconds == null) return 'non planifié';
  final hours = seconds < 0 ? 0 : seconds ~/ 3600;
  return hours < 48 ? 'dans $hours h' : 'dans ${hours ~/ 24} j';
}
