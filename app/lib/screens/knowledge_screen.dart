/// Connaissances trader: règles pédagogiques et hiérarchie des sources.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';
import '../widgets/common.dart';
import '../widgets/mobile_kit.dart';

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

  @override
  Widget build(BuildContext context) {
    return MobileGradientFrame(
      child: RefreshIndicator(
        onRefresh: () async => _reload(),
        child: FutureBuilder<Map<String, dynamic>>(
          future: _future,
          builder: (context, snapshot) {
            return ListView(
              padding: const EdgeInsets.fromLTRB(28, 28, 28, 28),
              children: [
                MobileHeader(
                  title: 'Connaissances trader',
                  subtitle: 'Règles de lecture et hiérarchie des sources',
                  onInfo: () => _showInfo(context),
                ),
                const SizedBox(height: 22),
                if (snapshot.connectionState == ConnectionState.waiting)
                  const SizedBox(
                    height: 440,
                    child: LoadingView(what: 'connaissances trader'),
                  )
                else if (snapshot.hasError)
                  SizedBox(
                    height: 440,
                    child: ErrorView(error: snapshot.error!, onRetry: _reload),
                  )
                else ...[
                  _HierarchyPanel(
                    hierarchy:
                        snapshot.data!['hierarchy'] as Map<String, dynamic>?,
                  ),
                  const SizedBox(height: 22),
                  _TheoryPanel(
                    claims: snapshot.data!['claims'] as Map<String, dynamic>?,
                    validation:
                        snapshot.data!['validation'] as Map<String, dynamic>?,
                  ),
                  const SizedBox(height: 90),
                  _HumanExamplesPanel(
                    dataset: snapshot.data!['dataset'] as Map<String, dynamic>?,
                  ),
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
        title: const Text('Connaissances trader'),
        content: const Text(
          'Les règles pédagogiques sont affichées comme des hypothèses. '
          'Elles ne peuvent pas remplacer une mesure empirique ou une donnée '
          'de meilleure qualité dans la hiérarchie des sources.',
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

class _HierarchyPanel extends StatelessWidget {
  final Map<String, dynamic>? hierarchy;

  const _HierarchyPanel({required this.hierarchy});

  @override
  Widget build(BuildContext context) {
    final tiers =
        (hierarchy?['tiers'] as Map?)?.cast<String, dynamic>() ?? const {};
    return GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const _RoundIcon(icon: Icons.layers_rounded),
              const SizedBox(width: 22),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: const [
                    Text(
                      'Hiérarchie des sources',
                      style: TextStyle(
                        color: AppColors.text,
                        fontSize: 26,
                        fontWeight: FontWeight.w800,
                        height: 1.1,
                      ),
                    ),
                    SizedBox(height: 8),
                    Text(
                      'Une source ne peut invalider qu’une source d’un niveau strictement inférieur. '
                      'En cas de désaccord entre sources de même niveau, le conflit est signalé, jamais masqué. '
                      'Les sources pédagogiques et humaines ne peuvent jamais écraser des données mesurées.',
                      style: TextStyle(
                          color: mobileMuted, fontSize: 18, height: 1.28),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 8),
            decoration: BoxDecoration(
              color: const Color(0xFF0C1725).withValues(alpha: 0.54),
              borderRadius: BorderRadius.circular(13),
              border: Border.all(color: const Color(0xFF2A4868), width: 1.1),
            ),
            child: Column(
              children: [
                if (tiers.isEmpty)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 12),
                    child: UnavailableText(),
                  )
                else
                  for (final entry in tiers.entries)
                    _TierRow(
                      level: entry.key,
                      payload: (entry.value as Map).cast<String, dynamic>(),
                    ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _TierRow extends StatelessWidget {
  final String level;
  final Map<String, dynamic> payload;

  const _TierRow({required this.level, required this.payload});

  @override
  Widget build(BuildContext context) {
    final primary = payload['is_primary_data'] == true;
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 8),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: Color(0xFF20344C))),
      ),
      child: Row(
        children: [
          SizedBox(
            width: 116,
            child: Text(
              'Niveau $level',
              style: const TextStyle(
                color: mobileBlue,
                fontSize: 18,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
          Container(width: 1, height: 26, color: const Color(0xFF34506F)),
          const SizedBox(width: 34),
          Expanded(
            child: Text(
              _tierLabel(level, '${payload['label']}'),
              style: const TextStyle(
                  color: AppColors.text, fontSize: 18, height: 1.15),
            ),
          ),
          const SizedBox(width: 12),
          MobilePill(
            label: primary ? 'données' : 'affirmations',
            color: primary ? AppColors.measured : const Color(0xFF8EA2BE),
            dense: true,
            filled: primary,
          ),
        ],
      ),
    );
  }
}

class _TheoryPanel extends StatelessWidget {
  final Map<String, dynamic>? claims;
  final Map<String, dynamic>? validation;

  const _TheoryPanel({required this.claims, required this.validation});

  @override
  Widget build(BuildContext context) {
    final claimRows = _claimRows(claims, validation);

    return GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: const [
              _RoundIcon(icon: Icons.bar_chart_rounded),
              SizedBox(width: 22),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Théorie vs données',
                      style: TextStyle(
                        color: AppColors.text,
                        fontSize: 26,
                        fontWeight: FontWeight.w800,
                        height: 1.1,
                      ),
                    ),
                    SizedBox(height: 8),
                    Text(
                      'Ces éléments sont des hypothèses pédagogiques de lecture graphique. '
                      'Ils ne peuvent pas primer sur la valeur mesurée.',
                      style: TextStyle(
                          color: mobileMuted, fontSize: 18, height: 1.25),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 4),
            decoration: BoxDecoration(
              color: const Color(0xFF0C1725).withValues(alpha: 0.54),
              borderRadius: BorderRadius.circular(13),
              border: Border.all(color: const Color(0xFF2A4868), width: 1.1),
            ),
            child: Column(
              children: [
                if (claimRows.isEmpty)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 12),
                    child: UnavailableText(reason: 'Assertions indisponibles.'),
                  )
                else
                  for (final row in claimRows) _ClaimTile(row: row),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ClaimTile extends StatelessWidget {
  final _ClaimView row;

  const _ClaimTile({required this.row});

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
      child: ExpansionTile(
        tilePadding: EdgeInsets.zero,
        childrenPadding: const EdgeInsets.only(bottom: 12),
        iconColor: AppColors.text,
        collapsedIconColor: AppColors.text,
        title: Text(
          row.title,
          style: const TextStyle(
            color: AppColors.text,
            fontSize: 20,
            fontWeight: FontWeight.w800,
          ),
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 3),
            Text(
              row.statement,
              style: const TextStyle(
                  color: mobileMuted, fontSize: 16, height: 1.25),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 12,
              runSpacing: 8,
              children: [
                for (final verdict in row.verdicts)
                  _VerdictBadge(verdict: verdict),
              ],
            ),
          ],
        ),
        children: [
          Align(
            alignment: Alignment.centerLeft,
            child: Text(
              row.detail,
              style: const TextStyle(
                  color: mobileMuted, fontSize: 14.5, height: 1.35),
            ),
          ),
        ],
      ),
    );
  }
}

class _VerdictBadge extends StatelessWidget {
  final _AssetVerdict verdict;

  const _VerdictBadge({required this.verdict});

  @override
  Widget build(BuildContext context) {
    return MobilePill(
      label: '${verdict.asset} ${verdict.label}',
      color: verdict.color,
      dense: true,
      filled:
          verdict.verdict == 'CONTRADICTED' || verdict.verdict == 'SUPPORTED',
    );
  }
}

class _HumanExamplesPanel extends StatelessWidget {
  final Map<String, dynamic>? dataset;

  const _HumanExamplesPanel({required this.dataset});

  @override
  Widget build(BuildContext context) {
    final status = '${dataset?['status'] ?? ''}';
    return GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Exemples humains',
            style: TextStyle(
              color: AppColors.text,
              fontSize: 24,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 8),
          if (dataset == null)
            const UnavailableText()
          else if (status == 'EMPTY')
            Text(
              _datasetNote('${dataset!['note']}'),
              style: const TextStyle(
                  color: mobileMuted, fontSize: 17, height: 1.32),
            )
          else
            Wrap(
              spacing: 12,
              runSpacing: 10,
              children: [
                _SmallMetric(
                    label: 'Exemples', value: '${dataset!['number_examples']}'),
                _SmallMetric(
                    label: 'Épisodes', value: '${dataset!['market_episodes']}'),
                _SmallMetric(
                    label: 'Échantillon',
                    value: '${dataset!['effective_sample_size']}'),
                _SmallMetric(
                    label: 'Vérifiés', value: '${dataset!['human_verified']}'),
              ],
            ),
        ],
      ),
    );
  }
}

class _SmallMetric extends StatelessWidget {
  final String label;
  final String value;

  const _SmallMetric({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 160,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF0C1725).withValues(alpha: 0.54),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF2A4868), width: 1.1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(color: mobileMuted, fontSize: 13)),
          const SizedBox(height: 5),
          Text(
            value,
            style: const TextStyle(
              color: AppColors.text,
              fontSize: 23,
              fontWeight: FontWeight.w800,
            ),
          ),
        ],
      ),
    );
  }
}

class _RoundIcon extends StatelessWidget {
  final IconData icon;

  const _RoundIcon({required this.icon});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 70,
      height: 70,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: const Color(0xFF123E71).withValues(alpha: 0.86),
        border: Border.all(color: const Color(0xFF1D65BA), width: 1.2),
      ),
      child: Icon(icon, color: const Color(0xFF66AEFF), size: 38),
    );
  }
}

