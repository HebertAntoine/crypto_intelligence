/// Traduction des états du domaine, en un seul endroit.
///
/// Les moteurs raisonnent en anglais et c'est très bien : leurs enums sont des
/// identifiants, pas du texte. Le défaut était qu'ils traversaient l'app
/// jusqu'à l'écran — « REINTEGRATION to the up through 81375.745 »,
/// « 4h price is near range top », « strongly bullish ».
///
/// Rien ici ne décide : cette couche nomme. Si un état n'est pas reconnu, elle
/// le rend lisible plutôt que de mentir, et un test échoue sur tout identifiant
/// brut atteignant l'interface.
library;

String regimeLabel(String raw) => switch (raw.toUpperCase()) {
      'STRONGLY_BULLISH' => 'Fortement haussier',
      'BULLISH' => 'Haussier',
      'NEUTRAL' => 'Neutre',
      'BEARISH' => 'Baissier',
      'STRONGLY_BEARISH' => 'Fortement baissier',
      'UNDETERMINED' => 'Indéterminé',
      _ => readableFallback(raw),
    };

String structureLabel(String raw) => switch (raw.toUpperCase()) {
      'BULLISH_STRUCTURE' => 'Structure haussière',
      'BEARISH_STRUCTURE' => 'Structure baissière',
      'RANGE_STRUCTURE' => 'En range',
      'UNDETERMINED_STRUCTURE' || 'UNDETERMINED' => 'Structure indéterminée',
      _ => readableFallback(raw),
    };

String locationLabel(String raw) => switch (raw.toUpperCase()) {
      'NEAR_RANGE_TOP' => 'Proche du haut du range',
      'NEAR_RANGE_BOTTOM' => 'Proche du bas du range',
      'MID_RANGE' => 'Milieu de range',
      'ABOVE_RANGE' => 'Au-dessus du range',
      'BELOW_RANGE' => 'Sous le range',
      'NO_RANGE' => 'Aucun range validé',
      _ => readableFallback(raw),
    };

String breakoutLabel(String raw) => switch (raw.toUpperCase()) {
      'BREAKOUT_UP' => 'Cassure haussière',
      'BREAKOUT_DOWN' => 'Cassure baissière',
      'REINTEGRATION' => 'Réintégration du range',
      'REINTEGRATION_UP' => 'Réintégration par le haut',
      'REINTEGRATION_DOWN' => 'Réintégration par le bas',
      'FALSE_BREAKOUT' => 'Fausse cassure',
      'NONE' || 'NO_BREAKOUT' => 'Aucune cassure récente',
      _ => readableFallback(raw),
    };

String fundingLabel(String raw) => switch (raw.toUpperCase()) {
      'EXTREME_NEGATIVE' => 'Très négatif',
      'NEGATIVE' => 'Plutôt faible',
      'NEUTRAL' => 'Neutre',
      'POSITIVE' => 'Plutôt élevé',
      'EXTREME_POSITIVE' => 'Très élevé',
      'UNKNOWN' => 'Indéterminé',
      _ => readableFallback(raw),
    };

String crowdingLabelFr(String raw) => switch (raw.toUpperCase()) {
      'LOW' => 'Faible',
      'NORMAL' => 'Normal',
      'ELEVATED' => 'Élevé',
      'EXTREME' => 'Extrême',
      'UNKNOWN' => 'Indéterminé',
      _ => readableFallback(raw),
    };

String volatilityLabelFr(String raw) => switch (raw.toUpperCase()) {
      'LOW' => 'Faible',
      'NORMAL' => 'Normale',
      'HIGH' => 'Élevée',
      'EXTREME' => 'Extrême',
      _ => readableFallback(raw),
    };

String edgeLabelFr(String raw) => switch (raw.toUpperCase()) {
      'POSITIVE_EDGE' => 'Avantage mesuré',
      'NEGATIVE_EDGE' => 'Avantage défavorable',
      'NO_MEASURABLE_EDGE' => 'Aucun avantage statistique démontré',
      'UNSTABLE' => 'Avantage instable',
      'INSUFFICIENT_DATA' => 'Données insuffisantes',
      'NOT_YET_TESTED' => 'Pas encore testé',
      _ => readableFallback(raw),
    };

String entryOpportunityLabel(String raw) => switch (raw.toUpperCase()) {
      'VERY_FAVORABLE' => 'Très favorable',
      'FAVORABLE' => 'Favorable',
      'NEUTRAL' => 'Neutre',
      'UNFAVORABLE' => 'Défavorable',
      'VERY_UNFAVORABLE' => 'Très défavorable',
      'INSUFFICIENT_DATA' => 'Données insuffisantes',
      _ => readableFallback(raw),
    };

String freshnessLabelFr(String raw) => switch (raw.toUpperCase()) {
      'LIVE' => 'À jour',
      'RECENT' => 'Récent',
      'DELAYED' => 'Différé',
      'STALE' => 'Périmé',
      'UNAVAILABLE' => 'Indisponible',
      _ => readableFallback(raw),
    };

String evidenceLabel(String raw) => switch (raw.toUpperCase()) {
      'FACT' => 'Fait mesuré',
      'COMPUTATION' => 'Calcul',
      'INTERPRETATION' => 'Interprétation',
      'HYPOTHESIS' => 'Hypothèse',
      'MISSING' => 'Absent',
      _ => readableFallback(raw),
    };

/// Un identifiant non reconnu devient lisible plutôt que brut.
///
/// Ce n'est pas une traduction : c'est un filet. Le test « aucun enum brut »
/// existe pour que ce filet ne serve jamais en pratique.
String readableFallback(String raw) {
  if (raw.isEmpty) return '—';
  final words = raw.replaceAll('_', ' ').toLowerCase().trim();
  if (words.isEmpty) return '—';
  return '${words[0].toUpperCase()}${words.substring(1)}';
}

/// Vrai si la chaîne ressemble à un identifiant technique et non à du français.
///
/// Utilisé par les tests : SCREAMING_SNAKE_CASE, ou un mot entièrement en
/// majuscules de plus de trois lettres, ne doit jamais atteindre l'écran.
bool looksLikeRawEnum(String value) {
  final trimmed = value.trim();
  if (trimmed.length < 4) return false;
  if (trimmed.contains('_') && trimmed == trimmed.toUpperCase()) return true;
  return RegExp(r'^[A-Z]{4,}$').hasMatch(trimmed);
}
