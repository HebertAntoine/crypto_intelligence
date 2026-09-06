/// Research: what the system measured about itself.
///
/// Negative results are shown as prominently as positive ones. The headline
/// figure is deliberately the ratio - how many hypotheses were tested versus
/// how many survived - because that ratio is what makes a surviving result
/// meaningful.
library;
import 'package:flutter/material.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';
import '../widgets/common.dart';

class ResearchScreen extends StatefulWidget {
  final ApiClient client;

  const ResearchScreen({super.key, required this.client});

  @override
  State<ResearchScreen> createState() => _ResearchScreenState();
}

class _ResearchScreenState extends State<ResearchScreen> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>> _load() async {
    // Each study is optional: a missing one is reported, not fatal.
    Future<Map<String, dynamic>?> safe(Future<Map<String, dynamic>> f) async {
      try {
        return await f;
      } catch (_) {
        return null;
      }
    }

    final results = await Future.wait([
      safe(widget.client.marginalValue()),
      safe(widget.client.structuralResearch()),
      safe(widget.client.replication()),
    ]);
    return {
      'marginal': results[0],
      'structural': results[1],
      'replication': results[2],
    };
  }

  void _reload() => setState(() => _future = _load());

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () async => _reload(),
      child: FutureBuilder<Map<String, dynamic>>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const LoadingView(what: 'resultats de recherche');
          }
          if (snapshot.hasError) {
            return ErrorView(error: snapshot.error!, onRetry: _reload);
          }
          final data = snapshot.data!;
          return ListView(
            padding: const EdgeInsets.only(bottom: 24),
            children: [
              _MarginalCard(data: data['marginal'] as Map<String, dynamic>?),
              _StructuralCard(data: data['structural'] as Map<String, dynamic>?),
              _ReplicationCard(data: data['replication'] as Map<String, dynamic>?),
            ],
          );
        },
      ),
    );
  }
}

class _MarginalCard extends StatelessWidget {
  final Map<String, dynamic>? data;

  const _MarginalCard({required this.data});

  @override
  Widget build(BuildContext context) {
    if (data == null) {
      return const SectionCard(
        title: 'LA LECTURE GRAPHIQUE AJOUTE-T-ELLE QUELQUE CHOSE ?',
        child: UnavailableText(reason: 'Etude pas encore lancee sur ce backend.'),
      );
    }
    final assets = (data!['assets'] as Map?)?.cast<String, dynamic>() ?? const {};
    return SectionCard(
      title: 'LA LECTURE GRAPHIQUE AJOUTE-T-ELLE QUELQUE CHOSE ?',
      subtitle:
          'Position dans le range et figures comparees a des variables numeriques simples, hors echantillon.',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final entry in assets.entries)
            _MarginalAsset(asset: entry.key, payload: entry.value as Map<String, dynamic>),
        ],
      ),
    );
  }
}

class _MarginalAsset extends StatelessWidget {
  final String asset;
  final Map<String, dynamic> payload;

  const _MarginalAsset({required this.asset, required this.payload});

  @override
  Widget build(BuildContext context) {
    final layers = (payload['layers'] as Map?)?.cast<String, dynamic>();
    final marginal = (payload['location_marginal_value'] as Map?)?.cast<String, dynamic>();
    final layerMap = (layers?['layers'] as Map?)?.cast<String, dynamic>() ?? const {};
    final verdict = (layers?['verdict'] as Map?)?.cast<String, dynamic>();
    final answer = (marginal?['answer'] as Map?)?.cast<String, dynamic>();

    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(asset, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
          const SizedBox(height: 6),
          for (final entry in layerMap.entries)
            if ((entry.value as Map)['status'] == 'OK')
              LabelledRow(
                label: entry.key.replaceAll('_', ' '),
                value: Text(
                  'OOS R² ${fmtSigned(((entry.value as Map)['oos_r2'] as num?)?.toDouble(), digits: 4, suffix: '')}',
                  style: TextStyle(
                    color: ((entry.value as Map)['oos_r2'] as num? ?? -1) > 0
                        ? AppColors.measured
                        : AppColors.bad,
                  ),
                ),
              ),
          if (verdict != null) ...[
            const SizedBox(height: 4),
            StatePill(label: '${verdict['answer']}', color: AppColors.warn, compact: true),
            const SizedBox(height: 4),
            Text(
              '${verdict['summary']}',
              style: const TextStyle(fontSize: 11.5, color: AppColors.textMuted, height: 1.35),
            ),
          ],
          if (answer != null) ...[
            const SizedBox(height: 8),
            Text(
              '${answer['statement']}',
              style: const TextStyle(fontSize: 11.5, height: 1.4),
            ),
          ],
        ],
      ),
    );
  }
}

