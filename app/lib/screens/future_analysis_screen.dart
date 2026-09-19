/// Future-first analysis for BTC, ETH and SOL.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/future_models.dart';
import '../api/models.dart';
import '../live_prices/live_price_service.dart';
import '../theme/app_theme.dart';
import 'cycle_page.dart';
import '../widgets/color_emoji.dart';
import '../widgets/live_price_builder.dart';
import '../widgets/mobile_kit.dart';
import 'full_analysis_page.dart';

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

  /// The full analysis page: the gated decision, the six families and their
  /// measures. The older scenario sheet stays one tap further.
  void _openFullAnalysis(FutureDecisionRead decision, _FutureBundle bundle) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        settings: RouteSettings(name: '/${_asset.toLowerCase()}/analysis'),
        builder: (_) => FullAnalysisPage(
          client: widget.client,
          asset: _asset,
          initialHorizon: _horizon,
          livePrices: widget.livePrices,
          fallbackPrice: bundle.market?.marketData?.displayPrice,
          fallbackChange24h: bundle.market?.marketData?.change24hPct,
          onTechnicalDetails: () => _showFullDetails(decision, bundle),
        ),
      ),
    );
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
          final reasons = _homeReasons(decision, bundle, limit: null);
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
                    if (index > 0)
                      const Divider(height: 1, color: Color(0xFF1D3853)),
                    _ReasonRow(index: index, reason: reasons[index]),
                  ],
                  const SizedBox(height: 16),
                  // The home no longer carries a button to the full analysis -
                  // it is not one of the three questions the page answers. The
                  // scenarios, the per-timeframe reading, implied volatility
                  // and the five families are still all here, now one level
                  // down instead of on the front page.
                  _SeeDetailsButton(
                    onTap: () {
                      Navigator.of(sheetContext).pop();
                      _showFullDetails(decision, bundle);
                    },
                  ),
                ],
              ),
            ),
          );
        },
      );

  void _showDecisionDetails(
    FutureDecisionRead decision,
    _FutureBundle bundle,
  ) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        settings: RouteSettings(name: '/${_asset.toLowerCase()}/decision'),
        builder: (_) => _DecisionDetailPage(
          asset: _asset,
          decision: decision,
          bundle: bundle,
          horizon: _horizon,
        ),
      ),
    );
  }

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
                  onTap: () => _showDecisionDetails(decision, bundle),
                ),
                const SizedBox(height: 14),
                if (decision.analysis != null) ...[
                  // The gated six-family decision: why, with figures, then
                  // the factors that actually move it - one tap from the full
                  // analysis.
                  _AnalysisExplanationCard(
                    decision: decision,
                    analysis: decision.analysis!,
                  ),
                  const SizedBox(height: 14),
                  _AnalysisFactorsCard(
                    analysis: decision.analysis!,
                    asset: _asset,
                    client: widget.client,
                    onSeeAnalysis: () => _openFullAnalysis(decision, bundle),
                  ),
                ] else if (decision.hierarchy != null) ...[
                  // Cause -> consequence -> decision, from the engine's own
                  // ranking. The flat list of readings it replaces gave a
                  // short-term trend the same room as a Fed decision.
                  _ExplanationCard(
                    decision: decision,
                    hierarchy: decision.hierarchy!,
                  ),
                  const SizedBox(height: 14),
                  _MainFactorsCard(
                    hierarchy: decision.hierarchy!,
                    onSeeAnalysis: () => _showFullDetails(decision, bundle),
                  ),
                ] else ...[
                  _WhaleIndicator(decision: decision),
                  const SizedBox(height: 14),
                  _WhyDecisionCard(
                    decision: decision,
                    bundle: bundle,
                    onSeeAll: () => _showReasonDetails(decision, bundle),
                  ),
                  const SizedBox(height: 14),
                  _ChangeAndRiskSection(decision: decision),
                ],
                const SizedBox(height: 14),
                _UpcomingEventsCard(
                  events: bundle.timeline?.events ?? const [],
                  // An event already listed among the main factors is not
                  // repeated in the calendar as a second, thinner copy.
                  skipIds: {
                    for (final item
                        in decision.hierarchy?.homeFactors ?? const <FutureDriverRead>[])
                      item.id,
                  },
                  alreadyShown: decision.hierarchy != null
                      ? const {}
                      : _decisionFactors(decision, bundle)
                          .where(
                            (item) => item.kind == _FactorKind.futureCatalyst,
                          )
                          .map((item) => item.title.split(' — ').first)
                          .toSet(),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

/// Focused decision route opened from the hero card. It deliberately lives in
/// the asset tab's nested navigator so the BTC/ETH/SOL/Graphique bar remains
/// available while the reader explores the full synthesis.
class _DecisionDetailPage extends StatelessWidget {
  final String asset;
  final FutureDecisionRead decision;
  final _FutureBundle bundle;
  final String horizon;

  const _DecisionDetailPage({
    required this.asset,
    required this.decision,
    required this.bundle,
    required this.horizon,
  });

  @override
  Widget build(BuildContext context) {
    final synthesis = decision.synthesis;
    return _FutureVisualFrame(
      asset: asset,
      child: MobileScrollView(
        padding: const EdgeInsets.fromLTRB(18, 10, 18, 170),
        children: [
          Row(
            children: [
              IconButton.filledTonal(
                key: const ValueKey('decision-detail-back'),
                tooltip: 'Retour',
                onPressed: () => Navigator.of(context).pop(),
                icon: const Icon(Icons.arrow_back_rounded),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Analyse complète · ${_assetName(asset)}',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          _DecisionCard(
            decision: decision,
            bundle: bundle,
            horizon: horizon,
          ),
          if (synthesis != null) ...[
            const SizedBox(height: 12),
            _MarketStateCard(synthesis: synthesis),
            const SizedBox(height: 12),
            _EvidenceListCard(
              key: const ValueKey('why-now-card'),
              emoji: '⚠️',
              title: 'POURQUOI MAINTENANT ?',
              tone: const Color(0xFFFFB34F),
              items: synthesis.whyNow,
              emptyText: 'Aucun facteur défavorable mesuré.',
            ),
            const SizedBox(height: 12),
            _EvidenceListCard(
              key: const ValueKey('counter-evidence-card'),
              emoji: '🛡️',
              title: 'POURQUOI CE N’EST PAS ENCORE CONFIRMÉ',
              tone: const Color(0xFF55DD8B),
              items: synthesis.counterEvidence,
            ),
            if (synthesis.upcomingEvents.isNotEmpty) ...[
              const SizedBox(height: 12),
              _CatalystListCard(events: synthesis.upcomingEvents),
            ],
            const SizedBox(height: 12),
            _ConditionListCard(
              key: const ValueKey('confirmation-card'),
              emoji: '🚨',
              title: 'CE QUI CONFIRMERAIT',
              tone: const Color(0xFFFF6676),
              conditions: synthesis.confirmationConditions,
              counter: synthesis.confirmationMet,
            ),
            const SizedBox(height: 12),
            _ConditionListCard(
              key: const ValueKey('invalidation-card'),
              emoji: '🟢',
              title: 'CE QUI INVALIDERAIT',
              tone: const Color(0xFF55DD8B),
              conditions: synthesis.invalidationConditions,
            ),
            const SizedBox(height: 12),
            _ScenarioPairCard(synthesis: synthesis),
          ] else ...[
            const SizedBox(height: 12),
            const GlassPanel(
              borderColor: Color(0xFF24506F),
              child: Text(
                'La synthèse détaillée est momentanément indisponible.',
                style: TextStyle(color: mobileMuted, fontSize: 13),
              ),
            ),
          ],
        ],
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
  final VoidCallback? onHorizonTap;
  final VoidCallback? onTap;

  const _DecisionCard({
    required this.decision,
    required this.bundle,
    required this.horizon,
    this.onHorizonTap,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final visual = _decisionVisual(decision.decision);
    return Semantics(
      button: onTap != null,
      label: onTap == null ? null : 'Ouvrir l’analyse complète',
      child: GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: ClipRRect(
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
                      constraints: const BoxConstraints(maxWidth: 322),
                      child: Text(
                        _heroSentence(decision, bundle),
                        maxLines: 3,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: Color(0xFFF4F8FF),
                          fontSize: 14.5,
                          height: 1.25,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                    const Spacer(),
                    Row(
                      children: [
                        Expanded(
                          child: Builder(builder: (context) {
                            // Risk is how badly it could go wrong - leverage,
                            // implied volatility, events - never the trend.
                            final risk = decision.analysis?.summary.risk;
                            final known = risk != null && !risk.isEmpty;
                            return _DecisionMetric(
                              key: const ValueKey('decision-risk'),
                              emoji: '⚠️',
                              label: 'Risque',
                              value: known
                                  ? risk.label
                                  : _riskLabelShort(decision.eventRisk),
                              tone: known
                                  ? _toneColor(risk.tone)
                                  : _impactColor(decision.eventRisk),
                            );
                          }),
                        ),
                        const SizedBox(width: 6),
                        Expanded(
                          child: _DecisionMetric(
                            key: const ValueKey('decision-horizon'),
                            emoji: '⏱️',
                            label: 'Horizon',
                            value: _horizonLongLabel(horizon),
                            tone: mobileBlue,
                            onTap: onHorizonTap,
                          ),
                        ),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Builder(builder: (context) {
                            // Amplitude and confidence used to sit here. Both
                            // describe how the model feels rather than what
                            // the market is doing; the balance of measured
                            // signals is what the verdict actually rests on.
                            // It is the hierarchy's reading, so the tile can
                            // never disagree with the reasoning beneath it.
                            final analysis = decision.analysis;
                            final trend = analysis?.summary.trend;
                            if (trend != null && !trend.isEmpty) {
                              // The direction only. Whether now is a good
                              // entry is a separate question, answered below.
                              return _DecisionMetric(
                                key: const ValueKey('decision-signals'),
                                emoji: trend.emoji.isEmpty ? '📊' : trend.emoji,
                                label: 'Tendance',
                                value: trend.label,
                                tone: switch (trend.label) {
                                  'Haussière' => _badgeGood,
                                  'Baissière' => _badgeBad,
                                  _ => _badgeWatch,
                                },
                              );
                            }
                            final reading = analysis != null
                                ? (analysis.blockingGate == 'CONTRADICTION'
                                    ? 'MIXED'
                                    : (analysis.score ?? 0) >= 15
                                        ? 'POSITIVE'
                                        : (analysis.score ?? 0) <= -15
                                            ? 'NEGATIVE'
                                            : analysis.score == null
                                                ? 'UNKNOWN'
                                                : 'NEUTRAL')
                                : decision.hierarchy?.reading;
                            final signals = reading == null
                                ? _signalsLabel(_decisionFactors(decision, bundle))
                                : switch (reading) {
                                    'POSITIVE' => 'Favorables',
                                    'NEGATIVE' => 'Défavorables',
                                    'MIXED' => 'Mitigés',
                                    'NEUTRAL' => 'Neutres',
                                    _ => 'Insuffisants',
                                  };
                            return _DecisionMetric(
                              key: const ValueKey('decision-signals'),
                              emoji: '📊',
                              label: 'Tendance',
                              value: _tendencyLabel(signals),
                              tone: _signalsTone(signals),
                            );
                          }),
                        ),
                      ],
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
}

class _DecisionMetric extends StatelessWidget {
  final String emoji;
  final String label;
  final String value;
  final Color tone;
  final VoidCallback? onTap;

  const _DecisionMetric({
    super.key,
    required this.emoji,
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
          borderRadius: BorderRadius.circular(14),
          child: Container(
            height: 64,
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
            decoration: BoxDecoration(
              color: const Color(0xC20A1726),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: const Color(0xFF314861)),
            ),
            child: Row(
              children: [
                ColorEmoji(emoji: emoji, size: 17),
                const SizedBox(width: 6),
                Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        label,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: Color(0xFFB7C6DC),
                          fontSize: 10,
                        ),
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
                            fontSize: 14,
                            fontWeight: FontWeight.w700,
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
    // One list, ordered by how much each factor weighs on the verdict. The
    // supporting and opposing reasons used to be split under two headings,
    // which cost a whole extra section for something each row's badge already
    // says: green argues one way, red the other, amber is still waiting on an
    // outcome. Seeing them interleaved is what makes a mixed verdict legible.
    final reasons = _homeReasons(decision, bundle);
    return GlassPanel(
      borderColor: const Color(0xFF2B669B),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: _SectionTitle(
                  emoji: '🤔',
                  text: switch (decision.decision) {
                    'BUY' => 'Pourquoi acheter ?',
                    'SELL' => 'Pourquoi vendre ?',
                    _ => 'Pourquoi attendre ?',
                  },
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
          const SizedBox(height: 4),
          if (reasons.isEmpty)
            const Padding(
              // Section 12: two real reasons beat six weak ones, and none at
              // all is a legitimate answer. Inventing filler would be worse
              // than an empty section.
              padding: EdgeInsets.symmetric(vertical: 10),
              child: Text(
                'Pas de catalyseur majeur immédiat.',
                key: ValueKey('why-empty'),
                style: TextStyle(color: mobileMuted, fontSize: 13),
              ),
            )
          else
            for (var index = 0; index < reasons.length; index++) ...[
              if (index > 0) const Divider(height: 1, color: Color(0xFF1D3853)),
              _ReasonRow(index: index, reason: reasons[index]),
            ],
        ],
      ),
    );
  }
}

/// The hero names the one thing that matters most, not a generic mood.
String _heroSentence(FutureDecisionRead decision, _FutureBundle bundle) {
  final analysis = decision.analysis;
  if (analysis != null && analysis.summary.sentence.isNotEmpty) {
    return analysis.summary.sentence;
  }
  if (analysis != null && analysis.subtitle.isNotEmpty) {
    return '${analysis.subtitle}.';
  }
  final primary = decision.hierarchy?.primary;
  if (primary == null) {
    return _verdictSentence(decision, _decisionFactors(decision, bundle));
  }
  return 'Facteur principal : ${primary.title} — '
      '${primary.status[0].toLowerCase()}${primary.status.substring(1)}.';
}

/// 🔴 🟠 🟡 🟢 ⚪ - the colour of a status, as a real emoji.
String _toneEmoji(String tone) => switch (tone) {
      'RED' => '🔴',
      'ORANGE' => '🟠',
      'YELLOW' => '🟡',
      'GREEN' => '🟢',
      // U+FE0F asks for the colour form; without it ⚪ can render as text.
      _ => '⚪️',
    };

Color _toneColor(String tone) => switch (tone) {
      'RED' => _badgeBad,
      'ORANGE' => const Color(0xFFFF9A4D),
      'YELLOW' => _badgeWatch,
      'GREEN' => _badgeGood,
      _ => mobileMuted,
    };

/// The reasoning under the verdict: four or five lines, each a cause and what
/// it does, ending on what the decision waits for. Written by the engine from
/// the ranked drivers; the screen only lays it out.
class _ExplanationCard extends StatelessWidget {
  final FutureDecisionRead decision;
  final FutureHierarchyRead hierarchy;

  const _ExplanationCard({required this.decision, required this.hierarchy});

  @override
  Widget build(BuildContext context) => GlassPanel(
        key: const ValueKey('decision-explanation'),
        borderColor: const Color(0xFF2B669B),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _SectionTitle(
              emoji: '🔎',
              text: switch (decision.decision) {
                'BUY' => 'Pourquoi acheter ?',
                'SELL' => 'Pourquoi vendre ?',
                'INSUFFICIENT_DATA' => 'Pourquoi pas de recommandation ?',
                _ => 'Pourquoi attendre ?',
              },
            ),
            const SizedBox(height: 10),
            for (final line in hierarchy.explanation) ...[
              Text(
                line,
                style: const TextStyle(
                  color: Color(0xFFE6EEF9),
                  fontSize: 14,
                  height: 1.4,
                ),
              ),
              const SizedBox(height: 7),
            ],
          ],
        ),
      );
}

/// The few drivers that weigh most right now, primary first. Each keeps one
/// status line; everything else about it is one tap away.
class _MainFactorsCard extends StatelessWidget {
  final FutureHierarchyRead hierarchy;
  final VoidCallback onSeeAnalysis;

  const _MainFactorsCard({required this.hierarchy, required this.onSeeAnalysis});

  @override
  Widget build(BuildContext context) {
    final factors = hierarchy.homeFactors;
    final whaleListed = factors.any((item) => item.key == 'whales');
    return GlassPanel(
      key: const ValueKey('main-factors'),
      borderColor: const Color(0xFF245E90),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _SectionTitle(emoji: '📌', text: 'Facteurs principaux'),
          const SizedBox(height: 4),
          if (factors.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 10),
              child: Text(
                'Aucun facteur ne se détache nettement en ce moment.',
                style: TextStyle(color: mobileMuted, fontSize: 13),
              ),
            ),
          for (var index = 0; index < factors.length; index++) ...[
            if (index > 0) const Divider(height: 1, color: Color(0xFF1D3853)),
            _DriverRow(
              key: ValueKey('main-factor-${index + 1}'),
              driver: factors[index],
            ),
          ],
          // Whales always have a line, even when they do not rank: an absent
          // or minor reading is said as such, never dropped silently.
          if (!whaleListed) ...[
            const Divider(height: 1, color: Color(0xFF1D3853)),
            _StatusRow(
              key: const ValueKey('whale-status'),
              emoji: '🐋',
              title: 'Baleines',
              status: hierarchy.whaleStatus,
              tone: hierarchy.whaleTone,
            ),
          ],
          const SizedBox(height: 6),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton(
              key: const ValueKey('see-full-analysis'),
              onPressed: onSeeAnalysis,
              style: TextButton.styleFrom(foregroundColor: mobileBlue),
              child: const Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Flexible(
                    child: Text(
                      'Voir l’analyse complète',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  Icon(Icons.chevron_right_rounded, size: 20),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _StatusRow extends StatelessWidget {
  final String emoji;
  final String title;
  final String status;
  final String tone;
  final VoidCallback? onTap;

  /// One figure, when the reading has one: "4,95 %", "95,4 $".
  final String value;

  /// Replaces the tone dot when the state has its own emoji (📈 for a trend).
  final String statusEmoji;

  /// One short key figure under the state ("RSI 77 · résistance proche").
  final String detail;

  const _StatusRow({
    super.key,
    required this.emoji,
    required this.title,
    required this.status,
    required this.tone,
    this.onTap,
    this.value = '',
    this.statusEmoji = '',
    this.detail = '',
  });

  @override
  Widget build(BuildContext context) => InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 11),
          child: Row(
            children: [
              SizedBox(
                width: 34,
                child: Text(
                  emoji,
                  style: const TextStyle(
                    fontSize: 22,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      '${statusEmoji.isEmpty ? _toneEmoji(tone) : statusEmoji} $status',
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: _toneColor(tone),
                        fontSize: 12.5,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    if (detail.isNotEmpty) ...[
                      const SizedBox(height: 2),
                      Text(
                        detail,
                        key: const ValueKey('factor-detail'),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(color: mobileMuted, fontSize: 12),
                      ),
                    ],
                  ],
                ),
              ),
              if (value.isNotEmpty) ...[
                const SizedBox(width: 8),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 130),
                  child: Text(
                    value,
                    key: const ValueKey('factor-value'),
                    textAlign: TextAlign.right,
                    maxLines: 2,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 13,
                      height: 1.25,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ],
              if (onTap != null)
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

class _DriverRow extends StatelessWidget {
  final FutureDriverRead driver;

  const _DriverRow({super.key, required this.driver});

  @override
  Widget build(BuildContext context) => _StatusRow(
        emoji: driver.emoji,
        title: driver.title,
        status: driver.status,
        tone: driver.tone,
        value: driver.value,
        onTap: () => _showDriverDetail(context, driver),
      );
}

/// Section 4: what is happening, why it matters, what the market expects,
/// and what would invalidate the reading - for one driver.
Future<void> _showDriverDetail(BuildContext context, FutureDriverRead driver) =>
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF061525),
      builder: (sheetContext) => SafeArea(
        top: false,
        child: SingleChildScrollView(
          key: const ValueKey('driver-detail'),
          padding: const EdgeInsets.fromLTRB(20, 18, 20, 26),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '${driver.emoji} ${driver.title}',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                '${_toneEmoji(driver.tone)} ${driver.status}',
                style: TextStyle(
                  color: _toneColor(driver.tone),
                  fontSize: 13,
                ),
              ),
              _ReasonDetailBlock(
                title: '📊 QUE SE PASSE-T-IL ?',
                body: driver.what.isEmpty ? 'Non renseigné.' : driver.what,
                muted: driver.what.isEmpty,
              ),
              _ReasonDetailBlock(
                title: '💡 POURQUOI EST-CE IMPORTANT ?',
                body: driver.why.isEmpty ? 'Non renseigné.' : driver.why,
                muted: driver.why.isEmpty,
              ),
              _ReasonDetailBlock(
                title: '🎯 CE QUE LE MARCHÉ ATTEND',
                body: driver.expectation ??
                    'Aucune attente de marché mesurée pour ce facteur.',
                muted: driver.expectation == null,
              ),
              _ReasonDetailBlock(
                title: '❌ CE QUI INVALIDERAIT LA LECTURE',
                body: driver.invalidation,
              ),
              _ReasonDetailBlock(
                title: '🔗 SOURCE',
                body: driver.source.isEmpty
                    ? 'Calcul interne à partir des données collectées.'
                    : driver.source,
                muted: driver.source.isEmpty,
              ),
            ],
          ),
        ),
      ),
    );

/// Why the decision is what it is: the gate that holds it, then the figures.
class _AnalysisExplanationCard extends StatelessWidget {
  final FutureDecisionRead decision;
  final FutureAnalysisRead analysis;

  const _AnalysisExplanationCard({required this.decision, required this.analysis});

  @override
  Widget build(BuildContext context) {
    final summary = analysis.summary;
    if (!summary.isEmpty) return _summaryCard(summary);
    final lead = switch (analysis.action) {
      'BUY' => '✅',
      'SELL' => '❌',
      'INSUFFICIENT_DATA' => '⚪',
      _ => '⏳',
    };
    return GlassPanel(
      key: const ValueKey('decision-explanation'),
      borderColor: const Color(0xFF2B669B),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionTitle(
            emoji: '🔎',
            text: switch (analysis.action) {
              'BUY' => 'Pourquoi acheter ?',
              'SELL' => 'Pourquoi vendre ?',
              'INSUFFICIENT_DATA' => 'Pourquoi pas de recommandation ?',
              _ => 'Pourquoi attendre ?',
            },
          ),
          const SizedBox(height: 10),
          for (final line in ['$lead ${analysis.headline}', ...analysis.reasons.take(4)]) ...[
            Text(
              line,
              style: const TextStyle(
                color: Color(0xFFE6EEF9),
                fontSize: 14,
                height: 1.4,
              ),
            ),
            const SizedBox(height: 7),
          ],
          const SizedBox(height: 2),
          Text(
            'Confiance ${analysis.confidence} % · données ${analysis.dataQuality} % · '
            'dernière donnée ${freshnessLabel(analysis.newestData)}',
            key: const ValueKey('home-data-trust'),
            style: const TextStyle(color: mobileMuted, fontSize: 11.5),
          ),
        ],
      ),
    );
  }
}

extension on _AnalysisExplanationCard {
  /// At most three reasons, chosen by weight in the decision. The statistical
  /// validation is a separate line, never the first reason to wait.
  Widget _summaryCard(AnalysisSummaryRead summary) {
    final entry = summary.entryQuality;
    return GlassPanel(
      key: const ValueKey('decision-explanation'),
      borderColor: const Color(0xFF2B669B),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionTitle(
            emoji: '🔎',
            text: switch (analysis.action) {
              'BUY' => 'Pourquoi acheter ?',
              'SELL' => 'Pourquoi vendre ?',
              'INSUFFICIENT_DATA' => 'Pourquoi pas de recommandation ?',
              _ => 'Pourquoi attendre ?',
            },
          ),
          if (!entry.isEmpty) ...[
            const SizedBox(height: 6),
            Text(
              '${entry.emoji} Point d’entrée : ${entry.label.toLowerCase()}',
              key: const ValueKey('entry-quality'),
              style: TextStyle(
                color: _toneColor(entry.tone),
                fontSize: 13,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
          const SizedBox(height: 6),
          for (var i = 0; i < summary.reasons.length; i++)
            Padding(
              key: ValueKey('home-reason-${i + 1}'),
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: 30,
                    child: Text(
                      summary.reasons[i].emoji,
                      style: const TextStyle(fontSize: 19),
                    ),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          summary.reasons[i].title,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 14.5,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        if (summary.reasons[i].detail.isNotEmpty)
                          Text(
                            summary.reasons[i].detail,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: mobileMuted,
                              fontSize: 12.5,
                              height: 1.3,
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          if (summary.hasValidationWarning) ...[
            const SizedBox(height: 6),
            const Divider(height: 1, color: Color(0xFF1D3853)),
            const SizedBox(height: 9),
            Text(
              '🧪 Validation — ${summary.validationMessage}',
              key: const ValueKey('home-validation'),
              style: const TextStyle(
                color: Color(0xFFB7C6DC),
                fontSize: 12.5,
                height: 1.35,
              ),
            ),
          ],
          const SizedBox(height: 8),
          Text(
            [summary.confidenceLabel, ...summary.dataIssues.take(1)]
                .where((s) => s.isNotEmpty)
                .join(' · '),
            key: const ValueKey('home-data-trust'),
            style: const TextStyle(color: mobileMuted, fontSize: 11.5),
          ),
        ],
      ),
    );
  }
}

/// The families that move the decision now, chosen by their contribution.
class _AnalysisFactorsCard extends StatelessWidget {
  final FutureAnalysisRead analysis;
  final String asset;
  final ApiClient client;
  final VoidCallback onSeeAnalysis;

  const _AnalysisFactorsCard({
    required this.analysis,
    required this.asset,
    required this.client,
    required this.onSeeAnalysis,
  });

  void _open(BuildContext context, AnalysisFamilyRead family) =>
      Navigator.of(context).push(
        MaterialPageRoute<void>(
          // The cycle has a page of its own: a phase, a chart and the
          // history of the analysis, not a list of measures.
          builder: (_) => family.family == 'cycle'
              ? CyclePage(client: client, asset: asset)
              : FamilyDetailPage(
                  family: family,
                  asset: asset,
                  horizon: analysis.horizon,
                ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final homeFamilies = analysis.summary.homeFamilies;
    if (homeFamilies.isNotEmpty) {
      final byKey = {for (final f in analysis.families) f.family: f};
      return GlassPanel(
        key: const ValueKey('main-factors'),
        borderColor: const Color(0xFF245E90),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const _SectionTitle(emoji: '🧭', text: 'Les familles d’indicateurs'),
            const SizedBox(height: 4),
            for (var index = 0; index < homeFamilies.length; index++) ...[
              if (index > 0) const Divider(height: 1, color: Color(0xFF1D3853)),
              _StatusRow(
                key: ValueKey(homeFamilies[index].family == 'onchain'
                    ? 'whale-status'
                    : 'main-factor-${index + 1}'),
                emoji: homeFamilies[index].emoji,
                title: homeFamilies[index].name,
                status: homeFamilies[index].status,
                statusEmoji: homeFamilies[index].statusEmoji,
                tone: homeFamilies[index].tone,
                detail: homeFamilies[index].keyInfo,
                onTap: byKey[homeFamilies[index].family] == null
                    ? null
                    : () => _open(context, byKey[homeFamilies[index].family]!),
              ),
            ],
            const SizedBox(height: 6),
            _seeAllButton(),
          ],
        ),
      );
    }
    final factors = analysis.homeFactors;
    final families = {for (final f in analysis.families) f.family: f};
    final onchain = families['onchain'];
    final onchainListed = factors.any((f) => f.family == 'onchain');
    return GlassPanel(
      key: const ValueKey('main-factors'),
      borderColor: const Color(0xFF245E90),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _SectionTitle(emoji: '📌', text: 'Facteurs principaux'),
          const SizedBox(height: 4),
          for (var index = 0; index < factors.length; index++) ...[
            if (index > 0) const Divider(height: 1, color: Color(0xFF1D3853)),
            _StatusRow(
              key: ValueKey('main-factor-${index + 1}'),
              emoji: factors[index].emoji,
              title: factors[index].label,
              status: factors[index].status,
              tone: factors[index].tone,
              value: factors[index].value,
              onTap: families[factors[index].family] == null
                  ? null
                  : () => Navigator.of(context).push(
                        MaterialPageRoute<void>(
                          builder: (_) => FamilyDetailPage(
                            family: families[factors[index].family]!,
                            asset: asset,
                            horizon: analysis.horizon,
                          ),
                        ),
                      ),
            ),
          ],
          if (onchain != null && !onchainListed) ...[
            const Divider(height: 1, color: Color(0xFF1D3853)),
            _StatusRow(
              key: const ValueKey('whale-status'),
              emoji: '🐋',
              title: 'Baleines & on-chain',
              status: onchain.usable ? onchain.stateLabel : 'Donnée indisponible',
              tone: onchain.usable ? 'YELLOW' : 'WHITE',
            ),
          ],
          const SizedBox(height: 6),
          _seeAllButton(),
        ],
      ),
    );
  }

  Widget _seeAllButton() => Align(
        alignment: Alignment.centerRight,
        child: TextButton(
          key: const ValueKey('see-full-analysis'),
          onPressed: onSeeAnalysis,
          style: TextButton.styleFrom(foregroundColor: mobileBlue),
          child: const Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Flexible(
                child: Text(
                  'Voir l’analyse complète',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Icon(Icons.chevron_right_rounded, size: 20),
            ],
          ),
        ),
      );
}

/// What the largest holders are doing, or a plain statement that it is not
/// measured. An absent reading is shown as absent - never as neutral, and
/// never filled in from something else.
class _WhaleIndicator extends StatelessWidget {
  final FutureDecisionRead decision;

  const _WhaleIndicator({required this.decision});

  @override
  Widget build(BuildContext context) {
    final reading =
        decision.factors.where((item) => item.key == 'whales').firstOrNull;
    if (reading == null) return const SizedBox.shrink();
    final unavailable = reading.availability == 'UNAVAILABLE' ||
        reading.availability == 'NOT_APPLICABLE';
    final (label, tone) = unavailable
        ? ('INDISPONIBLE', mobileMuted)
        : switch (reading.direction) {
            'POSITIVE' => ('FAVORABLE', _badgeGood),
            'NEGATIVE' => ('DÉFAVORABLE', _badgeBad),
            'NEUTRAL' => ('NEUTRE', mobileMuted),
            _ => ('À SURVEILLER', _badgeWatch),
          };
    final line = unavailable
        ? 'Suivi non connecté : aucune source de données baleines n’est '
            'configurée.'
        : _plainHomeSentence(reading.rationale);
    return GlassPanel(
      key: const ValueKey('whale-indicator'),
      borderColor: const Color(0xFF245E90),
      child: Row(
        children: [
          const ColorEmoji(emoji: '🐋', size: 24),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Baleines',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  line,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: mobileMuted,
                    fontSize: 12,
                    height: 1.3,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 9),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 5),
            decoration: BoxDecoration(
              color: tone.withValues(alpha: .13),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: tone.withValues(alpha: .34)),
            ),
            child: Text(
              label,
              style: TextStyle(
                color: tone,
                fontSize: 8.5,
                fontWeight: FontWeight.w900,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// A card heading: one emoji, then the question the card answers.
class _SectionTitle extends StatelessWidget {
  final String emoji;
  final String text;

  const _SectionTitle({required this.emoji, required this.text});

  @override
  Widget build(BuildContext context) => Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          ColorEmoji(emoji: emoji, size: 18),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              text,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 19,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
        ],
      );
}

class _ReasonRow extends StatelessWidget {
  final int index;
  final _DecisionFactor reason;

  const _ReasonRow({required this.index, required this.reason});

  @override
  Widget build(BuildContext context) {
    final badge = _factorBadge(reason);
    return InkWell(
      key: ValueKey('decision-reason-${index + 1}'),
      onTap: () => _showReasonDetail(context, reason),
      borderRadius: BorderRadius.circular(14),
      // No frame of its own: a card inside a card doubled every border on the
      // page. Only the badge keeps an outline, so it is what the eye finds.
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 11),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            // The rank used to be a numbered disc. Numbering implied an order
            // the reader had to hold in mind; the subject of the reason is what
            // they actually scan for, so the icon carries the slot instead.
            SizedBox(
              width: 32,
              child: Center(child: ColorEmoji(emoji: reason.emoji, size: 22)),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _homeTitle(reason),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    // One sentence. Freshness, trend and impact grade used to
                    // ride along in the badge; they answer questions a reader
                    // only asks once they have decided to look closer, so they
                    // live in the detail sheet this row opens.
                    _plainHomeSentence(reason.description),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: mobileMuted,
                      fontSize: 12,
                      height: 1.3,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 9),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 5),
              decoration: BoxDecoration(
                color: badge.tone.withValues(alpha: .13),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: badge.tone.withValues(alpha: .34)),
              ),
              child: Text(
                badge.label,
                style: TextStyle(
                  color: badge.tone,
                  fontSize: 8.5,
                  fontWeight: FontWeight.w900,
                ),
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
  final String emoji;
  final String title;
  final Color tone;
  final List<FutureEvidenceRead> items;
  final String emptyText;

  const _EvidenceListCard({
    super.key,
    required this.emoji,
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
            Row(
              children: [
                ColorEmoji(emoji: emoji, size: 13),
                const SizedBox(width: 6),
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
              ],
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
  final String emoji;
  final String title;
  final Color tone;
  final List<FutureConditionRead> conditions;
  final String? counter;

  const _ConditionListCard({
    super.key,
    required this.emoji,
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
                  child: Row(
                    children: [
                      ColorEmoji(emoji: emoji, size: 13),
                      const SizedBox(width: 6),
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
                    ],
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
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text(
                          _attentionLabelFr(item.attention),
                          style: TextStyle(
                            color: _attentionColor(item.attention),
                            fontSize: 8.5,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        const SizedBox(height: 2),
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
                  ],
                ),
              ),
            // Said once for the whole list rather than repeated on each row:
            // watching something closely is not the same as knowing which way
            // it will go, and the card must never let one imply the other.
            if (events.any((item) => item.directionIsUnknown))
              const Padding(
                padding: EdgeInsets.only(top: 2),
                child: Text(
                  'Ces échéances indiquent quoi surveiller, pas dans quel sens '
                  'le marché ira: le sens ne se connaît qu\'une fois le '
                  'résultat comparé aux attentes.',
                  style: TextStyle(
                    color: mobileMuted,
                    fontSize: 10,
                    height: 1.35,
                  ),
                ),
              ),
          ],
        ),
      );
}

/// Attention is a watching instruction, never a direction.
String _attentionLabelFr(String attention) => switch (attention) {
      'CRITICAL' => 'ATTENTION CRITIQUE',
      'HIGH' => 'ATTENTION ÉLEVÉE',
      'MODERATE' => 'ATTENTION MODÉRÉE',
      'LOW' => 'ATTENTION FAIBLE',
      _ => 'ATTENTION MINIME',
    };

/// Deliberately a single hue at varying strength: green and red would read as
/// a direction, which is exactly what this scale does not carry.
Color _attentionColor(String attention) => switch (attention) {
      'CRITICAL' => const Color(0xFF8FD0FF),
      'HIGH' => const Color(0xFF6FA8DA),
      'MODERATE' => const Color(0xFF5B8AB5),
      _ => mobileMuted,
    };

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

/// What would move the verdict, and nothing else.
///
/// This used to be two cards side by side - conditions to buy on the left,
/// conditions to sell on the right - which asked the reader to compare two
/// lists at a glance on a phone. Only one of them is ever actionable: the path
/// away from the verdict currently shown. The other one is the reason the
/// verdict already is what it is, and belongs to the full analysis.
class _ChangeAndRiskSection extends StatelessWidget {
  final FutureDecisionRead decision;

  const _ChangeAndRiskSection({required this.decision});

  /// The buy path, unless the verdict is already BUY - then what would undo it.
  ({String title, List<String> items, bool toBuy}) _path() {
    if (decision.decision == 'BUY') {
      final items = decision.conditionsToSell.isNotEmpty
          ? decision.conditionsToSell
          : _decisionRisks(decision);
      return (title: 'Ce qui invaliderait l’achat', items: items, toBuy: false);
    }
    final items = decision.conditionsToBuy.isNotEmpty
        ? decision.conditionsToBuy
        : decision.changes;
    return (title: 'Pour passer à acheter', items: items, toBuy: true);
  }

  @override
  Widget build(BuildContext context) {
    final path = _path();
    // Shortening can fold two conditions onto the same words; show each once.
    final items = path.items
        .map((item) => _shortCondition(item, toBuy: path.toBuy))
        .toSet()
        .take(3)
        .toList(growable: false);
    if (items.isEmpty) return const SizedBox.shrink();
    return GlassPanel(
      key: const ValueKey('what-would-change'),
      borderColor: const Color(0xFF2B669B),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionTitle(emoji: '🎯', text: path.title),
          const SizedBox(height: 12),
          for (var index = 0; index < items.length; index++) ...[
            if (index > 0) const SizedBox(height: 11),
            Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Container(
                  width: 22,
                  height: 22,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(
                      color: const Color(0xFF5E7FA3),
                      width: 1.6,
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    items[index],
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 14.5,
                      height: 1.3,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

/// The next few dates, as a glance rather than a briefing.
///
/// Day, time, subject and one line saying what kind of attention it
/// deserves. The countdown, the provider and the full calendar are one tap
/// away.
class _UpcomingEventsCard extends StatelessWidget {
  final List<FutureEventRead> events;

  /// Titles already argued under "Pourquoi ?", so the home never says the
  /// same thing twice in two different shapes.
  final Set<String> alreadyShown;

  /// Event ids already shown among the main factors.
  final Set<String> skipIds;

  const _UpcomingEventsCard({
    required this.events,
    this.alreadyShown = const {},
    this.skipIds = const {},
  });

  /// Dated events only - a row whose first thing is a date cannot show one
  /// without it - most consequential first, then soonest.
  static List<FutureEventRead> ranked(
    List<FutureEventRead> events, {
    Set<String> skip = const {},
    Set<String> skipIds = const {},
  }) {
    const rank = {'CRITICAL': 3, 'HIGH': 2, 'MEDIUM': 1, 'LOW': 0};
    return [...events]
      ..removeWhere((event) =>
          event.scheduledAt == null ||
          skipIds.contains(event.id) ||
          skip.contains(_eventTitleFr(event.title)))
      ..sort((left, right) {
        final byRank = (rank[right.importance.toUpperCase()] ?? 0)
            .compareTo(rank[left.importance.toUpperCase()] ?? 0);
        if (byRank != 0) return byRank;
        return left.scheduledAt!.compareTo(right.scheduledAt!);
      });
  }

  @override
  Widget build(BuildContext context) {
    final all = ranked(events, skip: alreadyShown, skipIds: skipIds);
    // Chosen by importance so the FOMC is not buried behind bill auctions,
    // then read in date order, which is how a calendar is read.
    final displayed = all.take(3).toList()
      ..sort((left, right) => left.scheduledAt!.compareTo(right.scheduledAt!));
    if (displayed.isEmpty) return const SizedBox.shrink();
    return GlassPanel(
      key: const ValueKey('upcoming-events'),
      borderColor: const Color(0xFF245E90),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: _SectionTitle(emoji: '👀', text: 'À surveiller'),
              ),
              if (all.length > displayed.length)
                TextButton(
                  key: const ValueKey('events-see-all'),
                  onPressed: () => _showAllEvents(context, all),
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
          for (var index = 0; index < displayed.length; index++) ...[
            if (index > 0) const Divider(height: 1, color: Color(0xFF1D3853)),
            _UpcomingEventRow(event: displayed[index]),
          ],
        ],
      ),
    );
  }
}

Future<void> _showAllEvents(
  BuildContext context,
  List<FutureEventRead> events,
) =>
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF061525),
      builder: (sheetContext) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: .7,
        maxChildSize: .92,
        builder: (context, controller) => SafeArea(
          top: false,
          child: ListView(
            controller: controller,
            padding: const EdgeInsets.fromLTRB(20, 18, 20, 28),
            children: [
              const _SectionTitle(emoji: '🗓️', text: 'Prochaines échéances'),
              const SizedBox(height: 12),
              for (var index = 0; index < events.length; index++) ...[
                if (index > 0)
                  const Divider(height: 1, color: Color(0xFF1D3853)),
                _UpcomingEventRow(event: events[index]),
              ],
            ],
          ),
        ),
      ),
    );

class _UpcomingEventRow extends StatelessWidget {
  final FutureEventRead event;

  const _UpcomingEventRow({required this.event});

  @override
  Widget build(BuildContext context) {
    final when = event.scheduledAt?.toLocal();
    final time = _eventTime(event.scheduledAt);
    return InkWell(
      key: ValueKey('event-${event.id}'),
      onTap: () => _showEventDetails(context, event),
      borderRadius: BorderRadius.circular(14),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 11),
        child: Row(
          children: [
            SizedBox(
              width: 44,
              child: Column(
                children: [
                  Text(
                    '${when?.day ?? '—'}',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 19,
                      height: 1,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    when == null ? '' : _monthsShort[when.month - 1],
                    style: const TextStyle(
                      color: Color(0xFF9FB3CC),
                      fontSize: 9.5,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ),
            SizedBox(
              width: 52,
              child: Text(
                time ?? '',
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: Color(0xFFB7C6DC),
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      // Inline in the Text the glyph fell back to a white
                      // outline; ColorEmoji carries the colour font.
                      ColorEmoji(
                        emoji: _reasonEmoji(
                          '${_eventTitleFr(event.title)} ${event.title}',
                        ),
                        size: 13,
                      ),
                      const SizedBox(width: 5),
                      Expanded(
                        child: Text(
                          _eventTitleFr(event.title),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 14,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 3),
                  Text(
                    _eventSubtitle(event),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: mobileMuted, fontSize: 12),
                  ),
                ],
              ),
            ),
            const Icon(
              Icons.chevron_right_rounded,
              color: Color(0xFF55749B),
              size: 18,
            ),
          ],
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
                  // The alignment label varies with the data and grew past the
                  // row when more timeframes started agreeing; it yields rather
                  // than pushing the heading off screen.
                  Flexible(
                    child: Text(
                      timeframes!.alignmentLabel,
                      textAlign: TextAlign.end,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: mobileBlue,
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                      ),
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
/// A gate is not a market reading: it is the reason the readings are not
/// acted on - here, that none of them has shown a measurable edge.
enum _FactorKind { futureCatalyst, currentSignal, gate }

class _DecisionFactor {
  final _FactorKind kind;

  /// The engine's factor key (flows, spot, technical...), empty for events.
  final String key;

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
    this.key = '',
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
    return 'Revenus des ménages US';
  }
  if (value.contains('gdp')) return 'PIB américain';
  if (value.contains('cpi') || value.contains('consumer price')) {
    return 'Inflation américaine';
  }
  if (value.contains('employment') || value.contains('nonfarm')) {
    return 'Emploi américain';
  }
  if (value.contains('treasury auction')) {
    // "1-Year 10-Month Note" is one maturity with two parts; reading only the
    // first produced "(1 ans)".
    final parts = RegExp(r'(\d+)[- ](week|year|month)')
        .allMatches(value)
        .map((match) {
      final count = int.parse(match.group(1)!);
      final unit = switch (match.group(2)) {
        'week' => count > 1 ? 'semaines' : 'semaine',
        'month' => 'mois',
        _ => count > 1 ? 'ans' : 'an',
      };
      return '$count $unit';
    }).toList();
    // The maturity first: it is the only thing telling two rows apart, and a
    // narrow screen cuts the end of a title.
    if (parts.isEmpty) return 'Adjudication du Trésor US';
    return 'Adjudication ${parts.join(' ')} du Trésor US';
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


String _importanceImpact(String importance) =>
    switch (importance.toUpperCase()) {
      'CRITICAL' => 'TRÈS ÉLEVÉ',
      'HIGH' => 'ÉLEVÉ',
      'MEDIUM' => 'MODÉRÉ',
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

/// A concrete, readable name for what one reading measures.
///
/// The name follows the measurement, never the family it is filed under.
String _readingTitle(FutureFactorRead reading) {
  final negative = reading.direction == 'NEGATIVE';
  return switch (reading.key) {
    'flows' => negative ? 'Sorties nettes des ETF' : 'Entrées nettes sur les ETF',
    'spot' => negative
        ? 'Pression vendeuse au comptant'
        : 'Pression acheteuse au comptant',
    'whales' => 'Mouvements de gros portefeuilles',
    'positioning' => 'Positionnement sur les dérivés',
    'derivatives' => 'Positionnement sur les dérivés',
    'funding' => 'Coût du levier',
    'basis' => 'Écart contrats / comptant',
    'technical' => negative
        ? 'Tendance court terme fragile'
        : 'Tendance court terme porteuse',
    'volatility' => 'Compression de volatilité',
    'implied_volatility' => 'Volatilité attendue par les options',
    'energy' => 'Énergie',
    'rates' => 'Rendements obligataires',
    'credit' => 'Écarts de crédit',
    _ => reading.label,
  };
}

String _readingInvalidation(String key) => switch (key) {
      'flows' =>
        'Un retour durable des flux dans le sens inverse sur plusieurs séances.',
      'spot' => 'Un rééquilibrage durable entre acheteurs et vendeurs au comptant.',
      'positioning' || 'derivatives' =>
        'Une reprise durable des positions à levier accompagnée d’une reprise du prix.',
      'funding' => 'Un retour du coût du levier vers sa zone habituelle.',
      'technical' => 'Une invalidation de la structure sur l’échelle de référence.',
      'volatility' || 'implied_volatility' =>
        'Une sortie de compression, qui donnerait enfin une direction.',
      'energy' => 'Une stabilisation durable du prix du pétrole.',
      'rates' => 'Une détente durable des rendements.',
      'credit' => 'Un resserrement durable des écarts de crédit.',
      _ => 'Une donnée nouvelle qui renverserait cette lecture.',
    };

String _readingConsequence(
  FutureFactorRead reading,
  String horizon,
  String asset,
) {
  if (reading.impactOnDirection == 'NONE') {
    return 'Mouvement potentiellement important sur $horizon, '
        'direction actuellement incertaine.';
  }
  return switch (reading.direction) {
    'POSITIVE' => 'Soutien à la hausse pour $asset sur $horizon.',
    'NEGATIVE' => 'Pression à la baisse pour $asset sur $horizon.',
    _ => 'Pas d’effet directionnel mesuré sur $horizon.',
  };
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


/// Build three to five concrete causes: dated catalysts and measured signals.
/// How many factors the home page carries before "voir l'analyse complète".
const _homeFactorLimit = 4;

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

  // Signals are built from the engine's own readings, not from the analytical
  // family they belong to. Titling by family identifier is what produced
  // "Sorties nettes des ETF" above a sentence about who crosses the spread:
  // when the ETF series went stale the family fell back to spot pressure, and
  // the screen kept the ETF title. A reading now names itself.
  for (final reading in decision.factors) {
    if (factors.length >= 5) break;
    if (reading.availability == 'UNAVAILABLE' ||
        reading.availability == 'NOT_APPLICABLE') {
      continue;
    }
    final guidance = _guidanceByKey[reading.key] ?? _guidanceFallback;
    if (identical(guidance, _guidanceFallback)) continue;
    factors.add(_DecisionFactor(
      kind: _FactorKind.currentSignal,
      key: reading.key,
      title: _readingTitle(reading),
      description: _cleanExplanation(reading.rationale),
      direction: _normalisedDirection(reading.direction),
      impact: _impactLabelFr(reading.impact),
      emoji: _emojiByKey[reading.key] ??
          _reasonEmoji('${reading.label} ${reading.key}'),
      when: reading.availability == 'STALE' ? 'PÉRIMÉ' : 'ACTUEL',
      confidence: reading.confidence,
      trend: reading.trend,
      impactOnDirection: reading.impactOnDirection,
      observation: _cleanExplanation(reading.rationale),
      invalidation: _readingInvalidation(reading.key),
      whyItMatters: reading.causalChain.length >= 3
          ? reading.causalChain.last
          : guidance.why,
      caveat: reading.missingRequirements.isNotEmpty
          ? reading.missingRequirements.first
          : guidance.caveat,
      consequence: _readingConsequence(reading, horizon, asset),
      source: reading.provider,
      sourceUrl: reading.sourceUrl,
    ));
  }

  // Section 7: order by contribution to the decision, not by date. An event
  // whose direction is unknown can still rank first when it dominates the risk.
  factors.sort((left, right) =>
      _contribution(right, decision).compareTo(_contribution(left, decision)));
  // Section 6: four factors on the home page. The rest stays one tap away in
  // the full analysis, which is where a reader goes to understand rather than
  // to decide.
  return factors.take(_homeFactorLimit).toList();
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
/// Turn a measured rationale into a sentence, for the front page only.
///
/// The reading behind an ETF row is "20 séances: +1 751.7 M\$ 5 dernières
/// séances: -623.8 M\$". Every figure there is real and every figure there is
/// noise to someone deciding whether to look closer: what they need is that
/// the month is positive and the last week is not. The numbers keep their
/// place in the detail sheet this row opens.
final _twoWindowFlows = RegExp(
  r'(\d+)\s+séances?\s*:\s*([+-])[\d\s.,]+\s*M\$[;,.\s]*'
  r'(\d+)\s+dernières\s+séances?\s*:\s*([+-])[\d\s.,]+\s*M\$',
);

String _plainHomeSentence(String rationale) {
  final match = _twoWindowFlows.firstMatch(rationale);
  if (match != null) {
    final longWindow = match.group(1);
    final shortWindow = match.group(3);
    final longPositive = match.group(2) == '+';
    final shortPositive = match.group(4) == '+';
    if (longPositive == shortPositive) {
      return longPositive
          ? 'Entrées positives sur $longWindow séances comme sur les '
              '$shortWindow dernières.'
          : 'Sorties sur $longWindow séances comme sur les $shortWindow '
              'dernières.';
    }
    return longPositive
        ? 'Entrées positives sur $longWindow séances, sorties sur les '
            '$shortWindow dernières.'
        : 'Sorties sur $longWindow séances, entrées sur les $shortWindow '
            'dernières.';
  }
  // "1 échelle(s) haussière(s) contre 0" - the placeholder plural reads as an
  // unfinished string to anyone who did not write it.
  return rationale.replaceAllMapped(
    RegExp(r'(\d+)\s+([^\s(]+)\(s\)(\s+([^\s(]+)\(s\))?'),
    (match) {
      final count = int.tryParse(match.group(1) ?? '') ?? 0;
      final plural = count > 1 ? 's' : '';
      final noun = '${match.group(2)}$plural';
      final adjective =
          match.group(4) == null ? '' : ' ${match.group(4)}$plural';
      return '$count $noun$adjective';
    },
  );
}

/// The reasons the home shows, in the order it shows them.
///
/// When the verdict is WAIT because no measured signal has shown an edge,
/// that absence is the real reason and it leads the list - otherwise three
/// green badges under ATTENDRE read as a contradiction. It comes from the
/// engine's own consistency check, never from the look of the signals.
List<_DecisionFactor> _homeReasons(
  FutureDecisionRead decision,
  _FutureBundle bundle, {
  int? limit = 3,
}) {
  // Whales have their own indicator on the home; listing them here as well
  // would say the same thing twice.
  final factors = _decisionFactors(decision, bundle)
      .where((item) => item.key != 'whales')
      .toList();
  final signals = _signalsLabel(factors);
  final gated = decision.decision == 'WAIT' &&
      decision.noMeasurableEdge &&
      !decision.eventRiskActive;
  // When signals pull against each other, the contradiction is itself the
  // explanation and both sides need the room. The gate still heads the full
  // list one tap away.
  final gateOnHome = gated && signals != 'Mitigés';
  if (limit == null) {
    return [if (gated) _edgeGate(decision, signals), ...factors];
  }
  final shown = [
    if (gateOnHome) _edgeGate(decision, signals),
    ...factors,
  ].take(limit).toList();
  // Section 14: a mixed reading must show both sides. Ranking by weight can
  // push every opposing signal past the cut, leaving "Mitigée" above three
  // green badges.
  bool leans(_DecisionFactor item, String side) =>
      item.kind == _FactorKind.currentSignal &&
      (item.direction ?? '').toUpperCase().contains(side);
  for (final side in ['BULLISH', 'BEARISH']) {
    if (shown.any((item) => leans(item, side))) continue;
    final missing = factors.where((item) => leans(item, side)).firstOrNull;
    if (missing == null || shown.isEmpty) continue;
    shown[shown.length - 1] = missing;
  }
  return shown;
}

_DecisionFactor _edgeGate(FutureDecisionRead decision, String signals) {
  final horizon = _horizonLongLabel(decision.horizon);
  return _DecisionFactor(
    kind: _FactorKind.gate,
    key: 'edge',
    title: 'Confirmation encore insuffisante',
    description: signals == 'Favorables'
        ? 'Les signaux positifs ne sont pas encore assez solides.'
        : 'Aucun signal ne montre encore un avantage mesurable.',
    direction: null,
    impact: 'ÉLEVÉ',
    emoji: '⏳',
    when: 'ACTUEL',
    observation: 'Aucun des signaux testés n’a montré, sur l’historique, un '
        'avantage qui résiste aux tests statistiques sur $horizon.',
    whyItMatters: 'Un signal favorable qui n’a jamais prédit mieux que le '
        'hasard ne justifie pas de prendre position, même s’il semble '
        'porteur aujourd’hui.',
    consequence: 'Le verdict reste ATTENDRE tant qu’aucun avantage mesurable '
        'n’apparaît, quelle que soit la couleur des autres signaux.',
    invalidation: 'Un signal dont l’avantage se confirme sur l’historique '
        'et survit à la correction pour tests multiples.',
    source: 'Contrôle de cohérence de l’analyse',
  );
}

/// Short, plain titles for the subjects that come up most. The engine title
/// stays in the detail sheet; the home needs something readable in one look.
String _homeTitle(_DecisionFactor factor) {
  final direction = (factor.direction ?? '').toUpperCase();
  final up = direction.contains('BULLISH');
  final down = direction.contains('BEARISH');
  switch (factor.key) {
    case 'spot':
      if (up) return 'Achats spot dominants';
      if (down) return 'Ventes spot dominantes';
    case 'flows':
      final flows = _twoWindowFlows.firstMatch(factor.description);
      final weakening =
          flows != null && flows.group(2) == '+' && flows.group(4) == '-';
      if (up) return weakening ? 'ETF encore favorables' : 'Entrées sur les ETF';
      if (down) return 'Sorties sur les ETF';
    case 'technical':
      if (up) return 'Tendance courte haussière';
      if (down) return 'Tendance courte baissière';
  }
  return factor.kind == _FactorKind.futureCatalyst
      ? factor.title.split(' — ').first
      : factor.title;
}

/// The balance of measured signals, in the words the hero card uses.
String _tendencyLabel(String signals) => switch (signals) {
      'Favorables' => 'Plutôt favorable',
      'Défavorables' => 'Plutôt défavorable',
      'Mitigés' => 'Mitigée',
      'Neutres' => 'Neutre',
      _ => 'Insuffisante',
    };

String _riskLabelShort(String risk) => switch (risk.toUpperCase()) {
      'CRITICAL' || 'VERY_HIGH' => 'Critique',
      'HIGH' => 'Élevé',
      'MODERATE' || 'MEDIUM' => 'Modéré',
      'LOW' => 'Faible',
      _ => 'Inconnu',
    };

/// A change condition, cut to the few words that fit on one line.
///
/// The engine phrases each condition as "Famille: mécanisme mesuré sur...";
/// the family says what to watch, which is all the front page needs. The full
/// wording stays in the analysis.
String _shortCondition(String raw, {required bool toBuy}) {
  final text = _frenchifyEventNames(raw).trim();
  final event = RegExp(r'^«\s*(.+?)\s*»').firstMatch(text);
  if (event != null) {
    return '${toBuy ? 'Issue favorable' : 'Issue défavorable'} : '
        '${event.group(1)}';
  }
  final family = text.split(':').first.trim().toLowerCase();
  if (family.startsWith('macro')) {
    return toBuy
        ? 'Contexte macro plus porteur'
        : 'Dégradation du contexte macro';
  }
  if (family.startsWith('flux')) {
    return toBuy ? 'Flux acheteurs durables' : 'Retour des sorties nettes';
  }
  if (family.startsWith('positionnement')) {
    return toBuy
        ? 'Reprise saine des positions acheteuses'
        : 'Excès de levier';
  }
  if (family.startsWith('technique')) {
    return toBuy
        ? 'Confirmation du mouvement'
        : 'Cassure de la structure haussière';
  }
  return text;
}

const _monthsShort = [
  'JAN', 'FÉV', 'MAR', 'AVR', 'MAI', 'JUIN',
  'JUIL', 'AOÛT', 'SEP', 'OCT', 'NOV', 'DÉC',
];

/// One line under an upcoming date: what kind of attention it deserves.
/// Never a direction - a date on a calendar does not have one yet.
String _eventSubtitle(FutureEventRead event) {
  final type = '${event.eventType} ${event.title}'.toUpperCase();
  if (RegExp(r'FOMC|ECB|BOJ|RATE_DECISION|POLICY_DECISION|MONETARY')
      .hasMatch(type)) {
    return 'Direction encore inconnue';
  }
  if (RegExp(r'VOTE|BILL|HEARING|MARKUP|SEC_|CFTC|REGUL|SENATE|HOUSE')
      .hasMatch(type)) {
    return 'Étape importante à surveiller';
  }
  return switch (event.importance.toUpperCase()) {
    'CRITICAL' || 'HIGH' => 'Impact potentiel élevé',
    _ => 'Impact potentiel modéré',
  };
}

/// "14:30", or nothing when the source only gives a day.
String? _eventTime(DateTime? when) {
  if (when == null) return null;
  final utc = when.toUtc();
  if (utc.hour == 0 && utc.minute == 0) return null;
  final local = when.toLocal();
  return '${local.hour.toString().padLeft(2, '0')}:'
      '${local.minute.toString().padLeft(2, '0')}';
}

/// The badge one reason carries on the home.
///
/// Attention and direction are different statements and the home must never
/// let one stand in for the other. A vote that has not happened yet is
/// something to watch; calling it unfavourable would mean deciding its outcome
/// in advance, which the engine refuses to do.
({String label, Color tone}) _factorBadge(_DecisionFactor factor) {
  if (factor.kind != _FactorKind.currentSignal) {
    return (label: 'À SURVEILLER', tone: _badgeWatch);
  }
  return switch (factor.direction?.toUpperCase()) {
    'BULLISH' || 'STRONGLY_BULLISH' => (label: 'FAVORABLE', tone: _badgeGood),
    'BEARISH' || 'STRONGLY_BEARISH' => (label: 'DÉFAVORABLE', tone: _badgeBad),
    'NEUTRAL' => (label: 'NEUTRE', tone: mobileMuted),
    _ => (label: 'À SURVEILLER', tone: _badgeWatch),
  };
}

const _badgeGood = Color(0xFF55DD8B);
const _badgeBad = Color(0xFFFF6676);
const _badgeWatch = Color(0xFFFFB34F);

/// One word for the balance of the measured signals.
///
/// Counts only what is measured now: a pending catalyst has no direction to
/// add to either side.
String _signalsLabel(List<_DecisionFactor> factors) {
  final measured =
      factors.where((item) => item.kind == _FactorKind.currentSignal).toList();
  if (measured.isEmpty) return 'Insuffisants';
  final favorable = measured
      .where((item) => (item.direction ?? '').toUpperCase().contains('BULLISH'))
      .length;
  final against = measured
      .where((item) => (item.direction ?? '').toUpperCase().contains('BEARISH'))
      .length;
  if (favorable > 0 && against > 0) return 'Mitigés';
  if (favorable > against) return 'Favorables';
  if (against > favorable) return 'Défavorables';
  return 'Neutres';
}

Color _signalsTone(String label) => switch (label) {
      'Favorables' => _badgeGood,
      'Défavorables' => _badgeBad,
      'Mitigés' => _badgeWatch,
      _ => mobileMuted,
    };

/// Why the verdict is what it is, in one sentence a reader can act on.
///
/// WAIT is not a failure state and the sentence must say which kind of waiting
/// this is: an outcome still pending, signals pulling against each other, or
/// not enough measured to justify taking a position at all.
String _verdictSentence(
  FutureDecisionRead decision,
  List<_DecisionFactor> factors,
) {
  final bullish = decision.direction.contains('BULLISH');
  final bearish = decision.direction.contains('BEARISH');

  switch (decision.decision) {
    case 'BUY':
      // A verdict that runs against the underlying reading has to say so. It
      // used to be a separate note under the card; hiding it now would be
      // simplification at the cost of honesty.
      if (bearish) {
        return 'Le fond reste baissier, mais la configuration actuelle '
            'justifie d’acheter sur cet horizon.';
      }
      return 'Plusieurs signaux favorables sont maintenant confirmés.';
    case 'SELL':
      if (bullish) {
        return 'Le marché reste haussier sur le fond, mais les risques à '
            'court terme justifient de réduire.';
      }
      return 'Le risque s’est nettement dégradé et plusieurs signaux '
          'défavorables sont confirmés.';
    default:
      if (decision.eventRiskActive) {
        if (bullish) {
          return 'La lecture de fond reste haussière, mais un événement '
              'important n’a pas encore livré son résultat.';
        }
        return 'Un événement important n’a pas encore livré son résultat: '
            's’engager maintenant reviendrait à parier sur son issue.';
      }
      final signals = _signalsLabel(factors);
      if (signals == 'Mitigés') {
        return 'Les signaux se contredisent et aucune confirmation ne se '
            'dégage pour l’instant.';
      }
      // Favourable readings under a WAIT verdict look like a contradiction
      // until the sentence says what is missing. It is not that conditions
      // are poor - several are good - it is that nothing measured yet gives
      // an edge worth acting on. Section 26: say that in the reader's terms,
      // never by naming the engine state that produced it.
      if (signals == 'Favorables') {
        return 'Les signaux sont plutôt favorables, mais sans avantage '
            'encore assez clair pour acheter.';
      }
      if (signals == 'Défavorables') {
        return 'Les signaux sont plutôt défavorables, mais pas assez nets pour '
            'justifier de vendre.';
      }
      return 'Les signaux actuels ne donnent pas encore un avantage '
          'suffisamment clair pour prendre position.';
  }
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


/// Amplitude of the move. It says how much, never which way.
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


/// One recognisable picture per subject, so a row can be scanned before it
/// is read.
const _emojiByKey = <String, String>{
  'spot': '🛒',
  'flows': '💰',
  'technical': '📈',
  'positioning': '⚖️',
  'derivatives': '⚖️',
  'funding': '💸',
  'volatility': '🌪️',
  'implied_volatility': '🌪️',
  'rates': '🏦',
  'energy': '🛢️',
  'credit': '💳',
  'regulation': '🏛️',
  'whales': '🐋',
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
      // An aggressive buyer lifts the ask; an aggressive seller hits the bid.
      // Translating both as "accepter de payer le prix demandé" described a
      // buyer and was applied to sellers too, which reversed the meaning.
      .replaceAll(
        "Les acheteurs traversent le spread plus souvent que d'habitude.",
        'Les achats au marché dominent actuellement les ventes.',
      )
      .replaceAll(
        "Les vendeurs traversent le spread plus souvent que d'habitude.",
        'Les ventes au marché dominent actuellement les achats.',
      )
      .replaceAll('traversent le spread', 'passent au marché')
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
