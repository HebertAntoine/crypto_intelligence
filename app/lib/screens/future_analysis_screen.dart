/// Future-first analysis for BTC, ETH and SOL.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/future_models.dart';
import '../api/models.dart';
import '../live_prices/live_price_service.dart';
import '../theme/app_theme.dart';
import '../widgets/live_price_builder.dart';
import '../widgets/mobile_kit.dart';

const _emojiFontFallback = <String>[
  'Apple Color Emoji',
  'Segoe UI Emoji',
  'Noto Color Emoji',
];

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

  Future<void> _showReasonDetails(
    FutureDecisionRead decision,
    _FutureBundle bundle,
  ) =>
      showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        backgroundColor: const Color(0xFF061525),
        builder: (sheetContext) {
          final reasons = _decisionReasons(decision, bundle);
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
                  horizon: _horizon,
                  onHorizonTap: _chooseHorizon,
                ),
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
                _Scenarios(
                  scenarios: decision.scenarios,
                  horizon: _horizon,
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
  final String horizon;
  final VoidCallback onHorizonTap;

  const _DecisionCard({
    required this.decision,
    required this.horizon,
    required this.onHorizonTap,
  });

  @override
  Widget build(BuildContext context) {
    final visual = _decisionVisual(decision.decision);
    return ClipRRect(
      borderRadius: BorderRadius.circular(22),
      child: Stack(
        children: [
          Positioned.fill(
            child: Image.asset(
              visual.asset,
              key: ValueKey(visual.asset),
              fit: BoxFit.cover,
              alignment: Alignment.centerRight,
              filterQuality: FilterQuality.high,
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
            constraints: const BoxConstraints(minHeight: 268),
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
                    _decisionHeadline(decision),
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
                const SizedBox(height: 18),
                Row(
                  children: [
                    Expanded(
                      child: _DecisionMetric(
                        icon: Icons.shield_outlined,
                        label: 'Risque',
                        value: _impactLabel(decision.eventRisk),
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
                        label: 'Volatilité',
                        value: _movementLabel(decision.movement),
                        tone: visual.accent,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: _DecisionMetric(
                        icon: Icons.bar_chart_rounded,
                        label: 'Confiance',
                        value: '${(decision.confidence * 100).round()} %',
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
    final reasons = _decisionReasons(decision, bundle);
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
          for (var index = 0; index < reasons.length; index++) ...[
            _ReasonRow(index: index, reason: reasons[index]),
            if (index < reasons.length - 1)
              const Divider(height: 1, color: Color(0xFF1D3853)),
          ],
        ],
      ),
    );
  }
}

class _ReasonRow extends StatelessWidget {
  final int index;
  final _DecisionReasonItem reason;

  const _ReasonRow({required this.index, required this.reason});

  @override
  Widget build(BuildContext context) {
    final tone = _reasonTone(index);
    return Padding(
      key: ValueKey('decision-reason-${index + 1}'),
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
            child: Text(
              reason.emoji,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 23,
                height: 1.2,
                fontFamilyFallback: _emojiFontFallback,
              ),
            ),
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
                  _cleanExplanation(reason.explanation),
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
            constraints: const BoxConstraints(minWidth: 55, maxWidth: 68),
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
                  _impactLabel(reason.impact),
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: tone,
                    fontSize: 9,
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
              child: _SignalListCard(
                icon: '⬆️',
                title: 'Ce qui pourrait changer la décision',
                items: decision.changes,
                tone: const Color(0xFF55DD8B),
                bullet: '✓',
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _SignalListCard(
                icon: '⚠️',
                title: 'Risques à surveiller',
                items: _decisionRisks(decision),
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
                Text(
                  icon,
                  style: const TextStyle(
                    fontSize: 18,
                    fontFamilyFallback: _emojiFontFallback,
                  ),
                ),
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
    final displayed =
        _expanded ? widget.events : widget.events.take(4).toList();
    return GlassPanel(
      borderColor: const Color(0xFF245E90),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text(
                '🗓️',
                style: TextStyle(
                  fontSize: 19,
                  fontFamilyFallback: _emojiFontFallback,
                ),
              ),
              const SizedBox(width: 8),
              const Expanded(
                child: Text(
                  'Ce qui arrive',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
              if (widget.events.length > 4)
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
                      Text(_expanded ? 'Réduire' : 'Voir tout'),
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
                      event.title,
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
                  const Text(
                    '🗓️',
                    style: TextStyle(
                      fontSize: 24,
                      fontFamilyFallback: _emojiFontFallback,
                    ),
                  ),
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
                event.title,
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

class _DecisionReasonItem {
  final String title;
  final String explanation;
  final String impact;
  final String when;
  final String emoji;

  const _DecisionReasonItem({
    required this.title,
    required this.explanation,
    required this.impact,
    required this.when,
    required this.emoji,
  });
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

List<_DecisionReasonItem> _decisionReasons(
  FutureDecisionRead decision,
  _FutureBundle bundle,
) {
  final items = <_DecisionReasonItem>[];
  for (final reason in decision.reasons.take(4)) {
    items.add(_DecisionReasonItem(
      title: reason.title,
      explanation: reason.explanation,
      impact: reason.impact ?? 'UNKNOWN',
      when: _dateBadge(reason.dateTime),
      emoji: _reasonEmoji(reason.title),
    ));
  }

  for (final family in decision.families) {
    if (items.length >= 4 ||
        items.any(
            (item) => item.title.toLowerCase() == family.label.toLowerCase())) {
      continue;
    }
    final explanation = family.available
        ? family.summary
        : family.unavailableReason ??
            'Famille indisponible pour cette analyse.';
    items.add(_DecisionReasonItem(
      title: family.label,
      explanation: explanation,
      impact: family.movement ?? 'UNKNOWN',
      when: family.freshness,
      emoji: _reasonEmoji(family.label),
    ));
  }

  final frames = bundle.timeframes;
  items.add(_DecisionReasonItem(
    title: 'Unités de temps',
    explanation: frames == null
        ? 'Lecture multi-unités indisponible pour cette analyse.'
        : frames.narrative.isNotEmpty
            ? frames.narrative
            : '${frames.alignmentLabel}. ${frames.caveat}',
    impact: frames?.conflicts.isNotEmpty == true ? 'HIGH' : 'NORMAL',
    when: 'ACTUEL',
    emoji: '🧭',
  ));

  final implied = bundle.impliedVolatility;
  items.add(_DecisionReasonItem(
    title: 'Volatilité implicite',
    explanation: implied == null
        ? 'Lecture des options indisponible pour cette analyse.'
        : implied.available
            ? _impliedVolatilitySentence(implied)
            : (implied.unavailableReason.isEmpty
                ? 'Indisponible pour cet actif.'
                : implied.unavailableReason),
    impact: implied?.pricing.contains('EXPENSIVE') == true ? 'HIGH' : 'NORMAL',
    when: 'ACTUEL',
    emoji: '〰️',
  ));
  return items.take(6).toList();
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
        : '${event.title} : risque événementiel '
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

String _decisionHeadline(FutureDecisionRead decision) {
  if (decision.reasons.isNotEmpty) {
    return _cleanExplanation(decision.reasons.first.explanation);
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
      value.contains('liquidité')) {
    return '🏛️';
  }
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
    return '📊';
  }
  if (value.contains('volatil') || value.contains('technique')) return '〰️';
  if (value.contains('réglement') || value.contains('regulat')) return '⚖️';
  return '🔎';
}

String _cleanExplanation(String value) {
  var cleaned = value
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

String _dateBadge(String? value) {
  final parsed = value == null ? null : DateTime.tryParse(value)?.toLocal();
  if (parsed == null) return 'ACTUEL';
  return '${parsed.day} ${_monthLabel(parsed).toLowerCase()}';
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
