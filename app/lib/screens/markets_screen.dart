/// Ecran "Marches".
///
/// Vue courte pour conserver la navigation mobile complete tout en restant
/// alignee avec la source backend.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../live_prices/live_price_service.dart';
import '../theme/app_theme.dart';
import '../widgets/common.dart';
import '../widgets/live_price_builder.dart';
import '../widgets/mobile_kit.dart';

class MarketsScreen extends StatefulWidget {
  final ApiClient client;
  final LivePriceSource? livePrices;
  final ValueChanged<String>? onAssetSelected;

  const MarketsScreen({
    super.key,
    required this.client,
    this.livePrices,
    this.onAssetSelected,
  });

  @override
  State<MarketsScreen> createState() => _MarketsScreenState();
}

class _MarketsScreenState extends State<MarketsScreen> {
  static const _assets = ['BTC', 'ETH', 'SOL'];
  late Future<_MarketsData> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<_MarketsData> _load() async {
    // Each block is optional: a missing one is reported in place rather than
    // failing the whole screen.
    Future<T?> safe<T>(Future<T> f) async {
      try {
        return await f;
      } catch (_) {
        return null;
      }
    }

    final reads = await widget.client.todayAll(_assets);
    final results = await Future.wait([
      safe(widget.client.marketRatios()),
      safe(widget.client.marketBreadth()),
      safe(widget.client.marketLiquidity()),
    ]);
    final frames = <String, MultiTimeframeRead?>{};
    final vols = <String, ImpliedVolatilityRead?>{};
    for (final asset in _assets) {
      frames[asset] = await safe(widget.client.multiTimeframeRead(asset));
      vols[asset] = await safe(widget.client.impliedVolatility(asset));
    }
    return _MarketsData(
      reads: reads,
      ratios: results[0],
      breadth: results[1],
      liquidity: results[2],
      timeframes: frames,
      impliedVolatility: vols,
    );
  }

  void _reload() {
    setState(() => _future = _load());
  }

