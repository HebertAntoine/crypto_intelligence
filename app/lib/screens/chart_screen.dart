/// Chart Intelligence: the structure the system sees, and what it verified.
///
/// Each pattern shows its recognition confidence and its edge state on the
/// same row. A 91/100 recognition next to NO_MEASURABLE_EDGE is the intended
/// reading: the shape is unambiguous and its consequences are unknown.
library;
import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../widgets/common.dart';

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
      // The structure is still worth showing without the opportunity read.
      opportunity = null;
    }
    return (structure, opportunity);
  }

  void _reload() => setState(() => _future = _load());

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _Selector(
          assets: _assets,
          timeframes: _timeframes,
          asset: _asset,
          timeframe: _timeframe,
          onAsset: (value) {
            setState(() => _asset = value);
            _reload();
          },
          onTimeframe: (value) {
            setState(() => _timeframe = value);
            _reload();
          },
        ),
        Expanded(
          child: FutureBuilder<(StructureRead, EntryOpportunity?)>(
            future: _future,
            builder: (context, snapshot) {
              if (snapshot.connectionState == ConnectionState.waiting) {
                return LoadingView(what: '$_asset $_timeframe structure');
              }
              if (snapshot.hasError) {
                return ErrorView(error: snapshot.error!, onRetry: _reload);
              }
              final (structure, opportunity) = snapshot.data!;
              return ListView(
                padding: const EdgeInsets.only(bottom: 24),
                children: [
                  if (opportunity != null) _OpportunityCard(opportunity: opportunity),
                  _RangeCard(location: structure.location),
                  _StructureCard(structure: structure.marketStructure),
                  _PatternsCard(
                    patterns: structure.patterns,
                    separationNote: structure.separationNote,
                  ),
                ],
              );
            },
          ),
        ),
      ],
    );
  }
}

class _Selector extends StatelessWidget {
  final List<String> assets;
  final List<String> timeframes;
  final String asset;
  final String timeframe;
  final ValueChanged<String> onAsset;
  final ValueChanged<String> onTimeframe;

  const _Selector({
    required this.assets,
    required this.timeframes,
    required this.asset,
    required this.timeframe,
    required this.onAsset,
    required this.onTimeframe,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
      child: Column(
        children: [
          Row(
            children: [
              for (final value in assets)
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: ChoiceChip(
                    label: Text(value),
                    selected: value == asset,
                    onSelected: (_) => onAsset(value),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 6),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                for (final value in timeframes)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                      label: Text(value),
                      selected: value == timeframe,
                      onSelected: (_) => onTimeframe(value),
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

class _OpportunityCard extends StatelessWidget {
  final EntryOpportunity opportunity;

  const _OpportunityCard({required this.opportunity});

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      title: 'ENTRY OPPORTUNITY',
      trailing: EdgeBadge(state: opportunity.measuredEdge, compact: true),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              StatePill(label: opportunity.state),
              const SizedBox(width: 8),
              if (opportunity.score != null)
                Text(
                  fmtSigned(opportunity.score, digits: 0, suffix: ''),
                  style: const TextStyle(fontSize: 12.5, color: AppColors.textMuted),
                ),
            ],
          ),
          const SizedBox(height: 12),

          // Invalidation comes first, before anything that sounds favourable.
          Container(
            padding: const EdgeInsets.only(left: 10),
            decoration: const BoxDecoration(
              border: Border(left: BorderSide(color: AppColors.warn, width: 3)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'What would invalidate this',
                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: AppColors.warn),
                ),
                const SizedBox(height: 3),
                Text(
                  opportunity.invalidation,
                  style: const TextStyle(fontSize: 12, height: 1.4),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),

          const Text(
            'Why now',
            style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: AppColors.textMuted),
          ),
          const SizedBox(height: 4),
          for (final reason in opportunity.whyNow)
            Padding(
              padding: const EdgeInsets.only(bottom: 3),
              child: Text('• $reason', style: const TextStyle(fontSize: 12, height: 1.35)),
            ),
          const SizedBox(height: 10),
          Text(
            opportunity.disclaimer,
            style: const TextStyle(
              fontSize: 11,
              color: AppColors.textMuted,
              fontStyle: FontStyle.italic,
              height: 1.35,
            ),
          ),
        ],
      ),
    );
  }
}

class _RangeCard extends StatelessWidget {
  final StructuralLocation location;

  const _RangeCard({required this.location});

  @override
  Widget build(BuildContext context) {
    final range = location.range;
    return SectionCard(
      title: 'RANGE & LOCATION',
      trailing: StatePill(label: location.state, compact: true),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (range == null || !range.valid) ...[
            UnavailableText(
              reason: range?.reason.isNotEmpty == true
                  ? range!.reason
                  : 'No validated range on this timeframe.',
            ),
          ] else ...[
            Text(location.rangeSummary, style: const TextStyle(fontSize: 12.5, height: 1.4)),
            const SizedBox(height: 12),
            _ZoneRow(zone: range.topZone, label: 'Top zone'),
            _ZoneRow(zone: range.bottomZone, label: 'Bottom zone'),
            const SizedBox(height: 8),
            LabelledRow(
              label: 'Position in range',
              value: Text(fmt(location.relativePosition, digits: 3)),
            ),
            LabelledRow(
              label: 'Distance to bottom',
              value: Text(fmt(location.distanceToBottomAtr, digits: 2, suffix: ' ATR')),
            ),
            LabelledRow(
              label: 'Distance to top',
              value: Text(fmt(location.distanceToTopAtr, digits: 2, suffix: ' ATR')),
            ),
            LabelledRow(
              label: 'Recognition',
              value: Text('${range.confidence.toStringAsFixed(0)}/100 — shape match only'),
            ),
            if (location.explanation.isNotEmpty) ...[
              const SizedBox(height: 10),
              const Text(
                'Why these are the boundaries',
                style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: AppColors.textMuted),
              ),
              const SizedBox(height: 4),
              for (final line in location.explanation)
                Padding(
                  padding: const EdgeInsets.only(bottom: 2),
                  child: Text('• $line', style: const TextStyle(fontSize: 11.5, color: AppColors.textMuted)),
                ),
            ],
          ],
          if (location.invalidation.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text(
              location.invalidation,
              style: const TextStyle(fontSize: 11.5, color: AppColors.warn, height: 1.35),
            ),
          ],
        ],
      ),
    );
  }
}

