/// Recherche: validation empirique des signaux.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../theme/app_theme.dart';
import '../widgets/common.dart';
import '../widgets/mobile_kit.dart';

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
      safe(widget.client.revalidation()),
      safe(widget.client.dvolStudy()),
    ]);
    return {
      'marginal': results[0],
      'structural': results[1],
      'replication': results[2],
      'revalidation': results[3],
      'dvol': results[4],
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
            return MobileScrollView(
              padding: const EdgeInsets.fromLTRB(28, 28, 28, 260),
              children: [
                MobileHeader(
                  title: 'Recherche',
                  subtitle: 'Validation des signaux et lecture empirique',
                  onInfo: () => _showInfo(context),
                ),
                const SizedBox(height: 22),
                if (snapshot.connectionState == ConnectionState.waiting)
                  const SizedBox(
                      height: 440,
                      child: LoadingView(what: 'resultats de recherche'))
                else if (snapshot.hasError)
                  SizedBox(
                    height: 440,
                    child: ErrorView(error: snapshot.error!, onRetry: _reload),
                  )
                else ...[
                  _MarginalPanel(
                      data:
                          snapshot.data!['marginal'] as Map<String, dynamic>?),
                  const SizedBox(height: 22),
                  _RevalidationPanel(
                    data: snapshot.data!['revalidation'] as Map<String, dynamic>?,
                  ),
                  const SizedBox(height: 22),
                  _DvolPanel(
                    data: snapshot.data!['dvol'] as Map<String, dynamic>?,
                  ),
                  const SizedBox(height: 22),
                  _SecondaryStudies(
                    structural:
                        snapshot.data!['structural'] as Map<String, dynamic>?,
                    replication:
                        snapshot.data!['replication'] as Map<String, dynamic>?,
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
        title: const Text('Recherche'),
        content: const Text(
          'Les cartes comparent les couches de lecture graphique aux variables '
          'numeriques simples. Un OOS R² negatif signifie que la couche predit '
          'moins bien que la moyenne d’entrainement.',
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

class _MarginalPanel extends StatelessWidget {
  final Map<String, dynamic>? data;

  const _MarginalPanel({required this.data});

  @override
  Widget build(BuildContext context) {
    final assets =
        (data?['assets'] as Map?)?.cast<String, dynamic>() ?? const {};
    return GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: const [
              IconTile(icon: Icons.science_outlined),
              SizedBox(width: 24),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'La lecture graphique apporte-t-elle quelque chose ?',
                      style: TextStyle(
                        color: AppColors.text,
                        fontSize: 28,
                        fontWeight: FontWeight.w800,
                        height: 1.15,
                      ),
                    ),
                    SizedBox(height: 10),
                    Text(
                      'Comparaison hors échantillon entre variables numériques, '
                      'position dans le range et figures chartistes.',
                      style: TextStyle(
                          color: mobileMuted, fontSize: 21, height: 1.24),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 22),
          if (assets.isEmpty)
            const Text(
              'Étude indisponible sur ce backend.',
              style: TextStyle(color: mobileMuted, fontSize: 18),
            )
          else
            for (final entry in assets.entries) ...[
              _MarginalAssetCard(
                asset: entry.key,
                payload: (entry.value as Map).cast<String, dynamic>(),
              ),
              if (entry.key != assets.keys.last) const SizedBox(height: 16),
            ],
        ],
      ),
    );
  }
}

class _MarginalAssetCard extends StatelessWidget {
  final String asset;
  final Map<String, dynamic> payload;

  const _MarginalAssetCard({required this.asset, required this.payload});

  @override
  Widget build(BuildContext context) {
    final visuals = AssetVisuals.forAsset(asset);
    final layersPayload = (payload['layers'] as Map?)?.cast<String, dynamic>();
    final layers =
        (layersPayload?['layers'] as Map?)?.cast<String, dynamic>() ?? const {};
    final verdict =
        (layersPayload?['verdict'] as Map?)?.cast<String, dynamic>();
    final answer =
        ((payload['location_marginal_value'] as Map?)?['answer'] as Map?)
            ?.cast<String, dynamic>();

    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        color: mobilePanelAlt.withValues(alpha: 0.72),
        borderRadius: BorderRadius.circular(15),
        border: Border.all(color: const Color(0xFF2A4868), width: 1.25),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CryptoLogo(asset: asset, size: 68),
              const SizedBox(width: 20),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      asset,
                      style: const TextStyle(
                        color: AppColors.text,
                        fontSize: 28,
                        fontWeight: FontWeight.w800,
                        height: 1,
                      ),
                    ),
                    const SizedBox(height: 7),
                    Text(
                      visuals.name,
                      style: const TextStyle(
                          color: mobileMuted, fontSize: 21, height: 1),
                    ),
                  ],
                ),
              ),
              MobilePill(
                  label: 'Analyse hors échantillon',
                  color: const Color(0xFF7DB7FF)),
            ],
          ),
          const SizedBox(height: 16),
          _LayerTable(layers: layers),
          const SizedBox(height: 10),
          MobilePill(
            label: _verdictLabel(
                '${verdict?['answer'] ?? answer?['verdict'] ?? ''}'),
            color: AppColors.warn,
          ),
          const SizedBox(height: 14),
          Text(
            _verdictSummary('${verdict?['summary'] ?? ''}'),
            style: const TextStyle(
                color: AppColors.text, fontSize: 20, height: 1.31),
          ),
          if (answer?['statement'] != null) ...[
            const SizedBox(height: 16),
            _InfoCallout(text: _marginalStatement('${answer!['statement']}')),
          ],
        ],
      ),
    );
  }
}