  @override
  Widget build(BuildContext context) {
    return MobileGradientFrame(
      child: RefreshIndicator(
        onRefresh: () async => _reload(),
        child: FutureBuilder<_MarketsData>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const LoadingView(what: 'marchés');
            }
            if (snapshot.hasError) {
              return ErrorView(error: snapshot.error!, onRetry: _reload);
            }

            final data = snapshot.data!;
            return MobileScrollView(
              padding: const EdgeInsets.fromLTRB(30, 30, 30, 260),
              children: [
                MobileHeader(
                  title: 'Marchés',
                  subtitle: 'Contexte marché, unités de temps et volatilité',
                  onInfo: () => _showInfo(context),
                ),
                const SizedBox(height: 24),
                _ContextPanel(
                  ratios: data.ratios,
                  breadth: data.breadth,
                  liquidity: data.liquidity,
                ),
                const SizedBox(height: 16),
                for (final read in data.reads) ...[
                  _MarketLine(
                    read: read,
                    livePrices: widget.livePrices,
                    timeframes: data.timeframes[read.asset],
                    impliedVolatility: data.impliedVolatility[read.asset],
                    onTap: widget.onAssetSelected == null
                        ? () => _showMarketDetail(
                              context,
                              read,
                              data.timeframes[read.asset],
                              data.impliedVolatility[read.asset],
                            )
                        : () => widget.onAssetSelected!(read.asset),
                  ),
                  const SizedBox(height: 16),
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
        title: const Text('Marchés'),
        content: const Text(
          'Synthèse rapide des actifs suivis. Les verdicts viennent du backend.',
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

  void _showMarketDetail(
    BuildContext context,
    TodayRead read,
    MultiTimeframeRead? timeframes,
    ImpliedVolatilityRead? impliedVolatility,
  ) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: mobilePanel,
      builder: (context) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.68,
        minChildSize: 0.34,
        maxChildSize: 0.92,
        builder: (context, controller) => ListView(
          controller: controller,
          padding: const EdgeInsets.fromLTRB(22, 18, 22, 32),
          children: [
            Row(
              children: [
                CryptoLogo(asset: read.asset, size: 56),
                const SizedBox(width: 14),
                Expanded(
                  child: Text(
                    '${read.asset} · ${_assetName(read.asset)}',
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
            LivePriceBuilder(
              source: widget.livePrices,
              asset: read.asset,
              builder: (context, live, connection) => Column(
                children: [
                  _MarketSheetLine(
                    label: 'Prix',
                    value: _marketPriceLabel(read.marketData, live),
                  ),
                  _MarketSheetLine(
                    label: '24h',
                    value: _marketChangeLabel(read.marketData, live),
                  ),
                  _MarketSheetLine(
                    label: 'Fraîcheur',
                    value: live == null
                        ? _marketFreshnessLabel(read.marketData)
                        : _liveFreshnessLabel(live, connection),
                  ),
                  if (live != null)
                    const _MarketSheetLine(
                      label: 'Source du prix',
                      value: 'Kraken · WebSocket direct de l’app',
                    ),
                ],
              ),
            ),
            _MarketSheetLine(
              label: 'Direction',
              value: _directionLabel(read.summary.marketDirection),
            ),
            _MarketSheetLine(
              label: 'Edge',
              value: _edgeLabel(read.edgeState),
            ),
            _MarketSheetLine(
              label: 'Crowding',
              value: readableLabel(read.crowdingLevel),
            ),
            _MarketSheetLine(
              label: 'Volatilité',
              value: _volatilityLabel(read.volatilityRegime),
            ),
            if (timeframes != null) ...[
              const SizedBox(height: 14),
              const Text(
                'Unités de temps',
                style: TextStyle(
                  color: AppColors.text,
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 8),
              for (final tf in timeframes.timeframes)
                _MarketSheetLine(
                  label: tf.timeframe,
                  value: tf.available
                      ? '${tf.structureLabel} · ${_locationLabel(tf.location)}'
                      : tf.reasonUnavailable,
                ),
              if (timeframes.conflicts.isNotEmpty) ...[
                const SizedBox(height: 8),
                for (final conflict in timeframes.conflicts)
                  Text(
                    '• $conflict',
                    style: const TextStyle(
                      color: AppColors.warn,
                      fontSize: 14,
                      height: 1.35,
                    ),
                  ),
              ],
            ],
            if (impliedVolatility != null) ...[
              const SizedBox(height: 14),
              const Text(
                'Volatilité implicite',
                style: TextStyle(
                  color: AppColors.text,
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 8),
              if (!impliedVolatility.available)
                Text(
                  impliedVolatility.unavailableReason.isEmpty
                      ? 'Indisponible.'
                      : impliedVolatility.unavailableReason,
                  style: const TextStyle(
                    color: mobileMuted,
                    fontSize: 15,
                    height: 1.35,
                  ),
                )
              else ...[
                _MarketSheetLine(
                  label: 'DVOL',
                  value: fmtFr(impliedVolatility.dvol, digits: 1),
                ),
                _MarketSheetLine(
                  label: 'Prime',
                  value: signedFr(
                    impliedVolatility.variancePremium,
                    digits: 1,
                    suffix: ' pts',
                  ),
                ),
                Text(
                  impliedVolatility.interpretation,
                  style: const TextStyle(
                    color: mobileMuted,
                    fontSize: 15,
                    height: 1.35,
                  ),
                ),
              ],
            ],
          ],
        ),
      ),
    );
  }
}

class _MarketsData {
  final List<TodayRead> reads;
  final Map<String, dynamic>? ratios;
  final Map<String, dynamic>? breadth;
  final Map<String, dynamic>? liquidity;
  final Map<String, MultiTimeframeRead?> timeframes;
  final Map<String, ImpliedVolatilityRead?> impliedVolatility;

  const _MarketsData({
    required this.reads,
    required this.ratios,
    required this.breadth,
    required this.liquidity,
    required this.timeframes,
    required this.impliedVolatility,
  });
}

/// Market-wide context: ratios, breadth and financial conditions.
class _ContextPanel extends StatelessWidget {
  final Map<String, dynamic>? ratios;
  final Map<String, dynamic>? breadth;
  final Map<String, dynamic>? liquidity;

  const _ContextPanel({
    required this.ratios,
    required this.breadth,
    required this.liquidity,
  });

  @override
  Widget build(BuildContext context) {
    final dominance =
        (ratios?['btc_dominance'] as Map?)?.cast<String, dynamic>();
    final pairs = (ratios?['ratios'] as List?) ?? const [];

    return GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'CONTEXTE MARCHÉ',
            style: TextStyle(
              fontSize: 12.5,
              fontWeight: FontWeight.w800,
              letterSpacing: 1.1,
              color: mobileMuted,
            ),
          ),
          const SizedBox(height: 14),
          _line(
            'Participation',
            breadth == null
                ? '—'
                : '${breadth!['state']} (${breadth!['score']}/100)',
            hint: 'trois actifs seulement',
          ),
          _line(
            'Liquidité',
            liquidity == null ? '—' : '${liquidity!['regime']}',
          ),
          _line(
            'Dominance BTC',
            dominance == null || dominance['available'] != true
                ? 'INDISPONIBLE'
                : '${(dominance['btc_dominance_pct'] as num).toStringAsFixed(2)}%',
            hint: dominance?['available'] == true
                ? 'live, sans historique exploitable'
                : null,
          ),
          if (pairs.isNotEmpty) ...[
            const SizedBox(height: 10),
            for (final pair in pairs)
              _line(
                '${(pair as Map)['name']}',
                pair['change_30d_pct'] == null
                    ? '—'
                    : '${(pair['change_30d_pct'] as num) > 0 ? '+' : ''}'
                        '${(pair['change_30d_pct'] as num).toStringAsFixed(1)}% sur 30 j',
                hint: pair['trend'] == null
                    ? null
                    : '${pair['trend']}'.toLowerCase(),
              ),
          ],
        ],
      ),
    );
  }

  Widget _line(String label, String value, {String? hint}) => Padding(
        padding: const EdgeInsets.only(bottom: 9),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(label,
                      style:
                          const TextStyle(fontSize: 13.5, color: Colors.white)),
                  if (hint != null)
                    Text(hint,
                        style:
                            const TextStyle(fontSize: 11, color: mobileMuted)),
                ],
              ),
            ),
            Text(
              value,
              style: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w700,
                color: Color(0xFFDCE7F5),
              ),
            ),
          ],
        ),
      );
}

