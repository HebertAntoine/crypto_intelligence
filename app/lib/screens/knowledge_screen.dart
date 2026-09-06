/// Connaissance: ce que les sources affirment, face à ce que les données montrent.
///
/// La confrontation est l'objet même de cet écran. Là où la théorie et la
/// mesure divergent, les deux restent affichées: masquer le désaccord annulerait
/// la raison d'avoir collecté l'affirmation.
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
    // Chaque étude est optionnelle: une absence est signalée, jamais fatale.
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
              padding: const EdgeInsets.fromLTRB(28, 28, 28, 24),
              children: [
                MobileHeader(
                  title: 'Connaissance',
                  subtitle: 'Ce que la théorie affirme, ce que les données mesurent',
                  onInfo: () => _showInfo(context),
                ),
                const SizedBox(height: 22),
                if (snapshot.connectionState == ConnectionState.waiting)
                  const SizedBox(
                    height: 440,
                    child: LoadingView(what: 'la base de connaissance'),
                  )
                else if (snapshot.hasError)
                  SizedBox(
                    height: 440,
                    child: ErrorView(error: snapshot.error!, onRetry: _reload),
                  )
                else ...[
                  _ConfrontationPanel(
                    claims: snapshot.data!['claims'] as Map<String, dynamic>?,
                    validation: snapshot.data!['validation'] as Map<String, dynamic>?,
                  ),
                  const SizedBox(height: 22),
                  _HierarchyPanel(
                    hierarchy: snapshot.data!['hierarchy'] as Map<String, dynamic>?,
                  ),
                  const SizedBox(height: 22),
                  _DatasetPanel(
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
        backgroundColor: mobilePanel,
        title: const Text('Théorie et mesure', style: TextStyle(fontSize: 16)),
        content: const Text(
          'Les affirmations pédagogiques sont des hypothèses sur la lecture des '
          'graphiques, pas des faits de marché. Elles se situent au niveau 4 de la '
          'hiérarchie des sources et ne peuvent jamais primer sur une donnée '
          'mesurée.\n\n'
          'CONTREDIT et NON SOUTENU sont des résultats informatifs, affichés aussi '
          'visiblement que SOUTENU.',
          style: TextStyle(fontSize: 13, height: 1.45, color: mobileMuted),
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

Color _verdictColour(String verdict) => switch (verdict) {
      'SUPPORTED' => AppColors.measured,
      'CONTRADICTED' => AppColors.bad,
      'PARTIALLY_SUPPORTED' => mobileBlue,
      _ => mobileMuted,
    };

String _verdictLabel(String verdict) => switch (verdict) {
      'SUPPORTED' => 'SOUTENU',
      'CONTRADICTED' => 'CONTREDIT',
      'PARTIALLY_SUPPORTED' => 'PARTIEL',
      'NOT_SUPPORTED' => 'NON SOUTENU',
      'INSUFFICIENT_DATA' => 'DONNÉES INSUFFISANTES',
      'UNTESTABLE' => 'NON TESTABLE',
      _ => verdict,
    };

class _ConfrontationPanel extends StatelessWidget {
  final Map<String, dynamic>? claims;
  final Map<String, dynamic>? validation;

  const _ConfrontationPanel({required this.claims, required this.validation});

  @override
  Widget build(BuildContext context) {
    if (claims == null) {
      return const GlassPanel(
        child: UnavailableText(reason: 'Affirmations indisponibles.'),
      );
    }

    // concept -> verdicts mesurés, un par actif.
    final verdicts = <String, List<Map<String, dynamic>>>{};
    for (final assetResult in ((validation?['results'] as Map?)?.values ?? const [])) {
      for (final claim in ((assetResult as Map)['claims'] as List? ?? const [])) {
        final concept = '${(claim as Map)['concept']}';
        verdicts.putIfAbsent(concept, () => []).add(claim.cast<String, dynamic>());
      }
    }

    final directional = (claims!['claims'] as List? ?? const [])
        .where((c) => (c as Map)['claim_type'] == 'EDUCATIONAL_CLAIM')
        .toList();

    return GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'THÉORIE FACE AUX DONNÉES',
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w800,
              letterSpacing: 1.1,
              color: mobileMuted,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            validation == null
                ? 'Validation non exécutée sur ce backend.'
                : '${directional.length} affirmations directionnelles testées.',
            style: const TextStyle(fontSize: 13, color: mobileMuted, height: 1.4),
          ),
          const SizedBox(height: 16),
          for (final claim in directional)
            _ClaimRow(
              claim: (claim as Map).cast<String, dynamic>(),
              measured: verdicts['${claim['concept']}'] ?? const [],
            ),
        ],
      ),
    );
  }
}