class _LayerTable extends StatelessWidget {
  final Map<String, dynamic> layers;

  const _LayerTable({required this.layers});

  @override
  Widget build(BuildContext context) {
    final rows = [
      _LayerRowData('A.  Variables numériques', layers['A_numeric'] as Map?),
      _LayerRowData(
          'B.  + Position dans le range', layers['B_plus_location'] as Map?),
      _LayerRowData(
          'C.  + Figures chartistes', layers['C_plus_patterns'] as Map?),
    ];

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 12),
      decoration: BoxDecoration(
        color: const Color(0xFF0C1725).withValues(alpha: 0.48),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF2A4868), width: 1.1),
      ),
      child: Column(
        children: [
          for (final row in rows) _LayerScoreRow(row: row),
        ],
      ),
    );
  }
}

class _LayerScoreRow extends StatelessWidget {
  final _LayerRowData row;

  const _LayerScoreRow({required this.row});

  @override
  Widget build(BuildContext context) {
    final value = (row.payload?['oos_r2'] as num?)?.toDouble();
    final positive = (value ?? -1) >= 0;
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 8),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: Color(0xFF22374D))),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(row.label,
                style: const TextStyle(color: mobileMuted, fontSize: 20)),
          ),
          Text(
            'OOS R² ${signedFr(value, digits: 4)}',
            style: TextStyle(
              color:
                  positive ? const Color(0xFF56E68B) : const Color(0xFFFF5D55),
              fontSize: 20,
              fontWeight: FontWeight.w800,
            ),
          ),
        ],
      ),
    );
  }
}

class _LayerRowData {
  final String label;
  final Map? payload;

  const _LayerRowData(this.label, this.payload);
}

class _InfoCallout extends StatelessWidget {
  final String text;

  const _InfoCallout({required this.text});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF132235).withValues(alpha: 0.78),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF2E4D6E), width: 1.05),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.info_outline_rounded,
              color: Color(0xFFBFD2F2), size: 32),
          const SizedBox(width: 16),
          Expanded(
            child: Text(text,
                style: const TextStyle(
                    color: mobileMuted, fontSize: 18, height: 1.32)),
          ),
        ],
      ),
    );
  }
}

/// The ten pre-registered candidates, re-tested with purged folds and both
/// control methods.
///
/// Every one passes stratification and fails residualisation. The panel shows
/// both numbers side by side, because the disagreement between the two methods
/// IS the finding.
class _RevalidationPanel extends StatelessWidget {
  final Map<String, dynamic>? data;

  const _RevalidationPanel({required this.data});