class _MarketLine extends StatelessWidget {
  final TodayRead read;
  final LivePriceSource? livePrices;
  final MultiTimeframeRead? timeframes;
  final ImpliedVolatilityRead? impliedVolatility;
  final VoidCallback onTap;

  const _MarketLine({
    required this.read,
    required this.livePrices,
    required this.onTap,
    this.timeframes,
    this.impliedVolatility,
  });

  @override
  Widget build(BuildContext context) {
    final bullish = read.summary.marketDirection.toUpperCase().contains('BULL');
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(17),
        onTap: onTap,
        child: LivePriceBuilder(
          source: livePrices,
          asset: read.asset,
          builder: (context, live, connection) => GlassPanel(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    CryptoLogo(asset: read.asset, size: 64),
                    const SizedBox(width: 18),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            read.asset,
                            style: const TextStyle(
                              color: AppColors.text,
                              fontSize: 28,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                          Text(
                            _assetName(read.asset),
                            style: const TextStyle(
                                color: mobileMuted, fontSize: 20),
                          ),
                        ],
                      ),
                    ),
                    MobilePill(
                      label: _marketPriceLabel(read.marketData, live),
                      color: mobileBlue,
                    ),
                  ],
                ),
                const SizedBox(height: 18),
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        _marketChangeLabel(read.marketData, live),
                        style: TextStyle(
                          color: _marketChangeColor(read.marketData, live),
                          fontSize: 17,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ),
                    Text(
                      live == null
                          ? _marketFreshnessShort(read.marketData)
                          : _liveFreshnessShort(connection),
                      style: const TextStyle(color: mobileMuted, fontSize: 12),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Text(
                  _statement(read),
                  style: const TextStyle(
                      color: AppColors.text, fontSize: 19, height: 1.32),
                ),
                const SizedBox(height: 18),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: [
                    MobilePill(
                        label: _directionLabel(read.summary.marketDirection),
                        color: bullish ? AppColors.measured : mobileBlue,
                        filled: bullish,
                        dense: true),
                    MobilePill(
                        label: _edgeLabel(read.edgeState),
                        color: AppColors.warn,
                        dense: true),
                    MobilePill(
                        label: readableLabel(read.crowdingLevel),
                        color: mobileBlue,
                        dense: true),
                    MobilePill(
                        label: _volatilityLabel(read.volatilityRegime),
                        color: const Color(0xFFBFD0FF),
                        dense: true),
                  ],
                ),
                if (timeframes != null) ...[
                  const SizedBox(height: 16),
                  _TimeframeStrip(reading: timeframes!),
                ],
                if (impliedVolatility != null) ...[
                  const SizedBox(height: 14),
                  _ImpliedVolatilityLine(reading: impliedVolatility!),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _MarketSheetLine extends StatelessWidget {
  final String label;
  final String value;

  const _MarketSheetLine({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 108,
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
                height: 1.3,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// One line per timeframe, with disagreements named rather than averaged.
class _TimeframeStrip extends StatelessWidget {
  final MultiTimeframeRead reading;

  const _TimeframeStrip({required this.reading});

  @override
  Widget build(BuildContext context) {
    final available = reading.timeframes.where((t) => t.available).toList();
    if (available.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Text(
              'UNITÉS DE TEMPS',
              style: TextStyle(
                fontSize: 11.5,
                fontWeight: FontWeight.w800,
                letterSpacing: 1,
                color: mobileMuted,
              ),
            ),
            const SizedBox(width: 10),
            MobilePill(
              label: reading.alignmentLabel,
              color:
                  reading.alignment == 'CONFLICT' ? AppColors.warn : mobileBlue,
              dense: true,
            ),
          ],
        ),
        const SizedBox(height: 9),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final tf in available)
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 11, vertical: 7),
                decoration: BoxDecoration(
                  color: mobilePanelAlt.withValues(alpha: 0.9),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: mobileBorder, width: 1.1),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      tf.timeframe,
                      style: const TextStyle(
                        fontSize: 12.5,
                        fontWeight: FontWeight.w800,
                        color: Colors.white,
                      ),
                    ),
                    Text(
                      tf.structureLabel,
                      style:
                          const TextStyle(fontSize: 11.5, color: mobileMuted),
                    ),
                  ],
                ),
              ),
          ],
        ),
        // A conflict between timeframes is the normal state of a market, so it
        // is stated plainly rather than hidden behind an average.
        for (final conflict in reading.conflicts)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              conflict,
              style: const TextStyle(
                fontSize: 11.5,
                color: AppColors.warn,
                height: 1.35,
              ),
            ),
          ),
      ],
    );
  }
}

