/// Preuves: jusqu'où chaque affirmation est réellement montée.
///
/// L'écran est construit pour rendre un résultat négatif lisible. Un verdict
/// n'est jamais affiché seul: il arrive avec l'entonnoir qui l'a produit et le
/// plancher de détection en dessous duquel «rien trouvé» ne veut rien dire.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';
import '../widgets/common.dart';
import '../widgets/mobile_kit.dart';

class EvidenceScreen extends StatefulWidget {
  final ApiClient client;

  const EvidenceScreen({super.key, required this.client});

  @override
  State<EvidenceScreen> createState() => _EvidenceScreenState();
}

class _EvidenceScreenState extends State<EvidenceScreen> {
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
      safe(widget.client.evidence()),
      safe(widget.client.power()),
      safe(widget.client.pooling()),
    ]);
    return {
      'evidence': results[0],
      'power': results[1],
      'pooling': results[2],
    };
  }

  void _reload() => setState(() => _future = _load());

  @override
  Widget build(BuildContext context) {
    return MobileGradientFrame(
      child: RefreshIndicator(
        onRefresh: () async => _reload(),
        child: FutureBuilder<Map<String, dynamic>>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const LoadingView(what: 'les preuves');
            }
            if (snapshot.hasError) {
              return ErrorView(message: '${snapshot.error}', onRetry: _reload);
            }
            final data = snapshot.data ?? const {};
            final evidence = data['evidence'] as Map<String, dynamic>?;
            final power = data['power'] as Map<String, dynamic>?;
            final pooling = data['pooling'] as Map<String, dynamic>?;

            return MobileScrollView(
              padding: const EdgeInsets.fromLTRB(20, 28, 20, 120),
              children: [
                const MobileHeader(
                  title: 'Preuves',
                  subtitle: 'Ce que les données soutiennent réellement',
                ),
                const SizedBox(height: 18),
                if (evidence == null)
                  const SectionCard(
                    title: 'ÉTUDE NON GÉNÉRÉE',
                    child: UnavailableText(
                      reason:
                          'Lancez «crypto-intel lot6b» pour produire l’analyse.',
                    ),
                  )
                else ...[
                  _VerdictCard(evidence: evidence),
                  const SizedBox(height: 12),
                  _FunnelCard(funnel: evidence['funnel'] as Map<String, dynamic>?),
                  const SizedBox(height: 12),
                  _ShortlistCard(
                    shortlist: evidence['shortlist'] as Map<String, dynamic>?,
                  ),
                ],
                if (power != null) ...[
                  const SizedBox(height: 12),
                  _DetectionFloorCard(power: power),
                ],
                if (pooling != null) ...[
                  const SizedBox(height: 12),
                  _PoolingCard(pooling: pooling),
                ],
                const SizedBox(height: 12),
                const _LadderCard(),
              ],
            );
          },
        ),
      ),
    );
  }
}

/// Couleur par niveau: rien n'est vert avant le niveau actionnable.
Color _levelColour(int level) {
  if (level >= 6) return AppColors.measured;
  if (level >= 4) return AppColors.accent;
  if (level >= 2) return AppColors.warn;
  return AppColors.textMuted;
}

class _VerdictCard extends StatelessWidget {
  final Map<String, dynamic> evidence;

  const _VerdictCard({required this.evidence});

