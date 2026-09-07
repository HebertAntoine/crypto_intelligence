/// Âge et fraîcheur recalculés à l'affichage, jamais lus tels quels.
///
/// Le défaut que ce fichier corrige : un instantané embarqué transporte les
/// champs `freshness`, `status` et `age_seconds` tels qu'ils étaient au moment
/// de la capture. Un snapshot pris pendant que le backend répondait contient
/// donc `freshness: LIVE` et `age_seconds: 0.0002` — et les rejoue à
/// l'identique six mois plus tard. L'interface affiche alors « LIVE · âge 0 s »
/// au-dessus d'un prix périmé, ce qui est exactement la présentation qu'il
/// faut rendre impossible.
///
/// La règle appliquée ici : le seul champ digne de confiance dans un instantané
/// est l'horodatage de l'observation. Tout le reste se recalcule contre
/// l'horloge courante. Un horodatage absent ou illisible ne donne jamais
/// « frais » : il donne « inconnu », qui est traité comme périmé.
library;

/// Les seuils reflètent la cadence réelle de chaque famille, comme côté
/// backend (`core/freshness.py`). Un prix de six minutes est vieux ; un flux
/// ETF de six heures est normal, car il n'est publié qu'une fois par séance.
/// Les seuils reflètent `core/usability.py` côté backend. Ils sont dupliqués
/// ici parce que le client doit pouvoir recalculer sans faire confiance aux
/// champs du payload: dans un instantané embarqué, la fraîcheur et l'âge ont
/// été figés à l'instant de l'export.
enum DataFamily {
  price(live: 120, recent: 900, delayed: 3600),
  ohlcvDaily(live: 93600, recent: 172800, delayed: 345600),
  funding(live: 3600, recent: 32400, delayed: 86400),
  openInterest(live: 3600, recent: 93600, delayed: 259200),
  dvol(live: 3600, recent: 93600, delayed: 259200),
  derivatives(live: 300, recent: 3600, delayed: 86400),
  onchain(live: 900, recent: 14400, delayed: 172800),
  etf(live: 3600, recent: 86400, delayed: 259200),
  macro(live: 3600, recent: 86400, delayed: 604800),
  analysis(live: 900, recent: 21600, delayed: 86400);

  final int live;
  final int recent;
  final int delayed;

  const DataFamily({
    required this.live,
    required this.recent,
    required this.delayed,
  });
}

enum FreshnessState {
  live,
  recent,
  delayed,
  stale,
  expired,
  unavailable;

  /// Au-delà de `stale`, aucune analyse ne doit être présentée comme actuelle.
  /// Au-delà de « différé », aucune analyse ne doit être présentée comme
  /// actuelle: la donnée décrit un moment passé.
  bool get blocksAnalysis =>
      this == FreshnessState.stale ||
      this == FreshnessState.expired ||
      this == FreshnessState.unavailable;

  bool get isTrustworthy =>
      this == FreshnessState.live || this == FreshnessState.recent;
}

/// Fraîcheur dérivée d'un horodatage d'observation, plus l'âge qui la justifie.
class DerivedFreshness {
  final FreshnessState state;
  final Duration? age;
  final DateTime? observedAt;

  const DerivedFreshness({
    required this.state,
    this.age,
    this.observedAt,
  });

  static const unknown = DerivedFreshness(state: FreshnessState.unavailable);

  bool get isTrustworthy => state.isTrustworthy;
  bool get blocksAnalysis => state.blocksAnalysis;

  String get label => switch (state) {
        FreshnessState.live => 'À JOUR',
        FreshnessState.recent => 'RÉCENT',
        FreshnessState.delayed => 'DIFFÉRÉ',
        FreshnessState.stale => 'PÉRIMÉ',
        FreshnessState.expired => 'PÉRIMÉ',
        FreshnessState.unavailable => 'INDISPONIBLE',
      };

  /// « il y a 3 min », « il y a 2 j ». Null quand l'âge est inconnu.
  String? get ageLabel {
    final value = age;
    if (value == null) return null;
    if (value.inSeconds < 90) return 'il y a ${value.inSeconds} s';
    if (value.inMinutes < 90) return 'il y a ${value.inMinutes} min';
    if (value.inHours < 48) return 'il y a ${value.inHours} h';
    return 'il y a ${value.inDays} j';
  }

  String get description {
    final suffix = ageLabel;
    return suffix == null ? label : '$label · $suffix';
  }
}

/// La famille correspondant à une clé du payload backend.
DataFamily familyFor(String key) => switch (key) {
      'price' => DataFamily.price,
      'ohlcv_daily' => DataFamily.ohlcvDaily,
      'funding' => DataFamily.funding,
      'open_interest' => DataFamily.openInterest,
      'dvol' => DataFamily.dvol,
      _ => DataFamily.derivatives,
    };

/// Recalcule la fraîcheur à partir de l'horodatage d'observation.
///
/// `observedAtRaw` est la seule entrée utilisée. Les champs `freshness` /
/// `status` / `age_seconds` du payload sont volontairement ignorés : dans un
/// instantané embarqué ils décrivent le passé, pas le présent.
DerivedFreshness deriveFreshness(
  String? observedAtRaw, {
  DataFamily family = DataFamily.price,
  DateTime? now,
}) {
  if (observedAtRaw == null || observedAtRaw.isEmpty) {
    return DerivedFreshness.unknown;
  }
  final observed = DateTime.tryParse(observedAtRaw)?.toUtc();
  if (observed == null) return DerivedFreshness.unknown;

  final reference = (now ?? DateTime.now()).toUtc();
  final age = reference.difference(observed);

  // Un horodatage nettement dans le futur signale une horloge fausse quelque
  // part. On ne le présente pas comme frais : on avoue ne pas savoir.
  if (age.isNegative && age.abs() > const Duration(minutes: 5)) {
    return DerivedFreshness(
      state: FreshnessState.unavailable,
      observedAt: observed,
    );
  }

  final seconds = age.isNegative ? 0 : age.inSeconds;
  final state = switch (seconds) {
    _ when seconds <= family.live => FreshnessState.live,
    _ when seconds <= family.recent => FreshnessState.recent,
    _ when seconds <= family.delayed => FreshnessState.delayed,
    _ => FreshnessState.stale,
  };

  return DerivedFreshness(
    state: state,
    age: age.isNegative ? Duration.zero : age,
    observedAt: observed,
  );
}