/// Implied volatility against what actually happened.
class _ImpliedVolatilityLine extends StatelessWidget {
  final ImpliedVolatilityRead reading;

  const _ImpliedVolatilityLine({required this.reading});

  @override
  Widget build(BuildContext context) {
    if (!reading.available) {
      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'VOL. IMPLICITE',
            style: TextStyle(
              fontSize: 11.5,
              fontWeight: FontWeight.w800,
              letterSpacing: 1,
              color: mobileMuted,
            ),
          ),
          const SizedBox(width: 10),
          const Expanded(
            child: Text(
              'INDISPONIBLE — Deribit ne publie pas d’indice pour cet actif, '
              'et rien n’est substitué.',
              style: TextStyle(
                fontSize: 11.5,
                color: mobileMuted,
                fontStyle: FontStyle.italic,
                height: 1.35,
              ),
            ),
          ),
        ],
      );
    }

    final premium = reading.variancePremium;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Text(
              'VOL. IMPLICITE',
              style: TextStyle(
                fontSize: 11.5,
                fontWeight: FontWeight.w800,
                letterSpacing: 1,
                color: mobileMuted,
              ),
            ),
            const SizedBox(width: 10),
            MobilePill(
              label: 'options ${reading.pricingLabel}',
              color: mobileBlue,
              dense: true,
            ),
          ],
        ),
        const SizedBox(height: 7),
        Text(
          'DVOL ${reading.dvol?.toStringAsFixed(1) ?? '—'} '
          'contre ${reading.realisedVolAnnualised?.toStringAsFixed(1) ?? '—'} réalisé'
          '${premium == null ? '' : ' · prime ${premium > 0 ? '+' : ''}'
              '${premium.toStringAsFixed(1)} pts'}'
          '${reading.premiumPercentile == null ? '' : ' (p${reading.premiumPercentile!.toStringAsFixed(0)})'}',
          style: const TextStyle(
              fontSize: 12.5, color: Color(0xFFDCE7F5), height: 1.35),
        ),
        const SizedBox(height: 4),
        const Text(
          'Décrit le prix de la protection, pas une direction.',
          style: TextStyle(
            fontSize: 11,
            color: mobileMuted,
            fontStyle: FontStyle.italic,
          ),
        ),
      ],
    );
  }
}

