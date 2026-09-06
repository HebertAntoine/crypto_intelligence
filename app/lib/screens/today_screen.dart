/// "Today" - the screen that must be readable in ten seconds.
///
/// Direction and measured edge sit on either side of a divider so the pairing
/// reads as two answers, never one verdict. The sentence at the top is the
/// whole system's output in one line:
///
///   "BTC is strongly bullish, but we currently hold no robust directional edge."
library;
import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../config.dart';
import '../theme/app_theme.dart';
import '../widgets/common.dart';

class TodayScreen extends StatefulWidget {
  final ApiClient client;

  const TodayScreen({super.key, required this.client});

  @override
  State<TodayScreen> createState() => _TodayScreenState();
}

class _TodayScreenState extends State<TodayScreen> {
  late Future<List<TodayRead>> _future;

  static const _assets = ['BTC', 'ETH', 'SOL'];

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
    return RefreshIndicator(
      onRefresh: () async => _reload(),
      child: FutureBuilder<List<TodayRead>>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const LoadingView(what: "today's read");
          }
          if (snapshot.hasError) {
            return ErrorView(error: snapshot.error!, onRetry: _reload);
          }
          final reads = snapshot.data ?? const [];
          return ListView(
            padding: const EdgeInsets.only(bottom: 24),
            children: [
              for (final read in reads) _AssetCard(read: read),
              const _DisclaimerCard(),
            ],
          );
        },
      ),
    );
  }
}

class _AssetCard extends StatelessWidget {
  final TodayRead read;

  const _AssetCard({required this.read});

  Color _directionColor(String direction) {
    // Deliberately NOT green: green is reserved for a measured edge, so a
    // bullish market never visually reads as verified evidence.
    if (direction.contains('BULLISH')) return AppColors.accent;
    if (direction.contains('BEARISH')) return AppColors.bad;
    return AppColors.textMuted;
  }

  Color _uncertaintyColor(String level) => switch (level) {
        'LOW' => AppColors.measured,
        'MODERATE' => AppColors.accent,
        _ => AppColors.warn,
      };

  @override
  Widget build(BuildContext context) {
    final summary = read.summary;
    return SectionCard(
      title: read.asset,
      trailing: EdgeBadge(state: read.edgeState, compact: true),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.only(left: 10),
            decoration: const BoxDecoration(
              border: Border(left: BorderSide(color: AppColors.accent, width: 3)),
            ),
            child: Text(
              summary.statement,
              style: const TextStyle(fontSize: 14.5, height: 1.45),
            ),
          ),
          const SizedBox(height: 14),

          // Direction | edge, separated so they read as two questions.
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: _MiniStat(
                  label: 'Market direction',
                  note: 'held ${summary.directionConfidence}% of last 20 days',
                  child: StatePill(
                    label: summary.marketDirection,
                    color: _directionColor(summary.marketDirection),
                    compact: true,
                  ),
                ),
              ),
              Container(
                width: 1,
                height: 54,
                margin: const EdgeInsets.symmetric(horizontal: 12),
                color: AppColors.border,
              ),
              Expanded(
                child: _MiniStat(
                  label: 'Measured edge',
                  note: '${read.admittedCount} admitted, ${read.rejectedCount} rejected',
                  child: EdgeBadge(state: read.edgeState, compact: true),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          const Divider(height: 1),
          const SizedBox(height: 10),

          LabelledRow(
            label: 'Crowding',
            value: Row(
              children: [
                StatePill(label: read.crowdingLevel, compact: true),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'direction ${read.crowdingDirection} — open interest has two sides',
                    style: const TextStyle(fontSize: 11, color: AppColors.textMuted),
                  ),
                ),
              ],
            ),
          ),
          LabelledRow(
            label: 'Leverage state',
            value: Text(read.leverageState.replaceAll('_', ' ')),
          ),
          LabelledRow(
            label: 'Funding',
            value: Text(
              read.fundingPercentile == null
                  ? read.fundingBand
                  : '${read.fundingBand} (p${read.fundingPercentile!.toStringAsFixed(0)})',
            ),
          ),
          LabelledRow(
            label: 'Volatility',
            value: Text(read.volatilityRegime.replaceAll('_', ' ')),
          ),
          LabelledRow(
            label: 'Uncertainty',
            value: StatePill(
              label: '${read.uncertaintyLevel} ${read.uncertaintyScore.toStringAsFixed(0)}/100',
              color: _uncertaintyColor(read.uncertaintyLevel),
              compact: true,
            ),
          ),
          LabelledRow(
            label: 'Actionable',
            value: Text(
              summary.actionable ? 'yes' : 'no',
              style: TextStyle(
                color: summary.actionable ? AppColors.measured : AppColors.textMuted,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),

          const SizedBox(height: 10),
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            childrenPadding: const EdgeInsets.only(bottom: 8),
            shape: const Border(),
            collapsedShape: const Border(),
            title: const Text(
              'Why this verdict',
              style: TextStyle(fontSize: 12.5, color: AppColors.textMuted),
            ),
            children: [
              Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  read.edgeStatement,
                  style: const TextStyle(fontSize: 12, color: AppColors.textMuted, height: 1.4),
                ),
              ),
              const SizedBox(height: 10),
              for (final driver in read.uncertaintyDrivers.take(3))
                Align(
                  alignment: Alignment.centerLeft,
                  child: Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Text(
                      '+${driver.contribution}  ${driver.driver} — ${driver.detail}',
                      style: const TextStyle(fontSize: 11.5, color: AppColors.textMuted),
                    ),
                  ),
                ),
              const SizedBox(height: 8),
              for (final caveat in summary.caveats)
                Align(
                  alignment: Alignment.centerLeft,
                  child: Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Text(
                      '• $caveat',
                      style: const TextStyle(
                        fontSize: 11.5,
                        color: AppColors.textMuted,
                        fontStyle: FontStyle.italic,
                        height: 1.35,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _MiniStat extends StatelessWidget {
  final String label;
  final Widget child;
  final String note;

  const _MiniStat({required this.label, required this.note, required this.child});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(fontSize: 11, color: AppColors.textMuted)),
        const SizedBox(height: 6),
        child,
        const SizedBox(height: 5),
        Text(note, style: const TextStyle(fontSize: 10.5, color: AppColors.textMuted)),
      ],
    );
  }
}

class _DisclaimerCard extends StatelessWidget {
  const _DisclaimerCard();

  @override
  Widget build(BuildContext context) {
    return Card(
      color: AppColors.surfaceAlt,
      child: const Padding(
        padding: EdgeInsets.all(14),
        child: Text(
          AppConfig.disclaimer,
          style: TextStyle(fontSize: 11.5, color: AppColors.textMuted, height: 1.4),
        ),
      ),
    );
  }
}
