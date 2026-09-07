/// Ce que l'app a reçu, et si c'est exploitable.
///
/// L'écran affiche des verdicts; ce fichier répond à la question d'en dessous:
/// sur quoi reposent-ils, d'où ça vient, et qu'est-ce qui cloche. Chaque
/// contrôle est une fonction pure sur le payload déjà décodé, donc testable
/// sans widget ni réseau.
///
/// Le principe: un contrôle ne dit jamais « OK » par défaut. Il dit OK quand il
/// a vérifié quelque chose, et sinon il dit ce qui manque.
library;

import '../api/client.dart';
import '../api/freshness.dart';
import '../api/models.dart';

enum CheckStatus {
  ok,
  warning,
  failed,
  unknown;

  String get label => switch (this) {
        CheckStatus.ok => 'OK',
        CheckStatus.warning => 'À VÉRIFIER',
        CheckStatus.failed => 'PROBLÈME',
        CheckStatus.unknown => 'INCONNU',
      };
}

class DiagnosticCheck {
  final String name;
  final String received;
  final CheckStatus status;
  final String detail;

  const DiagnosticCheck({
    required this.name,
    required this.received,
    required this.status,
    required this.detail,
  });
}

class DiagnosticSection {
  final String title;
  final List<DiagnosticCheck> checks;

  const DiagnosticSection({required this.title, required this.checks});

  CheckStatus get worst {
    if (checks.any((c) => c.status == CheckStatus.failed)) {
      return CheckStatus.failed;
    }
    if (checks.any((c) => c.status == CheckStatus.warning)) {
      return CheckStatus.warning;
    }
    if (checks.every((c) => c.status == CheckStatus.ok)) return CheckStatus.ok;
    return CheckStatus.unknown;
  }
}

class TodayDiagnostics {
  final String asset;
  final List<DiagnosticSection> sections;
  final DataOrigin origin;
  final DerivedFreshness freshness;

  const TodayDiagnostics({
    required this.asset,
    required this.sections,
    required this.origin,
    required this.freshness,
  });

  List<DiagnosticCheck> get all =>
      [for (final section in sections) ...section.checks];

  int get failures =>
      all.where((c) => c.status == CheckStatus.failed).length;
  int get warnings =>
      all.where((c) => c.status == CheckStatus.warning).length;
  int get passed => all.where((c) => c.status == CheckStatus.ok).length;

  CheckStatus get overall {
    if (failures > 0) return CheckStatus.failed;
    if (warnings > 0) return CheckStatus.warning;
    return passed == all.length ? CheckStatus.ok : CheckStatus.unknown;
  }

  String get summary {
    if (all.isEmpty) return 'Aucun contrôle exécuté.';
    final parts = <String>['$passed/${all.length} contrôles passés'];
    if (warnings > 0) parts.add('$warnings à vérifier');
    if (failures > 0) parts.add('$failures en échec');
    return parts.join(' · ');
  }
}

String _absent = 'absent';

String _num(num? value, {int digits = 2, String unit = ''}) =>
    value == null ? _absent : '${value.toStringAsFixed(digits)}$unit';

DiagnosticCheck _check(
  String name,
  String received,
  CheckStatus status,
  String detail,
) =>
    DiagnosticCheck(
      name: name, received: received, status: status, detail: detail,
    );

/// Origine et âge: la question la plus importante avant toutes les autres.
DiagnosticSection _transport(
  DataProvenance provenance,
  DerivedFreshness freshness,
) {
  final checks = <DiagnosticCheck>[];

  checks.add(switch (provenance.origin) {
    DataOrigin.live => _check(
        'Origine', 'backend en direct', CheckStatus.ok,
        'La réponse vient du backend, pas d’un instantané embarqué.'),
    DataOrigin.snapshot => _check(
        'Origine', 'instantané embarqué', CheckStatus.warning,
        'Backend injoignable. Les chiffres datent de la construction de '
        'l’app et ne bougeront pas avant un nouveau déploiement.'),
    DataOrigin.unknown => _check(
        'Origine', 'inconnue', CheckStatus.failed,
        'L’app ne sait pas d’où viennent ces données.'),
  });

  final observed = freshness.observedAt;
  checks.add(observed == null
      ? _check('Horodatage', _absent, CheckStatus.failed,
          'Sans horodatage d’observation, l’âge est incalculable et rien ne '
          'peut être présenté comme actuel.')
      : _check('Horodatage', observed.toIso8601String(), CheckStatus.ok,
          'Lisible, donc l’âge est vérifiable.'));

  checks.add(switch (freshness.state) {
    FreshnessState.live => _check('Fraîcheur', freshness.description,
        CheckStatus.ok, 'Dans la cadence attendue pour un prix.'),
    FreshnessState.delayed => _check('Fraîcheur', freshness.description,
        CheckStatus.warning, 'Utilisable, mais ce n’est plus du temps réel.'),
    FreshnessState.stale => _check('Fraîcheur', freshness.description,
        CheckStatus.warning,
        'Trop ancien pour décrire le marché actuel. Valeur conservée à titre '
        'informatif.'),
    FreshnessState.expired => _check('Fraîcheur', freshness.description,
        CheckStatus.failed,
        'Lecture figée: elle décrit un moment passé, pas le marché.'),
    FreshnessState.unavailable => _check('Fraîcheur', freshness.description,
        CheckStatus.failed, 'Âge inconnu, donc traité comme périmé.'),
  });

  return DiagnosticSection(title: 'Transport', checks: checks);
}