String _assetName(String asset) => switch (asset) {
      'BTC' => 'Bitcoin',
      'ETH' => 'Ethereum',
      'SOL' => 'Solana',
      _ => asset,
    };

String _directionLabel(String value) => switch (value.toUpperCase()) {
      'STRONGLY_BULLISH' => 'FORTEMENT HAUSSIER',
      'BULLISH' => 'HAUSSIER',
      'BEARISH' => 'BAISSIER',
      'STRONGLY_BEARISH' => 'FORTEMENT BAISSIER',
      'RANGE' => 'RANGE',
      _ => readableLabel(value),
    };

String _marketPriceLabel(MarketPriceRead? market, [LivePriceTick? live]) {
  if (live != null) {
    return '€${_numberFr(
      live.priceEur,
      digits: live.priceEur >= 1000 ? 0 : 2,
    )}';
  }
  if (market == null || !market.available || market.displayPrice == null) {
    return 'INDISPONIBLE';
  }
  final value = market.displayPrice!;
  final symbol = market.displayUnit == 'EUR' ? '€' : r'$';
  return '$symbol${_numberFr(value, digits: value >= 1000 ? 0 : 2)}';
}

String _marketChangeLabel(MarketPriceRead? market, [LivePriceTick? live]) {
  final value = live?.change24hPct ?? market?.change24hPct;
  if (value == null || value.isNaN) return '24h indisponible';
  final sign = value > 0 ? '+' : '';
  return '$sign${_numberFr(value, digits: 1)} % sur 24 h';
}

Color _marketChangeColor(MarketPriceRead? market, [LivePriceTick? live]) {
  final value = live?.change24hPct ?? market?.change24hPct;
  if (value == null || value.isNaN) return mobileMuted;
  return value >= 0 ? AppColors.measured : AppColors.bad;
}

String _liveFreshnessShort(LivePriceConnection connection) =>
    connection == LivePriceConnection.live
        ? 'LIVE · Kraken · flux 0,5 s'
        : 'RECONNEXION · Kraken';

String _liveFreshnessLabel(
  LivePriceTick live,
  LivePriceConnection connection,
) {
  final elapsed = DateTime.now().toUtc().difference(live.receivedAt);
  final seconds = elapsed.isNegative ? 0 : elapsed.inSeconds;
  final prefix = connection == LivePriceConnection.live
      ? 'LIVE · flux 0,5 s'
      : 'RECONNEXION · dernier prix reçu';
  return '$prefix · Kraken · ${seconds}s';
}