  @override
  Widget build(BuildContext context) {
    if (data == null) {
      return const GlassPanel(
        child: UnavailableText(reason: 'Revalidation non exécutée.'),
      );
    }
    final counts = (data!['verdict_counts'] as Map?)?.cast<String, dynamic>() ?? const {};
    final results = (data!['results'] as List?) ?? const [];

    return GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'REVALIDATION DES CANDIDATS',
            style: TextStyle(
              fontSize: 12.5,
              fontWeight: FontWeight.w800,
              letterSpacing: 1.1,
              color: mobileMuted,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            '${data!['candidates_preregistered'] ?? results.length} candidats '
            'préenregistrés, repassés avec purge et double contrôle.',
            style: const TextStyle(fontSize: 12.5, color: mobileMuted, height: 1.4),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final entry in counts.entries)
                MobilePill(
                  label: '${entry.value} ${_studyVerdict(entry.key)}',
                  color: _studyColour(entry.key),
                  dense: true,
                ),
            ],
          ),
          const SizedBox(height: 14),
          for (final row in results)
            if ((row as Map)['status'] == 'OK') _revalRow(row.cast<String, dynamic>()),
        ],
      ),
    );
  }

  Widget _revalRow(Map<String, dynamic> row) {
    final strat = (row['stratified'] as Map?)?.cast<String, dynamic>();
    final sample = (row['effective_sample'] as Map?)?.cast<String, dynamic>();
    final residual = row['residual_excess_pct'];
    final residualP = row['residual_p_value'];

    return Padding(
      padding: const EdgeInsets.only(bottom: 13),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  '${row['id']}'.replaceAll('_', ' '),
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    color: Colors.white,
                  ),
                ),
              ),
              MobilePill(
                label: _studyVerdict('${row['verdict']}'),
                color: _studyColour('${row['verdict']}'),
                dense: true,
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            'stratifié ${strat?['excess_pct'] ?? '—'}% '
            '(p=${(strat?['p_value'] as num?)?.toStringAsFixed(4) ?? '—'})  ·  '
            'résidualisé ${residual ?? '—'}% '
            '(p=${(residualP as num?)?.toStringAsFixed(3) ?? '—'})',
            style: const TextStyle(fontSize: 11.5, color: Color(0xFFDCE7F5)),
          ),
          Text(
            'n_effectif ${sample?['effective_n'] ?? '—'}  ·  ${row['binding_reason'] ?? ''}',
            style: const TextStyle(fontSize: 11, color: mobileMuted, height: 1.3),
          ),
        ],
      ),
    );
  }
}

/// The 24 pre-registered implied-volatility hypotheses.
class _DvolPanel extends StatelessWidget {
  final Map<String, dynamic>? data;

  const _DvolPanel({required this.data});

  @override
  Widget build(BuildContext context) {
    if (data == null) {
      return const GlassPanel(
        child: UnavailableText(reason: 'Étude volatilité implicite non exécutée.'),
      );
    }
    final testing = (data!['multiple_testing'] as Map?)?.cast<String, dynamic>() ?? const {};
    final counts = (data!['verdict_counts'] as Map?)?.cast<String, dynamic>() ?? const {};
    final unavailable = (data!['assets_unavailable'] as List?) ?? const [];

    return GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'VOLATILITÉ IMPLICITE (DVOL)',
            style: TextStyle(
              fontSize: 12.5,
              fontWeight: FontWeight.w800,
              letterSpacing: 1.1,
              color: mobileMuted,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            '${data!['hypotheses_preregistered'] ?? '—'} hypothèses déclarées avant calcul. '
            '${testing['raw_significant'] ?? '—'} significatives brutes, '
            '${testing['fdr_significant'] ?? '—'} après FDR, '
            '${testing['expected_false_positives'] ?? '—'} faux positifs attendus.',
            style: const TextStyle(fontSize: 12.5, color: mobileMuted, height: 1.4),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final entry in counts.entries)
                MobilePill(
                  label: '${entry.value} ${_studyVerdict(entry.key)}',
                  color: _studyColour(entry.key),
                  dense: true,
                ),
            ],
          ),
          if (unavailable.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              'Sans indice de volatilité: ${unavailable.join(', ')}. '
              'Rien n’est substitué.',
              style: const TextStyle(fontSize: 11.5, color: mobileMuted, height: 1.35),
            ),
          ],
        ],
      ),
    );
  }
}