class _StructuralCard extends StatelessWidget {
  final Map<String, dynamic>? data;

  const _StructuralCard({required this.data});

  @override
  Widget build(BuildContext context) {
    if (data == null) {
      return const SectionCard(
        title: 'HYPOTHESES STRUCTURELLES',
        child: UnavailableText(reason: 'Etude pas encore lancee sur ce backend.'),
      );
    }
    final results = (data!['results'] as Map?)?.cast<String, dynamic>() ?? const {};
    return SectionCard(
      title: 'HYPOTHESES STRUCTURELLES',
      subtitle: 'Chaque label est teste contre une base adaptee au regime, avec FDR.',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final entry in results.entries)
            if ((entry.value as Map)['status'] == 'OK')
              _StructuralRow(
                key_: entry.key,
                payload: (entry.value as Map).cast<String, dynamic>(),
              ),
        ],
      ),
    );
  }
}

class _StructuralRow extends StatelessWidget {
  final String key_;
  final Map<String, dynamic> payload;

  const _StructuralRow({required this.key_, required this.payload});

  @override
  Widget build(BuildContext context) {
    final testing = (payload['multiple_testing'] as Map?)?.cast<String, dynamic>() ?? const {};
    final labels = (payload['labels'] as Map?)?.cast<String, dynamic>() ?? const {};
    final edges = labels.entries
        .where((e) => ['POSITIVE_EDGE', 'NEGATIVE_EDGE']
            .contains((e.value as Map)['edge_state']))
        .toList();

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(key_, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
          const SizedBox(height: 4),
          Text(
            '${testing['hypotheses_tested']} hypotheses · '
            '${testing['raw_significant']} brutes · '
            '${testing['fdr_significant']} apres FDR · '
            '${testing['expected_false_positives']} faux positifs attendus',
            style: const TextStyle(fontSize: 11.5, color: AppColors.textMuted),
          ),
          const SizedBox(height: 6),
          if (edges.isEmpty)
            const Text(
              'Aucun label ne passe tous les filtres.',
              style: TextStyle(fontSize: 12, color: AppColors.warn),
            )
          else
            for (final entry in edges)
              Padding(
                padding: const EdgeInsets.only(bottom: 3),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Text(
                        entry.key.replaceAll('|', ' · '),
                        style: const TextStyle(fontSize: 12),
                      ),
                    ),
                    StatePill(
                      label: '${(entry.value as Map)['edge_state']}',
                      color: (entry.value as Map)['edge_state'] == 'POSITIVE_EDGE'
                          ? AppColors.measured
                          : AppColors.bad,
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

class _ReplicationCard extends StatelessWidget {
  final Map<String, dynamic>? data;

  const _ReplicationCard({required this.data});

  @override
  Widget build(BuildContext context) {
    if (data == null) {
      return const SectionCard(
        title: 'REPLICATION',
        child: UnavailableText(reason: 'Etude pas encore lancee sur ce backend.'),
      );
    }
    final findings = (data!['findings'] as Map?)?.cast<String, dynamic>() ?? const {};
    return SectionCard(
      title: 'REPLICATION',
      subtitle: 'Les resultats precedents survivent-ils a un changement de definition du detecteur ?',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final entry in findings.entries)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    entry.key.replaceAll('_', ' '),
                    style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 3),
                  StatePill(
                    label: '${((entry.value as Map)['comparison'] as Map?)?['verdict'] ?? '—'}',
                    compact: true,
                  ),
                  const SizedBox(height: 3),
                  Text(
                    '${((entry.value as Map)['comparison'] as Map?)?['statement'] ?? ''}',
                    style: const TextStyle(fontSize: 11.5, color: AppColors.textMuted, height: 1.35),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