class _ClaimRow extends StatelessWidget {
  final Map<String, dynamic> claim;
  final List<Map<String, dynamic>> measured;

  const _ClaimRow({required this.claim, required this.measured});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${claim['concept']}'.replaceAll('_', ' '),
            style: const TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w700,
              color: Colors.white,
            ),
          ),
          const SizedBox(height: 3),
          Text(
            '${claim['statement']}',
            style: const TextStyle(fontSize: 12.5, color: mobileMuted, height: 1.35),
          ),
          const SizedBox(height: 8),
          if (measured.isEmpty)
            const Text(
              'non testé',
              style: TextStyle(
                fontSize: 12,
                color: mobileMuted,
                fontStyle: FontStyle.italic,
              ),
            )
          else
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final entry in measured)
                  MobilePill(
                    label: '${entry['asset']} · ${_verdictLabel('${entry['verdict']}')}',
                    color: _verdictColour('${entry['verdict']}'),
                    dense: true,
                  ),
              ],
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
    if (hierarchy == null) {
      return const GlassPanel(child: UnavailableText());
    }
    final tiers = (hierarchy!['tiers'] as Map?)?.cast<String, dynamic>() ?? const {};
    return GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'HIÉRARCHIE DES SOURCES',
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w800,
              letterSpacing: 1.1,
              color: mobileMuted,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            '${hierarchy!['rule']}',
            style: const TextStyle(fontSize: 12.5, color: mobileMuted, height: 1.4),
          ),
          const SizedBox(height: 14),
          for (final entry in tiers.entries)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: 52,
                    child: Text(
                      'T${entry.key}',
                      style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w800,
                        color: Colors.white,
                      ),
                    ),
                  ),
                  Expanded(
                    child: Text(
                      '${(entry.value as Map)['label']}',
                      style: const TextStyle(fontSize: 13, color: Colors.white),
                    ),
                  ),
                  MobilePill(
                    label: (entry.value as Map)['is_primary_data'] == true
                        ? 'donnée'
                        : 'affirmation',
                    color: (entry.value as Map)['is_primary_data'] == true
                        ? AppColors.measured
                        : mobileMuted,
                    dense: true,
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _DatasetPanel extends StatelessWidget {
  final Map<String, dynamic>? dataset;

  const _DatasetPanel({required this.dataset});

  @override
  Widget build(BuildContext context) {
    if (dataset == null) {
      return const GlassPanel(child: UnavailableText());
    }

    if (dataset!['status'] == 'EMPTY') {
      return GlassPanel(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'EXEMPLES HUMAINS',
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w800,
                letterSpacing: 1.1,
                color: mobileMuted,
              ),
            ),
            const SizedBox(height: 10),
            Text(
              '${dataset!['note']}',
              style: const TextStyle(fontSize: 13, color: Colors.white, height: 1.45),
            ),
            const SizedBox(height: 8),
            Text(
              'Cible: ${dataset!['target']}',
              style: const TextStyle(fontSize: 12.5, color: mobileMuted),
            ),
          ],
        ),
      );
    }

    return GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'EXEMPLES HUMAINS',
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w800,
              letterSpacing: 1.1,
              color: mobileMuted,
            ),
          ),
          const SizedBox(height: 14),
          _MetricRow(label: 'Exemples', value: '${dataset!['number_examples']}'),
          _MetricRow(
            label: 'Épisodes de marché',
            value: '${dataset!['market_episodes']}',
            hint: 'la vraie unité de preuve',
          ),
          _MetricRow(
            label: 'Échantillon effectif',
            value: '${dataset!['effective_sample_size']}',
          ),
          _MetricRow(label: 'Vérifiés', value: '${dataset!['human_verified']}'),
        ],
      ),
    );
  }
}

class _MetricRow extends StatelessWidget {
  final String label;
  final String value;
  final String? hint;

  const _MetricRow({required this.label, required this.value, this.hint});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: const TextStyle(fontSize: 13.5, color: Colors.white),
                ),
                if (hint != null)
                  Text(
                    hint!,
                    style: const TextStyle(fontSize: 11.5, color: mobileMuted),
                  ),
              ],
            ),
          ),
          Text(
            value,
            style: const TextStyle(
              fontSize: 17,
              fontWeight: FontWeight.w800,
              color: Colors.white,
            ),
          ),
        ],
      ),
    );
  }
}