String _studyVerdict(String verdict) => switch (verdict) {
      'SUPPORTED' => 'soutenu',
      'INCONCLUSIVE' => 'non concluant',
      'FAILED' => 'infirmé',
      'INSUFFICIENT_DATA' => 'données insuffisantes',
      _ => verdict.toLowerCase(),
    };

Color _studyColour(String verdict) => switch (verdict) {
      'SUPPORTED' => AppColors.measured,
      'FAILED' => AppColors.bad,
      'INCONCLUSIVE' => AppColors.warn,
      _ => mobileMuted,
    };

class _SecondaryStudies extends StatelessWidget {
  final Map<String, dynamic>? structural;
  final Map<String, dynamic>? replication;

  const _SecondaryStudies(
      {required this.structural, required this.replication});

  @override
  Widget build(BuildContext context) {
    final structuralResults =
        (structural?['results'] as Map?)?.cast<String, dynamic>() ?? const {};
    final findings =
        (replication?['findings'] as Map?)?.cast<String, dynamic>() ?? const {};

    return GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Études complémentaires',
            style: TextStyle(
                color: AppColors.text,
                fontSize: 24,
                fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 10),
          Text(
            '${structuralResults.length} familles structurelles suivies · '
            '${findings.length} tests de réplication disponibles',
            style:
                const TextStyle(color: mobileMuted, fontSize: 18, height: 1.3),
          ),
        ],
      ),
    );
  }
}

String _verdictLabel(String value) => switch (value) {
      'NO_LAYER_ADDS_VALUE' => 'AUCUNE COUCHE N’APPORTE DE VALEUR',
      'NEITHER_ADDS_VALUE' =>
        'NI LA POSITION NI LES FIGURES N’AJOUTENT DE VALEUR',
      'LOCATION_ADDS_VALUE' => 'LA POSITION AJOUTE DE LA VALEUR',
      'PATTERNS_ADD_VALUE' => 'LES FIGURES AJOUTENT DE LA VALEUR',
      'NO_MARGINAL_INFORMATION' => 'AUCUNE INFORMATION MARGINALE',
      _ => value.isEmpty ? 'RÉSULTAT INDISPONIBLE' : readableLabel(value),
    };

String _verdictSummary(String value) {
  if (value.contains('Every layer has NEGATIVE')) {
    return 'Chaque couche présente un R² hors échantillon négatif, ce qui signifie que toutes prédisent des rendements futurs moins bien que la moyenne d’entraînement. Aucune couche n’améliore la qualité prédictive à cet horizon.';
  }
  if (value.contains('Neither structural location nor patterns')) {
    return 'Ni la position structurelle dans le range, ni les figures chartistes n’améliorent l’ajustement hors échantillon par rapport aux simples variables numériques.';
  }
  if (value.isEmpty) return 'Résultat empirique indisponible.';
  return value;
}

String _marginalStatement(String value) {
  final nMatch = RegExp(r'n=(\d+)').firstMatch(value);
  final pMatch = RegExp(r'p=([0-9.]+)').firstMatch(value);
  final n = nMatch?.group(1) ?? '—';
  final p = pMatch?.group(1)?.replaceAll('.', ',') ?? '—';
  final bottom = RegExp(
          r'Being near a range bottom preceded returns ([^%]+)% relative to the unconditional average, and ([^%]+)% relative to a REGIME-MATCHED baseline')
      .firstMatch(value);
  if (bottom != null) {
    return 'Être proche d’un plus bas de range précédait des rendements '
        '${bottom.group(1)!.trim().replaceAll('.', ',')} % par rapport à la moyenne inconditionnelle, '
        'et ${bottom.group(2)!.trim().replaceAll('.', ',')} % par rapport à une base appariée par régime '
        '(n = $n, p = $p). Une fois le régime pris en compte, la position dans le range '
        'n’apporte aucun effet mesurable : l’effet apparent venait du régime lui-même.';
  }
  return value;
}