  @override
  Widget build(BuildContext context) {
    final verdict = '${evidence['verdict'] ?? 'INCONNU'}';
    final highest = (evidence['highest_level_reached'] as num?)?.toInt() ?? 0;
    final actionable = (evidence['n_actionable'] as num?)?.toInt() ?? 0;
    final byLevel = (evidence['by_level'] as Map?)?.cast<String, dynamic>() ?? {};

    return SectionCard(
      title: 'VERDICT DU LOT',
      trailing: StatePill(
        label: verdict,
        color: actionable > 0 ? AppColors.measured : AppColors.warn,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          LabelledRow(
            label: 'Niveau le plus haut',
            value: Text(
              '$highest / 7',
              style: TextStyle(
                color: _levelColour(highest),
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          LabelledRow(
            label: 'Actionnables',
            value: Text(
              '$actionable',
              style: TextStyle(
                color: actionable > 0 ? AppColors.measured : AppColors.textMuted,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          const SizedBox(height: 8),
          for (final entry in byLevel.entries)
            LabelledRow(
              label: entry.key,
              value: Text('${entry.value} hypothèse(s)'),
            ),
          const SizedBox(height: 10),
          const Text(
            'Une affirmation n’est actionnable qu’au niveau 6, et seulement si '
            'la puissance statistique suffit. Aucune ne l’atteint aujourd’hui.',
            style: TextStyle(fontSize: 11.5, color: AppColors.textMuted),
          ),
        ],
      ),
    );
  }
}

class _FunnelCard extends StatelessWidget {
  final Map<String, dynamic>? funnel;

  const _FunnelCard({required this.funnel});

  @override
  Widget build(BuildContext context) {
    final data = funnel;
    if (data == null) {
      return const SectionCard(
        title: 'ENTONNOIR',
        child: UnavailableText(reason: 'Entonnoir non disponible.'),
      );
    }
    final stages = (data['stages'] as List?) ?? const [];
    final start = (data['tests_started'] as num?)?.toDouble() ?? 1;
    final expected = data['expected_false_positives_at_alpha_05'];

    return SectionCard(
      title: 'ENTONNOIR DES TESTS',
      subtitle: 'Combien d’hypothèses ont survécu à chaque étape',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final stage in stages.cast<Map<String, dynamic>>())
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          '${stage['stage']}',
                          style: const TextStyle(fontSize: 12.5),
                        ),
                      ),
                      Text(
                        '${stage['count']}',
                        style: const TextStyle(
                          fontSize: 12.5,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(3),
                    child: LinearProgressIndicator(
                      value: start > 0
                          ? ((stage['count'] as num?)?.toDouble() ?? 0) / start
                          : 0,
                      minHeight: 5,
                      backgroundColor: AppColors.surfaceAlt,
                      valueColor: const AlwaysStoppedAnimation(AppColors.accent),
                    ),
                  ),
                ],
              ),
            ),
          const SizedBox(height: 10),
          if (expected != null)
            Text(
              'Le hasard seul produirait environ $expected résultat(s) '
              'apparent(s) à 5 %.',
              style: const TextStyle(fontSize: 11.5, color: AppColors.warn),
            ),
          const SizedBox(height: 6),
          Text(
            '${data['note'] ?? ''}',
            style: const TextStyle(fontSize: 11.5, color: AppColors.textMuted),
          ),
        ],
      ),
    );
  }
}

class _ShortlistCard extends StatelessWidget {
  final Map<String, dynamic>? shortlist;

  const _ShortlistCard({required this.shortlist});

  @override
  Widget build(BuildContext context) {
    final entries = (shortlist?['shortlist'] as List?) ?? const [];
    if (entries.isEmpty) {
      return const SectionCard(
        title: 'CANDIDATS',
        child: UnavailableText(
          reason: 'Aucun candidat n’a franchi le seuil d’entrée.',
        ),
      );
    }

    return SectionCard(
      title: 'CANDIDATS À SUIVRE',
      subtitle: 'Questions ouvertes, pas des recommandations',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final raw in entries.cast<Map<String, dynamic>>())
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 7,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: _levelColour(
                            (raw['evidence_level'] as num?)?.toInt() ?? 0,
                          ).withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          'N${raw['evidence_level']}',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            color: _levelColour(
                              (raw['evidence_level'] as num?)?.toInt() ?? 0,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          '${raw['claim']}',
                          style: const TextStyle(fontSize: 12.5),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 3),
                  Padding(
                    padding: const EdgeInsets.only(left: 38),
                    child: Text(
                      'effet ${_formatPct(raw['effect_pct'])} · '
                      'bloqué à ${raw['blocked_at'] ?? '-'}',
                      style: const TextStyle(
                        fontSize: 11.5,
                        color: AppColors.textMuted,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          const SizedBox(height: 8),
          Text(
            '${shortlist?['note'] ?? ''}',
            style: const TextStyle(fontSize: 11.5, color: AppColors.textMuted),
          ),
        ],
      ),
    );
  }
}

class _DetectionFloorCard extends StatelessWidget {
  final Map<String, dynamic> power;

  const _DetectionFloorCard({required this.power});