class _ZoneRow extends StatelessWidget {
  final Zone? zone;
  final String label;

  const _ZoneRow({required this.zone, required this.label});

  @override
  Widget build(BuildContext context) {
    if (zone == null) return LabelledRow(label: label, value: const UnavailableText());
    return LabelledRow(
      label: label,
      value: Text(
        '${zone!.low.toStringAsFixed(2)} – ${zone!.high.toStringAsFixed(2)}   '
        '(${zone!.quality.touches} touches, quality ${zone!.quality.score.toStringAsFixed(0)}/100)',
      ),
    );
  }
}

class _StructureCard extends StatelessWidget {
  final MarketStructure structure;

  const _StructureCard({required this.structure});

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      title: 'SWING STRUCTURE',
      trailing: StatePill(label: structure.state, compact: true),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(structure.interpretation, style: const TextStyle(fontSize: 12.5, height: 1.4)),
          const SizedBox(height: 10),
          LabelledRow(label: 'Last confirmed HH', value: Text(fmt(structure.lastConfirmedHh))),
          LabelledRow(label: 'Last confirmed HL', value: Text(fmt(structure.lastConfirmedHl))),
          LabelledRow(label: 'Last confirmed LH', value: Text(fmt(structure.lastConfirmedLh))),
          LabelledRow(label: 'Last confirmed LL', value: Text(fmt(structure.lastConfirmedLl))),
          if (structure.events.isNotEmpty) ...[
            const SizedBox(height: 10),
            for (final event in structure.events)
              Padding(
                padding: const EdgeInsets.only(bottom: 3),
                child: Text(
                  '${event.kind} ${event.direction} at ${event.level.toStringAsFixed(2)} '
                  '(confirmed ${event.confirmationTime.split('T').first})',
                  style: const TextStyle(fontSize: 11.5, color: AppColors.textMuted),
                ),
              ),
          ],
          const SizedBox(height: 10),
          Text(
            structure.caveat,
            style: const TextStyle(
              fontSize: 11,
              color: AppColors.textMuted,
              fontStyle: FontStyle.italic,
              height: 1.35,
            ),
          ),
        ],
      ),
    );
  }
}

class _PatternsCard extends StatelessWidget {
  final List<DetectedPattern> patterns;
  final String separationNote;

  const _PatternsCard({required this.patterns, required this.separationNote});

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      title: 'PATTERNS (${patterns.length})',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (patterns.isEmpty)
            const UnavailableText(
              reason: 'No pattern detected. This is the normal outcome most of the time.',
            )
          else
            for (final pattern in patterns) _PatternTile(pattern: pattern),
          if (separationNote.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              separationNote,
              style: const TextStyle(
                fontSize: 11,
                color: AppColors.textMuted,
                fontStyle: FontStyle.italic,
                height: 1.35,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _PatternTile extends StatelessWidget {
  final DetectedPattern pattern;

  const _PatternTile({required this.pattern});

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
      child: ExpansionTile(
        tilePadding: EdgeInsets.zero,
        childrenPadding: const EdgeInsets.only(left: 4, bottom: 10),
        title: Text(
          pattern.name.replaceAll('_', ' '),
          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
        ),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 5),
          child: Wrap(
            spacing: 6,
            runSpacing: 4,
            children: [
              StatePill(label: pattern.state, compact: true),
              StatePill(
                label: 'recognition ${pattern.recognitionConfidence.toStringAsFixed(0)}',
                color: AppColors.textMuted,
                compact: true,
              ),
              // Always beside the recognition score, never on its own line.
              EdgeBadge(state: pattern.edgeState, compact: true),
            ],
          ),
        ),
        children: [
          Align(
            alignment: Alignment.centerLeft,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                LabelledRow(
                  label: 'Detection class',
                  value: Text('${pattern.patternClass} — ${pattern.classHint}'),
                ),
                LabelledRow(
                  label: 'Textbook reading',
                  value: Text(pattern.directionIfTextbook),
                ),
                LabelledRow(
                  label: 'Measured edge',
                  value: EdgeBadge(state: pattern.edgeState, compact: true),
                ),
                for (final entry in pattern.keyLevels.entries)
                  LabelledRow(
                    label: entry.key.replaceAll('_', ' '),
                    value: Text(entry.value.toStringAsFixed(2)),
                  ),
                if (pattern.invalidationRule.isNotEmpty)
                  LabelledRow(
                    label: 'Invalidation',
                    value: Text(pattern.invalidationRule),
                  ),
                if (pattern.notes.isNotEmpty) ...[
                  const SizedBox(height: 6),
                  Text(
                    pattern.notes,
                    style: const TextStyle(fontSize: 11.5, color: AppColors.textMuted, height: 1.35),
                  ),
                ],
                const SizedBox(height: 6),
                Text(
                  pattern.separationNote,
                  style: const TextStyle(
                    fontSize: 10.5,
                    color: AppColors.textMuted,
                    fontStyle: FontStyle.italic,
                    height: 1.3,
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