class _ClaimView {
  final String title;
  final String statement;
  final String detail;
  final List<_AssetVerdict> verdicts;

  const _ClaimView({
    required this.title,
    required this.statement,
    required this.detail,
    required this.verdicts,
  });
}

class _AssetVerdict {
  final String asset;
  final String verdict;

  const _AssetVerdict({required this.asset, required this.verdict});

  String get label => switch (verdict) {
        'SUPPORTED' => 'soutenu',
        'CONTRADICTED' => 'contredit',
        'PARTIALLY_SUPPORTED' => 'partiel',
        'INSUFFICIENT_DATA' => 'données insuff.',
        'NOT_SUPPORTED' => 'non confirmé',
        _ => 'non confirmé',
      };

  Color get color => switch (verdict) {
        'SUPPORTED' => AppColors.measured,
        'CONTRADICTED' => AppColors.bad,
        'PARTIALLY_SUPPORTED' => mobileBlue,
        'INSUFFICIENT_DATA' => AppColors.warn,
        _ => const Color(0xFF8EA2BE),
      };
}

List<_ClaimView> _claimRows(
  Map<String, dynamic>? claims,
  Map<String, dynamic>? validation,
) {
  final rawClaims = (claims?['claims'] as List? ?? const [])
      .where((claim) => (claim as Map)['claim_type'] == 'EDUCATIONAL_CLAIM')
      .map((claim) => (claim as Map).cast<String, dynamic>())
      .toList();

  final claimByConcept = {
    for (final claim in rawClaims) '${claim['concept']}': claim,
  };

  final verdictByConceptAsset = <String, Map<String, String>>{};
  final results =
      (validation?['results'] as Map?)?.cast<String, dynamic>() ?? const {};
  for (final assetEntry in results.entries) {
    final asset = assetEntry.key;
    for (final claim
        in ((assetEntry.value as Map)['claims'] as List? ?? const [])) {
      final claimMap = (claim as Map).cast<String, dynamic>();
      final concept = '${claimMap['concept']}';
      verdictByConceptAsset.putIfAbsent(concept, () => {})[asset] =
          '${claimMap['verdict']}';
    }
  }

  const concepts = [
    'double_top',
    'double_bottom',
    'triple_top',
    'triple_bottom',
    'head_and_shoulders',
    'inverse_head_and_shoulders',
  ];

  return [
    for (final concept in concepts)
      _ClaimView(
        title: _conceptTitle(concept),
        statement: _claimStatement(
            concept, '${claimByConcept[concept]?['statement'] ?? ''}'),
        detail: _claimDetail(
            concept, '${claimByConcept[concept]?['status_note'] ?? ''}'),
        verdicts: [
          for (final asset in const ['BTC', 'ETH', 'SOL'])
            _AssetVerdict(
              asset: asset,
              verdict:
                  verdictByConceptAsset[concept]?[asset] ?? 'NOT_SUPPORTED',
            ),
        ],
      ),
  ];
}