  @override
  Widget build(BuildContext context) {
    final floors = (power['detection_floors'] as List?) ?? const [];

    return SectionCard(
      title: 'PLANCHER DE DÉTECTION',
      subtitle: 'Le plus petit effet que ce pipeline sait certifier',
      trailing: StatePill(
        label: '${power['verdict'] ?? '-'}',
        color: AppColors.warn,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final raw in floors.cast<Map<String, dynamic>>())
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Row(
                children: [
                  SizedBox(
                    width: 56,
                    child: Text(
                      '${raw['horizon_days']} j',
                      style: const TextStyle(
                        fontSize: 12.5,
                        color: AppColors.textMuted,
                      ),
                    ),
                  ),
                  Expanded(
                    child: Text(
                      'plancher ${raw['empirical_floor_pct'] ?? '-'} %',
                      style: TextStyle(
                        fontSize: 12.5,
                        fontWeight: FontWeight.w700,
                        color: raw['floor_above_meaningful'] == true
                            ? AppColors.warn
                            : AppColors.measured,
                      ),
                    ),
                  ),
                  Text(
                    'seuil utile ${raw['meaningful_effect_pct'] ?? '-'} %',
                    style: const TextStyle(
                      fontSize: 11.5,
                      color: AppColors.textMuted,
                    ),
                  ),
                ],
              ),
            ),
          const SizedBox(height: 10),
          Text(
            '${power['note'] ?? ''}',
            style: const TextStyle(fontSize: 11.5, color: AppColors.textMuted),
          ),
        ],
      ),
    );
  }
}

class _PoolingCard extends StatelessWidget {
  final Map<String, dynamic> pooling;

  const _PoolingCard({required this.pooling});

  @override
  Widget build(BuildContext context) {
    final correlation = pooling['mean_cross_asset_correlation'];
    final unavailable =
        (pooling['assets_unavailable'] as Map?)?.cast<String, dynamic>() ?? {};
    final counts =
        (pooling['verdict_counts'] as Map?)?.cast<String, dynamic>() ?? {};

    return SectionCard(
      title: 'MISE EN COMMUN BTC + ETH',
      subtitle: 'Deux actifs ne font pas deux échantillons',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          LabelledRow(
            label: 'Corrélation moyenne',
            value: Text(
              correlation == null ? 'indisponible' : '$correlation',
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
          ),
          for (final entry in counts.entries)
            LabelledRow(label: entry.key, value: Text('${entry.value}')),
          for (final entry in unavailable.entries)
            LabelledRow(
              label: entry.key,
              value: Text(
                '${entry.value}',
                style: const TextStyle(color: AppColors.textMuted),
              ),
            ),
          const SizedBox(height: 8),
          const Text(
            'À 0,8 de corrélation, deux actifs portent l’information d’environ '
            '1,1 série indépendante. Le nombre de lignes double, pas '
            'l’information.',
            style: TextStyle(fontSize: 11.5, color: AppColors.textMuted),
          ),
        ],
      ),
    );
  }
}

class _LadderCard extends StatelessWidget {
  const _LadderCard();

  static const _levels = [
    (0, 'NON TESTÉ', 'déclaré, jamais exécuté'),
    (1, 'OBSERVÉ', 'une différence existe dans l’échantillon'),
    (2, 'RELATIF À UNE RÉFÉRENCE', 'survit à une référence conditionnée'),
    (3, 'STRATIFIÉ', 'survit à la stratification par régime'),
    (4, 'CONTRÔLÉ', 'survit à la résidualisation sur plis purgés'),
    (5, 'ROBUSTE', 'survit au retrait d’une année, d’un actif, d’un cycle'),
    (6, 'RÉPLIQUÉ', 'se reproduit sur des données non utilisées'),
    (7, 'CONFIRMÉ EN LIVE', 'confirmé sur des données futures'),
  ];

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      title: 'ÉCHELLE DE PREUVE',
      subtitle: 'Les barreaux sont cumulatifs et ordonnés',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final (level, name, meaning) in _levels)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 22,
                    height: 22,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: _levelColour(level).withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(5),
                    ),
                    child: Text(
                      '$level',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        color: _levelColour(level),
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          name,
                          style: const TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        Text(
                          meaning,
                          style: const TextStyle(
                            fontSize: 11.5,
                            color: AppColors.textMuted,
                          ),
                        ),
                      ],
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

String _formatPct(dynamic value) {
  if (value is num) {
    return '${value >= 0 ? '+' : ''}${value.toStringAsFixed(2)} %';
  }
  return '-';
}