DiagnosticSection _market(MarketPriceRead? market) {
  if (market == null) {
    return DiagnosticSection(title: 'Marché', checks: [
      _check('Bloc market_data', _absent, CheckStatus.failed,
          'Le payload reçu ne contient aucun bloc de prix. C’est ce qui fait '
          'afficher INDISPONIBLE.'),
    ]);
  }

  final checks = <DiagnosticCheck>[];
  final price = market.displayPrice;

  checks.add(price == null
      ? _check('Prix', _absent, CheckStatus.failed,
          'Ni price_eur ni price_usd dans la réponse.')
      : _check('Prix', '${_num(price)} ${market.displayUnit}', CheckStatus.ok,
          'Valeur numérique présente et positive.'));

  checks.add(market.priceEur == null
      ? _check('Devise', 'USD (pas d’EUR)', CheckStatus.warning,
          'Aucun prix EUR fourni. L’USD est affiché tel quel plutôt qu’une '
          'conversion fabriquée.')
      : _check('Devise', 'EUR', CheckStatus.ok,
          'Prix EUR fourni directement, sans conversion supposée.'));

  checks.add(market.fxSource == null
      ? _check('Source du taux', _absent, CheckStatus.warning,
          'Le taux de change n’est pas tracé.')
      : _check('Source du taux', market.fxSource!, CheckStatus.ok,
          'La provenance du taux est déclarée.'));

  checks.add(market.change24hPct == null
      ? _check('Variation 24 h', _absent, CheckStatus.warning,
          'Non fournie par la source.')
      : _check('Variation 24 h', _num(market.change24hPct, unit: ' %'),
          CheckStatus.ok, 'Fournie par la même source que le prix.'));

  final count = market.providerCount;
  checks.add(count == 0
      ? _check('Providers', '0', CheckStatus.failed,
          'Aucune source de prix n’a répondu.')
      : count == 1
          ? _check('Providers', '1', CheckStatus.warning,
              'Une seule source: aucun recoupement possible.')
          : _check('Providers', '$count', CheckStatus.ok,
              'Le prix est une médiane, pas une source unique.'));

  final dispersion = market.dispersionPct;
  checks.add(dispersion == null
      ? _check('Dispersion', _absent, CheckStatus.unknown,
          'Non calculable avec moins de deux sources.')
      : dispersion > 1.0
          ? _check('Dispersion', _num(dispersion, unit: ' %'),
              CheckStatus.warning,
              'Les sources s’écartent de plus de 1 %: prix peu consensuel.')
          : _check('Dispersion', _num(dispersion, digits: 3, unit: ' %'),
              CheckStatus.ok, 'Les sources concordent.'));

  return DiagnosticSection(title: 'Marché', checks: checks);
}