String _marketFreshnessShort(MarketPriceRead? market) {
  if (market == null) return 'prix indisponible';
  String? provider;
  for (final item in market.providers) {
    if (item.status == 'OK' && item.price != null) {
      provider = _providerSourceLabel(item);
      break;
    }
  }
  final source = provider == null ? '' : ' · $provider';
  return '${_dataStatusLabel(market.status)}$source';
}

String _marketFreshnessLabel(MarketPriceRead? market) {
  if (market == null) return 'INDISPONIBLE';
  final age = market.ageSeconds == null
      ? ''
      : ' · âge ${_ageLabel(market.ageSeconds!)}';
  final asOf =
      market.asOf == null ? '' : ' · as_of ${_dateTimeLabel(market.asOf!)}';
  return '${_dataStatusLabel(market.status)}$age$asOf';
}

String _providerSourceLabel(MarketProviderRead provider) {
  final raw = provider.source.isEmpty ? provider.provider : provider.source;
  if (provider.provider == 'fixtures' ||
      raw.toUpperCase().contains('MOCK FIXTURES')) {
    return 'fixtures hors ligne';
  }
  return raw;
}

String _dataStatusLabel(String raw) => switch (raw.toUpperCase()) {
      'LIVE' => 'LIVE',
      'DELAYED' => 'RETARDÉ',
      'SNAPSHOT' => 'INSTANTANÉ',
      'STALE' => 'PÉRIMÉ',
      'UNAVAILABLE' => 'INDISPONIBLE',
      'ERROR' => 'ERREUR',
      _ => raw.replaceAll('_', ' '),
    };

String _ageLabel(double seconds) {
  final value = seconds.round();
  if (value < 60) return '${value}s';
  if (value < 3600) return '${(value / 60).round()} min';
  if (value < 86400) return '${(value / 3600).round()} h';
  return '${(value / 86400).round()} j';
}

String _dateTimeLabel(String raw) {
  final parsed = DateTime.tryParse(raw);
  if (parsed == null) return raw;
  final local = parsed.toLocal();
  final minute = local.minute.toString().padLeft(2, '0');
  return '${local.day}/${local.month}/${local.year} ${local.hour}:$minute';
}

String _numberFr(num value, {int digits = 2}) {
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

String _statement(TodayRead read) {
  if (read.summary.statement.isEmpty) return 'Aucune synthèse disponible.';
  final direction = read.summary.marketDirection.toUpperCase();
  if (read.summary.statement.contains('strongly bullish')) {
    return '${read.asset} est fortement haussier, mais nous n’avons actuellement aucun edge directionnel robuste.';
  }
  if (read.summary.statement.contains('strongly bearish')) {
    return '${read.asset} est fortement baissier, mais nous n’avons actuellement aucun edge directionnel robuste.';
  }
  if (direction.contains('BULLISH')) {
    return '${read.asset} est haussier, mais nous n’avons actuellement aucun edge directionnel robuste.';
  }
  if (direction.contains('BEARISH')) {
    return '${read.asset} est baissier, mais nous n’avons actuellement aucun edge directionnel robuste.';
  }
  return read.summary.statement;
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

String _locationLabel(String raw) => switch (raw.toUpperCase()) {
      'NEAR_RANGE_TOP' => 'proche du haut du range',
      'NEAR_RANGE_BOTTOM' => 'proche du bas du range',
      'MID_RANGE' => 'milieu du range',
      'ABOVE_RANGE' => 'au-dessus du range',
      'BELOW_RANGE' => 'sous le range',
      'NO_VALID_RANGE' => 'aucun range valide',
      _ => readableLabel(raw).toLowerCase(),
    };

String _volatilityLabel(String raw) => switch (raw.toUpperCase()) {
      'LOW' => 'FAIBLE',
      'VERY_LOW' => 'TRÈS FAIBLE',
      'NORMAL' => 'NORMALE',
      'MODERATE' => 'MODÉRÉE',
      'HIGH' => 'ÉLEVÉE',
      'EXTREME' => 'EXTRÊME',
      _ => readableLabel(raw),
    };
