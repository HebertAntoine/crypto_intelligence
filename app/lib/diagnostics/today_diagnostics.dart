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
    FreshnessState.recent => _check('Fraîcheur', freshness.description,
        CheckStatus.ok, 'Récent: exploitable, sans être instantané.'),
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

/// Un resultat analytique porte deux choses distinctes: ce qu'il vaut
/// historiquement, et s'il decrit encore le present.
///
/// Le percentile de funding calcule sur 7006 observations reste parfaitement
/// valide; l'observation d'aujourd'hui, vieille de 25 h, ne l'est pas. Afficher
/// « OK » melangeait les deux et laissait croire que le funding actuel etait
/// exploitable.
DiagnosticSection _analysis(
  TodayRead read,
  Map<String, FamilyState> families, {
  DateTime? now,
}) {
  bool usable(String family) =>
      families[family]?.usableNow(now: now) ?? false;

  String staleNote(List<String> deps) {
    final broken = deps.where((d) => !usable(d)).map(familyLabel).toList();
    return broken.isEmpty
        ? ''
        : ' Entrée${broken.length > 1 ? 's' : ''} non utilisable'
            '${broken.length > 1 ? 's' : ''}: ${broken.join(', ')}.';
  }

  CheckStatus gated(List<String> deps, CheckStatus ifFresh) =>
      deps.every(usable) ? ifFresh : CheckStatus.warning;

  final checks = <DiagnosticCheck>[];
  final direction = read.summary.marketDirection.toUpperCase();

  checks.add(direction.isEmpty || direction == 'UNDETERMINED'
      ? _check('Direction', direction.isEmpty ? _absent : 'indéterminée',
          CheckStatus.warning, 'Aucune lecture directionnelle établie.')
      : _check(
          'Direction (mode prix simplifié)',
          directionLabel(direction),
          gated(['ohlcv_daily'], CheckStatus.ok),
          'Régime de prix simplifié: tendance, position EMA, momentum, ADX. '
          'Ce n’est pas le moteur de régime multi-domaines complet.'
          '${staleNote(['ohlcv_daily'])}',
        ));

  final confidence = double.tryParse(read.summary.directionConfidence);
  checks.add(confidence == null
      ? _check('Persistance 20 j', read.summary.directionConfidence,
          CheckStatus.unknown, 'Valeur non numérique.')
      : (confidence < 0 || confidence > 100)
          ? _check('Persistance 20 j', '$confidence %', CheckStatus.failed,
              'Hors de l’intervalle 0-100: le calcul est faux.')
          : _check('Persistance 20 j', '${confidence.toStringAsFixed(1)} %',
              gated(['ohlcv_daily'], CheckStatus.ok),
              'Part des 20 dernières clôtures portant le même régime.'
              '${staleNote(['ohlcv_daily'])}'));

  final tested = read.admittedCount + read.rejectedCount;
  checks.add(tested == 0
      ? _check('Avantage statistique', 'aucun candidat testé',
          CheckStatus.warning,
          'Aucune recherche n’a encore tourné pour cet actif.')
      : _check(
          'Avantage statistique',
          '${read.admittedCount} validé, ${read.rejectedCount} rejeté',
          CheckStatus.ok,
          '$tested relations testées. Une relation validée reste une '
          'propriété historique: elle ne dit pas qu’un setup est actif '
          'aujourd’hui.'));

  // Funding: le contexte historique et l'observation actuelle sont separes.
  final percentile = read.fundingPercentile;
  checks.add(percentile == null
      ? _check('Funding', read.fundingBand, CheckStatus.warning,
          'Bande sans percentile: historique insuffisant, ou funding absent.')
      : _check(
          'Funding (contexte historique)',
          '${_bandLabel(read.fundingBand)} · '
              '${percentile.toStringAsFixed(0)}e percentile',
          gated(['funding'], CheckStatus.ok),
          'La dernière valeur connue se situe au '
          '${percentile.toStringAsFixed(0)}e percentile de l’historique de cet '
          'actif. Ce classement reste valide.${staleNote(['funding'])}'));

  // Volatilite: realisee (ATR sur OHLCV) et implicite (DVOL) ne sont pas la
  // meme mesure et ne partagent pas leur fraicheur.
  checks.add(_check(
    'Volatilité réalisée (ATR)',
    _volatilityLabelFr(read.volatilityRegime),
    gated(['ohlcv_daily'], CheckStatus.ok),
    'Calculée sur les bougies journalières, pas sur la volatilité implicite.'
    '${staleNote(['ohlcv_daily'])}',
  ));

  final dvolState = families['dvol'];
  if (dvolState != null) {
    checks.add(_check(
      'Volatilité implicite (DVOL)',
      dvolState.available
          ? (dvolState.usableNow(now: now) ? 'utilisable' : 'non utilisable')
          : 'absente',
      dvolState.available
          ? (dvolState.usableNow(now: now)
              ? CheckStatus.ok
              : CheckStatus.warning)
          : CheckStatus.unknown,
      dvolState.available
          ? 'Mesure distincte de l’ATR. Elle ne contribue pas au régime de '
              'volatilité affiché.'
          : 'Aucune série DVOL pour cet actif; seule la volatilité réalisée '
              'est disponible.',
    ));
  }

  final score = read.uncertaintyScore;
  checks.add((score < 0 || score > 100)
      ? _check('Incertitude', '$score/100', CheckStatus.failed,
          'Hors de l’intervalle 0-100.')
      : read.uncertaintyDrivers.isEmpty
          ? _check('Incertitude', '${score.toStringAsFixed(0)}/100',
              CheckStatus.warning,
              'Score sans facteur: impossible de savoir d’où il vient.')
          : _check('Incertitude', '${score.toStringAsFixed(0)}/100',
              CheckStatus.ok,
              '${read.uncertaintyDrivers.length} facteur(s) nommé(s) '
              'expliquent le score.'));

  // Crowding consomme funding et open interest: les deux doivent etre frais.
  checks.add(read.crowdingScore == null
      ? _check('Crowding', _crowdingLabelFr(read.crowdingLevel),
          CheckStatus.warning, 'Niveau sans score chiffré.')
      : _check(
          'Crowding',
          '${_crowdingLabelFr(read.crowdingLevel)} · '
              '${read.crowdingScore!.toStringAsFixed(0)}/100',
          gated(['funding', 'open_interest'], CheckStatus.ok),
          'Composé de l’étirement du funding, du percentile et de la vitesse '
          'de l’open interest.${staleNote(['funding', 'open_interest'])}'));

  return DiagnosticSection(title: 'Analyse', checks: checks);
}

