/// Ecran "Marches".
///
/// Vue courte pour conserver la navigation mobile complete tout en restant
/// alignee avec la source backend.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../widgets/common.dart';
import '../widgets/mobile_kit.dart';

class MarketsScreen extends StatefulWidget {
  final ApiClient client;

  const MarketsScreen({super.key, required this.client});

  @override
  State<MarketsScreen> createState() => _MarketsScreenState();
}

class _MarketsScreenState extends State<MarketsScreen> {
  static const _assets = ['BTC', 'ETH', 'SOL'];
  late Future<List<TodayRead>> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.client.todayAll(_assets);
  }

  void _reload() {
    setState(() => _future = widget.client.todayAll(_assets));
  }

  @override
  Widget build(BuildContext context) {
    return MobileGradientFrame(
      child: RefreshIndicator(
        onRefresh: () async => _reload(),
        child: FutureBuilder<List<TodayRead>>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const LoadingView(what: 'marchés');
            }
            if (snapshot.hasError) {
              return ErrorView(error: snapshot.error!, onRetry: _reload);
            }

            final reads = snapshot.data ?? const [];
            return ListView(
              padding: const EdgeInsets.fromLTRB(30, 30, 30, 178),
              children: [
                MobileHeader(
                  title: 'Marchés',
                  subtitle: 'Vue rapide des actifs',
                  onInfo: () => _showInfo(context),
                ),
                const SizedBox(height: 24),
                for (final read in reads) ...[
                  _MarketLine(read: read),
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
}

class _MarketLine extends StatelessWidget {
  final TodayRead read;

  const _MarketLine({required this.read});

  @override
  Widget build(BuildContext context) {
    final bullish = read.summary.marketDirection.toUpperCase().contains('BULL');
    return GlassPanel(
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
                      style: const TextStyle(color: mobileMuted, fontSize: 20),
                    ),
                  ],
                ),
              ),
              MobilePill(
                label: _directionLabel(read.summary.marketDirection),
                color: bullish ? AppColors.measured : mobileBlue,
                filled: bullish,
              ),
            ],
          ),
          const SizedBox(height: 18),
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
        ],
      ),
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

String _volatilityLabel(String raw) => switch (raw.toUpperCase()) {
      'LOW' => 'FAIBLE',
      'VERY_LOW' => 'TRÈS FAIBLE',
      'NORMAL' => 'NORMALE',
      'MODERATE' => 'MODÉRÉE',
      'HIGH' => 'ÉLEVÉE',
      'EXTREME' => 'EXTRÊME',
      _ => readableLabel(raw),
    };