DiagnosticSection _analysis(TodayRead read) {
  final checks = <DiagnosticCheck>[];
  final direction = read.summary.marketDirection.toUpperCase();

  checks.add(direction.isEmpty || direction == 'UNDETERMINED'
      ? _check('Direction', direction.isEmpty ? _absent : direction,
          CheckStatus.warning,
          'Aucune lecture directionnelle établie.')
      : _check('Direction', direction, CheckStatus.ok,
          'Reconstruite depuis la structure de prix, point-in-time.'));

  final confidence = double.tryParse(read.summary.directionConfidence);
  checks.add(confidence == null
      ? _check('Persistance 20 j', read.summary.directionConfidence,
          CheckStatus.unknown, 'Valeur non numérique.')
      : (confidence < 0 || confidence > 100)
          ? _check('Persistance 20 j', '$confidence %', CheckStatus.failed,
              'Hors de l’intervalle 0-100: le calcul est faux.')
          : _check('Persistance 20 j', '${confidence.toStringAsFixed(1)} %',
              CheckStatus.ok,
              'Part des 20 dernières clôtures portant le même régime.'));

  final tested = read.admittedCount + read.rejectedCount;
  checks.add(tested == 0
      ? _check('Edge', 'aucun candidat testé', CheckStatus.warning,
          'Aucune recherche n’a encore tourné pour cet actif.')
      : _check('Edge',
          '${read.admittedCount} validé, ${read.rejectedCount} rejeté',
          CheckStatus.ok,
          '$tested relations testées; les compteurs sont cohérents.'));

  final percentile = read.fundingPercentile;
  checks.add(percentile == null
      ? _check('Funding', read.fundingBand, CheckStatus.warning,
          'Bande sans percentile: historique insuffisant, ou funding absent.')
      : (percentile < 0 || percentile > 100)
          ? _check('Funding', 'p$percentile', CheckStatus.failed,
              'Percentile hors 0-100.')
          : _check('Funding',
              '${read.fundingBand} · p${percentile.toStringAsFixed(0)}',
              CheckStatus.ok,
              'Percentile réel, calculé sur l’historique propre de l’actif.'));

  final score = read.uncertaintyScore;
  checks.add((score < 0 || score > 100)
      ? _check('Incertitude', '$score/100', CheckStatus.failed,
          'Hors de l’intervalle 0-100.')
      : read.uncertaintyDrivers.isEmpty
          ? _check('Incertitude', '${score.toStringAsFixed(0)}/100',
              CheckStatus.warning,
              'Score sans driver: impossible de savoir d’où il vient.')
          : _check('Incertitude', '${score.toStringAsFixed(0)}/100',
              CheckStatus.ok,
              '${read.uncertaintyDrivers.length} driver(s) nommé(s) '
              'expliquent le score.'));

  checks.add(read.crowdingScore == null
      ? _check('Crowding', read.crowdingLevel, CheckStatus.warning,
          'Niveau sans score chiffré.')
      : _check('Crowding',
          '${read.crowdingLevel} · ${_num(read.crowdingScore, digits: 0)}/100',
          CheckStatus.ok, 'Score composite disponible.'));

  return DiagnosticSection(title: 'Analyse', checks: checks);
}

DiagnosticSection _families(Map<String, String> declared) {
  if (declared.isEmpty) {
    return const DiagnosticSection(title: 'Familles d’entrée', checks: [
      DiagnosticCheck(
        name: 'input_freshness',
        received: 'absent',
        status: CheckStatus.warning,
        detail: 'Le backend ne déclare pas l’état de ses familles d’entrée. '
            'Version antérieure à ce champ.',
      ),
    ]);
  }

  return DiagnosticSection(
    title: 'Familles d’entrée',
    checks: [
      for (final entry in declared.entries)
        if (!entry.key.endsWith('_missing'))
          _check(
            entry.key,
            entry.value,
            switch (entry.value.toUpperCase()) {
              'OK' => CheckStatus.ok,
              'INSUFFICIENT_HISTORY' => CheckStatus.warning,
              'STALE' => CheckStatus.warning,
              'UNAVAILABLE' => CheckStatus.failed,
              _ => CheckStatus.unknown,
            },
            switch (entry.value.toUpperCase()) {
              'OK' => 'Donnée présente et suffisante.',
              'INSUFFICIENT_HISTORY' =>
                'Présente mais trop courte pour un percentile.',
              'UNAVAILABLE' => 'Absente: rien ne peut en être dérivé.',
              'STALE' => 'Trop ancienne pour la cadence de cette famille.',
              _ => 'État non reconnu.',
            },
          ),
    ],
  );
}

/// Construit le diagnostic complet pour un actif.
TodayDiagnostics buildDiagnostics(
  TodayRead read,
  DataProvenance provenance, {
  DateTime? now,
}) {
  final freshness = read.marketData?.derived(now: now) ?? DerivedFreshness.unknown;
  return TodayDiagnostics(
    asset: read.asset,
    origin: provenance.origin,
    freshness: freshness,
    sections: [
      _transport(provenance, freshness),
      _market(read.marketData),
      _analysis(read),
      _families(read.inputFreshness),
    ],
  );
}