String _conceptTitle(String concept) => switch (concept) {
      'double_top' => 'Double sommet',
      'double_bottom' => 'Double creux',
      'triple_top' => 'Triple sommet',
      'triple_bottom' => 'Triple creux',
      'head_and_shoulders' => 'Tête et épaules',
      'inverse_head_and_shoulders' => 'Tête et épaules inversée',
      _ => readableLabel(concept),
    };

String _claimStatement(String concept, String fallback) => switch (concept) {
      'double_top' =>
        'Se résout généralement à la baisse après cassure de la ligne de cou.',
      'double_bottom' =>
        'Se résout généralement à la hausse après cassure de la ligne de cou.',
      'triple_top' => 'Se résout généralement à la baisse.',
      'triple_bottom' => 'Se résout généralement à la hausse.',
      'head_and_shoulders' => 'Précède souvent un retournement baissier.',
      'inverse_head_and_shoulders' =>
        'Précède souvent un retournement haussier.',
      _ => fallback,
    };

String _claimDetail(String concept, String fallback) {
  if (fallback.isEmpty) {
    return 'Cette règle est une hypothèse pédagogique. Elle doit être validée contre les rendements futurs avant de pouvoir être utilisée comme signal.';
  }
  return 'Cette règle provient d’une source pédagogique. Elle est conservée comme hypothèse, mais la décision finale revient aux tests empiriques par actif.';
}

String _tierLabel(String level, String fallback) => switch (level) {
      '1' => 'blockchain / protocole natif',
      '2' => 'API officielle ou documentation',
      '3' => 'fournisseur de données spécialisé',
      '4' => 'recherche ou littérature pédagogique',
      '5' => 'analyse de trader humain',
      '6' => 'média généraliste ou commentaire',
      _ => fallback,
    };

String _datasetNote(String raw) {
  if (raw.contains('No human examples stored yet')) {
    return 'Aucun exemple humain n’est encore enregistré. Toute étude fondée sur des exemples humains restera marquée DONNÉES_INSUFFISANTES tant qu’un jeu de données robuste n’aura pas été constitué.';
  }
  return raw;
}
