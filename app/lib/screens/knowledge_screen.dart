/// Trader Knowledge: what sources claim, beside what the data shows.
///
/// The confrontation is the point. Where theory and measurement disagree, both
/// are displayed - hiding the disagreement would defeat the reason for
/// collecting the claim.
library;
import 'package:flutter/material.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';
import '../widgets/common.dart';

class KnowledgeScreen extends StatefulWidget {
  final ApiClient client;

  const KnowledgeScreen({super.key, required this.client});

  @override
  State<KnowledgeScreen> createState() => _KnowledgeScreenState();
}

class _KnowledgeScreenState extends State<KnowledgeScreen> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>> _load() async {
    Future<Map<String, dynamic>?> safe(Future<Map<String, dynamic>> f) async {
      try {
        return await f;
      } catch (_) {
        return null;
      }
    }

    final results = await Future.wait([
      safe(widget.client.educationalClaims()),
      safe(widget.client.claimValidation()),
      safe(widget.client.datasetQuality()),
      safe(widget.client.sourceHierarchy()),
    ]);
    return {
      'claims': results[0],
      'validation': results[1],
      'dataset': results[2],
      'hierarchy': results[3],
    };
  }

  void _reload() => setState(() => _future = _load());

  Color _verdictColour(String verdict) => switch (verdict) {
        'SUPPORTED' => AppColors.measured,
        'CONTRADICTED' => AppColors.bad,
        'PARTIALLY_SUPPORTED' => AppColors.accent,
        _ => AppColors.textMuted,
      };

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () async => _reload(),
      child: FutureBuilder<Map<String, dynamic>>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const LoadingView(what: 'trader knowledge');
          }
          if (snapshot.hasError) {
            return ErrorView(error: snapshot.error!, onRetry: _reload);
          }
          final data = snapshot.data!;
          final claims = data['claims'] as Map<String, dynamic>?;
          final validation = data['validation'] as Map<String, dynamic>?;
          final dataset = data['dataset'] as Map<String, dynamic>?;
          final hierarchy = data['hierarchy'] as Map<String, dynamic>?;

          // concept -> per-asset verdicts
          final verdicts = <String, List<Map<String, dynamic>>>{};
          for (final assetResult
              in ((validation?['results'] as Map?)?.values ?? const [])) {
            for (final claim in ((assetResult as Map)['claims'] as List? ?? const [])) {
              final concept = '${(claim as Map)['concept']}';
              verdicts.putIfAbsent(concept, () => []).add(claim.cast<String, dynamic>());
            }
          }

          return ListView(
            padding: const EdgeInsets.only(bottom: 24),
            children: [
              _HierarchyCard(hierarchy: hierarchy),
              SectionCard(
                title: 'THEORY VERSUS DATA',
                subtitle: claims?['note'] as String?,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (claims == null)
                      const UnavailableText(reason: 'Claims not available.')
                    else
                      for (final claim in (claims['claims'] as List? ?? const [])
                          .where((c) => (c as Map)['claim_type'] == 'EDUCATIONAL_CLAIM'))
                        _ClaimRow(
                          claim: (claim as Map).cast<String, dynamic>(),
                          measured: verdicts['${claim['concept']}'] ?? const [],
                          colourOf: _verdictColour,
                        ),
                  ],
                ),
              ),
              _DatasetCard(dataset: dataset),
            ],
          );
        },
      ),
    );
  }
}

class _HierarchyCard extends StatelessWidget {
  final Map<String, dynamic>? hierarchy;

  const _HierarchyCard({required this.hierarchy});

  @override
  Widget build(BuildContext context) {
    if (hierarchy == null) {
      return const SectionCard(
        title: 'SOURCE HIERARCHY',
        child: UnavailableText(),
      );
    }
    final tiers = (hierarchy!['tiers'] as Map?)?.cast<String, dynamic>() ?? const {};
    return SectionCard(
      title: 'SOURCE HIERARCHY',
      subtitle: hierarchy!['rule'] as String?,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final entry in tiers.entries)
            LabelledRow(
              label: 'Tier ${entry.key}',
              value: Row(
                children: [
                  Expanded(child: Text('${(entry.value as Map)['label']}')),
                  StatePill(
                    label: (entry.value as Map)['is_primary_data'] == true
                        ? 'data'
                        : 'claims only',
                    color: (entry.value as Map)['is_primary_data'] == true
                        ? AppColors.measured
                        : AppColors.textMuted,
                    compact: true,
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _ClaimRow extends StatelessWidget {
  final Map<String, dynamic> claim;
  final List<Map<String, dynamic>> measured;
  final Color Function(String) colourOf;

  const _ClaimRow({
    required this.claim,
    required this.measured,
    required this.colourOf,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${claim['concept']}'.replaceAll('_', ' '),
            style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 2),
          Text(
            '${claim['statement']}',
            style: const TextStyle(fontSize: 11.5, color: AppColors.textMuted, height: 1.3),
          ),
          const SizedBox(height: 5),
          if (measured.isEmpty)
            const Text(
              'not tested',
              style: TextStyle(fontSize: 11, color: AppColors.textMuted, fontStyle: FontStyle.italic),
            )
          else
            Wrap(
              spacing: 6,
              runSpacing: 4,
              children: [
                for (final entry in measured)
                  StatePill(
                    label: '${entry['asset']} ${entry['verdict']}',
                    color: colourOf('${entry['verdict']}'),
                    compact: true,
                  ),
              ],
            ),
        ],
      ),
    );
  }
}

class _DatasetCard extends StatelessWidget {
  final Map<String, dynamic>? dataset;

  const _DatasetCard({required this.dataset});

  @override
  Widget build(BuildContext context) {
    if (dataset == null) {
      return const SectionCard(title: 'HUMAN EXAMPLES', child: UnavailableText());
    }
    if (dataset!['status'] == 'EMPTY') {
      return SectionCard(
        title: 'HUMAN EXAMPLES',
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${dataset!['note']}', style: const TextStyle(fontSize: 12, height: 1.4)),
            const SizedBox(height: 6),
            Text(
              'Target: ${dataset!['target']}',
              style: const TextStyle(fontSize: 11.5, color: AppColors.textMuted),
            ),
          ],
        ),
      );
    }
    return SectionCard(
      title: 'HUMAN EXAMPLES',
      subtitle: dataset!['note'] as String?,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          LabelledRow(label: 'Examples', value: Text('${dataset!['number_examples']}')),
          LabelledRow(label: 'Market episodes', value: Text('${dataset!['market_episodes']}')),
          LabelledRow(
            label: 'Effective sample',
            value: Text('${dataset!['effective_sample_size']}'),
          ),
          LabelledRow(label: 'Human verified', value: Text('${dataset!['human_verified']}')),
        ],
      ),
    );
  }
}