String _bandLabel(String raw) => switch (raw.toUpperCase()) {
      'VERY_NEGATIVE' => 'Très négatif',
      'NEGATIVE' => 'Négatif',
      'NEUTRAL' => 'Neutre',
      'POSITIVE' => 'Positif',
      'VERY_POSITIVE' => 'Très positif',
      _ => raw.replaceAll('_', ' ').toLowerCase(),
    };

String _volatilityLabelFr(String raw) => switch (raw.toUpperCase()) {
      'LOW' => 'Faible',
      'NORMAL' => 'Normale',
      'HIGH' => 'Élevée',
      'EXTREME' => 'Extrême',
      _ => raw.replaceAll('_', ' ').toLowerCase(),
    };

String _crowdingLabelFr(String raw) => switch (raw.toUpperCase()) {
      'LOW' => 'Faible',
      'NORMAL' => 'Normal',
      'HIGH' => 'Élevé',
      'EXTREME' => 'Extrême',
      _ => raw.replaceAll('_', ' ').toLowerCase(),
    };

/// Chaque famille, avec les quatre reponses separees.
///
/// Le point du LOT: ne plus dire « OK » d'une donnee presente mais perimee.
/// Le libelle porte la fraicheur, et l'utilisabilite est dite explicitement.
DiagnosticSection _families(
  Map<String, FamilyState> declared, {
  DateTime? now,
}) {
  if (declared.isEmpty) {
    return const DiagnosticSection(title: 'Familles d’entrée', checks: [
      DiagnosticCheck(
        name: 'familles',
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
        _check(
          familyLabel(entry.key),
          _familyReceived(entry.value, now: now),
          _familyStatus(entry.value, now: now),
          _familyReason(entry.value, now: now),
        ),
    ],
  );
}

String _familyReceived(FamilyState state, {DateTime? now}) {
  // Recalcule: l'age et la fraicheur du payload sont figes a l'export.
  final derived = state.derived(now: now);
  final parts = <String>[derived.label];
  final age = derived.ageLabel;
  if (age != null) parts.add(age);
  parts.add(state.usableNow(now: now) ? 'utilisable' : 'non utilisable');
  if (state.points != null) parts.add('${state.points} obs.');
  return parts.join(' · ');
}

CheckStatus _familyStatus(FamilyState state, {DateTime? now}) {
  if (!state.available) return CheckStatus.failed;
  if (!state.valid) return CheckStatus.failed;
  if (state.usableNow(now: now)) return CheckStatus.ok;
  // Presente et valide mais trop ancienne: ce n'est pas un echec de la
  // donnee, c'est un refus de s'en servir maintenant.
  return CheckStatus.warning;
}

String _familyReason(FamilyState state, {DateTime? now}) {
  if (!state.available) return 'aucune observation disponible';
  if (!state.valid) return 'les valeurs reçues ne sont pas exploitables';
  if (state.usableNow(now: now)) return 'présente, valide et dans sa cadence';
  final age = state.derived(now: now).ageLabel ?? 'à une date inconnue';
  return 'dernière observation $age: trop ancienne pour l’analyse actuelle';
}

/// Libelle francais d'un regime directionnel.
String directionLabel(String raw) => switch (raw.toUpperCase()) {
      'STRONGLY_BULLISH' => 'Fortement haussier',
      'BULLISH' => 'Haussier',
      'NEUTRAL' => 'Neutre',
      'BEARISH' => 'Baissier',
      'STRONGLY_BEARISH' => 'Fortement baissier',
      'UNDETERMINED' => 'Indéterminé',
      _ => raw.replaceAll('_', ' ').toLowerCase(),
    };

/// Libelle francais d'une famille. Les identifiants internes restent en
/// anglais; l'utilisateur ne doit jamais les voir.
String familyLabel(String key) => switch (key) {
      'price' => 'Prix',
      'ohlcv_daily' => 'Bougies journalières',
      'funding' => 'Funding',
      'open_interest' => 'Open interest',
      'dvol' => 'Volatilité implicite (DVOL)',
      _ => key.replaceAll('_', ' '),
    };

String freshnessLabel(String value) => switch (value.toUpperCase()) {
      'LIVE' => 'À JOUR',
      'RECENT' => 'RÉCENT',
      'DELAYED' => 'DIFFÉRÉ',
      'STALE' => 'PÉRIMÉ',
      'UNAVAILABLE' => 'INDISPONIBLE',
      _ => value,
    };

/// « il y a 3 min », « il y a 2 j ».
String ageLabel(double seconds) {
  final value = seconds.round();
  if (value < 90) return 'il y a $value s';
  if (value < 5400) return 'il y a ${(value / 60).round()} min';
  if (value < 172800) return 'il y a ${(value / 3600).round()} h';
  return 'il y a ${(value / 86400).round()} j';
}

/// Ce que la page a le droit d'affirmer, en francais.
String pageStatusLabel(String value) => switch (value.toUpperCase()) {
      'LIVE' => 'DONNÉES À JOUR',
      'RECENT' => 'DONNÉES RÉCENTES',
      'DEGRADED' => 'DONNÉES PARTIELLES',
      'STALE' => 'DONNÉES PÉRIMÉES',
      'SUSPENDED' => 'ANALYSE SUSPENDUE',
      'UNAVAILABLE' => 'DONNÉES INDISPONIBLES',
      _ => value,
    };

/// Construit le diagnostic complet pour un actif.
TodayDiagnostics buildDiagnostics(
  TodayRead read,
  DataProvenance provenance, {
  DateTime? now,
}) {
  final freshness = read.marketData?.derived(now: now) ?? DerivedFreshness.unknown;
  final reference = now;
  return TodayDiagnostics(
    asset: read.asset,
    origin: provenance.origin,
    freshness: freshness,
    sections: [
      _transport(provenance, freshness),
      _market(read.marketData),
      _analysis(read, read.families, now: reference),
      _families(read.families, now: reference),
    ],
  );
}
