/// La page « Aujourd'hui », telle que le backend l'a composée.
///
/// Rien n'est décidé ici. Chaque bloc vient d'un même `AnalysisContextSnapshot`
/// et porte son `analysisId`: si deux blocs affichés ensemble n'ont pas le même
/// identifiant, ils décrivent deux instants différents et l'écran doit refuser
/// de les combiner plutôt que de les empiler silencieusement.
///
/// Les libellés arrivent déjà en français. Les champs `state`, `direction` et
/// `coverage` restent des identifiants: l'app s'en sert pour choisir une
/// couleur ou une icône, jamais pour les afficher.
library;

double? _double(dynamic value) => (value as num?)?.toDouble();

int _int(dynamic value, [int fallback = 0]) =>
    (value as num?)?.toInt() ?? fallback;

String _string(dynamic value, [String fallback = '']) =>
    value as String? ?? fallback;

Map<String, dynamic> _map(dynamic value) =>
    ((value as Map?) ?? const {}).cast<String, dynamic>();

List<Map<String, dynamic>> _list(dynamic value) =>
    ((value as List?) ?? const [])
        .map((item) => (item as Map).cast<String, dynamic>())
        .toList();

/// Une des trois lectures indépendantes: direction, timing, avantage démontré.
class ReadingLine {
  final String value;
  final String state;
  final String detail;
  final String question;

  const ReadingLine({
    this.value = 'Indisponible',
    this.state = 'UNKNOWN',
    this.detail = '',
    this.question = '',
  });

  factory ReadingLine.fromJson(Map<String, dynamic> json) => ReadingLine(
        value: _string(json['value'], 'Indisponible'),
        state: _string(json['state'], 'UNKNOWN'),
        detail: _string(json['detail']),
        question: _string(json['question']),
      );
}

/// Direction, timing et avantage ne sont jamais fusionnés en un seul score.
/// « Fortement haussière + attendre + aucun avantage démontré » est une
/// combinaison cohérente, et la plus fréquente que ce système produise.
class DirectionTimingEdge {
  final ReadingLine direction;
  final ReadingLine timing;
  final ReadingLine edge;
  final String note;

  const DirectionTimingEdge({
    this.direction = const ReadingLine(),
    this.timing = const ReadingLine(),
    this.edge = const ReadingLine(),
    this.note = '',
  });

  static const unavailable = DirectionTimingEdge();

  factory DirectionTimingEdge.fromJson(Map<String, dynamic> json) =>
      DirectionTimingEdge(
        direction: ReadingLine.fromJson(_map(json['direction'])),
        timing: ReadingLine.fromJson(_map(json['timing'])),
        edge: ReadingLine.fromJson(_map(json['edge'])),
        note: _string(json['note']),
      );
}

/// Où le prix se situe dans son range — quand un range validé existe.
///
/// `hasRange` faux n'est pas une donnée manquante: c'est une structure qui
/// n'est pas un range. Aucune borne n'est alors fabriquée pour remplir la
/// barre, parce qu'une fausse précision serait pire que pas de barre.
class StructuralPosition {
  final bool hasRange;
  final String timeframe;
  final String headline;
  final String state;
  final String detail;
  final String reason;
  final String note;
  final String invalidation;
  final double? rangeBottom;
  final double? rangeMidpoint;
  final double? rangeTop;
  final double? price;
  final double? relativePosition;
  final int? percent;
  final String bottomLabel;
  final String topLabel;

  const StructuralPosition({
    this.hasRange = false,
    this.timeframe = '4H',
    this.headline = 'Indisponible',
    this.state = 'NO_VALID_RANGE',
    this.detail = '',
    this.reason = '',
    this.note = '',
    this.invalidation = '',
    this.rangeBottom,
    this.rangeMidpoint,
    this.rangeTop,
    this.price,
    this.relativePosition,
    this.percent,
    this.bottomLabel = 'Bas du range',
    this.topLabel = 'Haut du range',
  });

  static const unavailable = StructuralPosition();

  /// Position dessinable, bornée à la barre. La valeur brute reste lisible
  /// dans `relativePosition`: un prix sorti du range n'est pas « à 100 % ».
  double get fraction {
    final raw = relativePosition;
    if (raw == null) return 0;
    return raw.clamp(0.0, 1.0).toDouble();
  }

  factory StructuralPosition.fromJson(Map<String, dynamic> json) =>
      StructuralPosition(
        hasRange: json['has_range'] as bool? ?? false,
        timeframe: _string(json['timeframe'], '4H'),
        headline: _string(json['headline'], 'Indisponible'),
        state: _string(json['state'], 'NO_VALID_RANGE'),
        detail: _string(json['detail']),
        reason: _string(json['reason']),
        note: _string(json['note']),
        invalidation: _string(json['invalidation']),
        rangeBottom: _double(json['range_bottom']),
        rangeMidpoint: _double(json['range_midpoint']),
        rangeTop: _double(json['range_top']),
        price: _double(json['price']),
        relativePosition: _double(json['relative_position']),
        percent: (json['percent'] as num?)?.toInt(),
        bottomLabel: _string(json['bottom_label'], 'Bas du range'),
        topLabel: _string(json['top_label'], 'Haut du range'),
      );
}

class PriceLevel {
  final double price;
  final double distancePct;
  final int? touches;
  final double? strength;

  const PriceLevel({
    required this.price,
    required this.distancePct,
    this.touches,
    this.strength,
  });

  static PriceLevel? maybe(dynamic value) {
    if (value is! Map) return null;
    final json = value.cast<String, dynamic>();
    final price = _double(json['price']);
    final distance = _double(json['distance_pct']);
    if (price == null || distance == null) return null;
    return PriceLevel(
      price: price,
      distancePct: distance,
      touches: (json['touches'] as num?)?.toInt(),
      strength: _double(json['strength']),
    );
  }
}

class NearestLevels {
  final bool available;
  final double? referencePrice;
  final PriceLevel? support;
  final PriceLevel? resistance;
  final String source;
  final String reason;

  const NearestLevels({
    this.available = false,
    this.referencePrice,
    this.support,
    this.resistance,
    this.source = '',
    this.reason = '',
  });

  static const unavailable = NearestLevels();

  factory NearestLevels.fromJson(Map<String, dynamic> json) => NearestLevels(
        available: json['available'] as bool? ?? false,
        referencePrice: _double(json['reference_price']),
        support: PriceLevel.maybe(json['support']),
        resistance: PriceLevel.maybe(json['resistance']),
        source: _string(json['source']),
        reason: _string(json['reason']),
      );
}

class ContextItem {
  final String label;
  final String value;
  final String detail;

  const ContextItem({
    required this.label,
    required this.value,
    this.detail = '',
  });

  factory ContextItem.fromJson(Map<String, dynamic> json) => ContextItem(
        label: _string(json['label']),
        value: _string(json['value']),
        detail: _string(json['detail']),
      );
}

/// Une échéance programmée et sourcée, pas une actualité.
class Catalyst {
  final String kind;
  final String name;
  final String when;
  final String importance;
  final String importanceLabel;
  final double hoursUntil;
  final List<String> assetScope;
  final String source;

  const Catalyst({
    required this.name,
    required this.when,
    this.kind = '',
    this.importance = 'MEDIUM',
    this.importanceLabel = 'Modéré',
    this.hoursUntil = 0,
    this.assetScope = const [],
    this.source = '',
  });

  bool get isMajor => importance == 'CRITICAL';

  factory Catalyst.fromJson(Map<String, dynamic> json) => Catalyst(
        kind: _string(json['kind']),
        name: _string(json['name']),
        when: _string(json['when']),
        importance: _string(json['importance'], 'MEDIUM'),
        importanceLabel: _string(json['importance_label'], 'Modéré'),
        hoursUntil: _double(json['hours_until']) ?? 0,
        assetScope: ((json['asset_scope'] as List?) ?? const [])
            .map((item) => '$item')
            .toList(),
        source: _string(json['source']),
      );
}

class CatalystAlert {
  final String label;
  final String name;
  final double hoursUntil;
  final String note;

  const CatalystAlert({
    required this.label,
    required this.name,
    required this.hoursUntil,
    required this.note,
  });
}

class Catalysts {
  final List<Catalyst> items;
  final CatalystAlert? alert;
  final String horizonNote;
  final String notNews;

  const Catalysts({
    this.items = const [],
    this.alert,
    this.horizonNote = '',
    this.notNews = '',
  });

  static const empty = Catalysts();

  factory Catalysts.fromJson(Map<String, dynamic> json) {
    final rawAlert = json['alert'];
    return Catalysts(
      items: _list(json['items']).map(Catalyst.fromJson).toList(),
      alert: rawAlert is Map
          ? CatalystAlert(
              label: _string(rawAlert['label']),
              name: _string(rawAlert['name']),
              hoursUntil: _double(rawAlert['hours_until']) ?? 0,
              note: _string(rawAlert['note']),
            )
          : null,
      horizonNote: _string(json['horizon_note']),
      notNews: _string(json['not_news']),
    );
  }
}

/// Trois catégories, jamais deux. Une cassure du haut de range invalide le
/// range sans dégrader la lecture: la ranger dans « ce qui dégraderait »
/// faisait lire une cassure haussière comme une mauvaise nouvelle.
class ChangeConditions {
  final List<String> improve;
  final List<String> degrade;
  final List<String> structureChange;
  final String improveTitle;
  final String degradeTitle;
  final String structureChangeTitle;
  final String note;

  const ChangeConditions({
    this.improve = const [],
    this.degrade = const [],
    this.structureChange = const [],
    this.improveTitle = 'POUR DEVENIR PLUS FAVORABLE',
    this.degradeTitle = 'POUR DEVENIR MOINS FAVORABLE',
    this.structureChangeTitle = 'CHANGEMENT À SURVEILLER',
    this.note = '',
  });

  static const empty = ChangeConditions();

  bool get isEmpty =>
      improve.isEmpty && degrade.isEmpty && structureChange.isEmpty;

  static List<String> _texts(dynamic value) =>
      _list(value).map((item) => _string(item['text'])).toList();

  factory ChangeConditions.fromJson(Map<String, dynamic> json) =>
      ChangeConditions(
        improve: _texts(json['improve']),
        degrade: _texts(json['degrade']),
        structureChange: _texts(json['structure_change']),
        improveTitle:
            _string(json['improve_title'], 'POUR DEVENIR PLUS FAVORABLE'),
        degradeTitle:
            _string(json['degrade_title'], 'POUR DEVENIR MOINS FAVORABLE'),
        structureChangeTitle:
            _string(json['structure_change_title'], 'CHANGEMENT À SURVEILLER'),
        note: _string(json['note']),
      );
}

class TimeframeRow {
  final String timeframe;
  final String state;
  final String label;
  final String arrow;

  const TimeframeRow({
    required this.timeframe,
    required this.state,
    required this.label,
    required this.arrow,
  });

  factory TimeframeRow.fromJson(Map<String, dynamic> json) => TimeframeRow(
        timeframe: _string(json['timeframe']),
        state: _string(json['state'], 'UNCLEAR'),
        label: _string(json['label'], 'Indéterminée'),
        arrow: _string(json['arrow'], '↔'),
      );
}

class TimeframeSummary {
  final List<TimeframeRow> rows;
  final String alignment;
  final String alignmentLabel;
  final String note;

  const TimeframeSummary({
    this.rows = const [],
    this.alignment = 'UNDETERMINED',
    this.alignmentLabel = 'Indéterminé',
    this.note = '',
  });

  static const empty = TimeframeSummary();

  factory TimeframeSummary.fromJson(Map<String, dynamic> json) =>
      TimeframeSummary(
        rows: _list(json['rows']).map(TimeframeRow.fromJson).toList(),
        alignment: _string(json['alignment'], 'UNDETERMINED'),
        alignmentLabel: _string(json['alignment_label'], 'Indéterminé'),
        note: _string(json['note']),
      );
}

class ContradictionNote {
  final String title;
  final String text;

  const ContradictionNote({required this.title, required this.text});
}

class Contradictions {
  final List<ContradictionNote> items;
  final String badge;

  const Contradictions({this.items = const [], this.badge = ''});

  static const none = Contradictions();

  bool get has => badge.isNotEmpty;

  factory Contradictions.fromJson(Map<String, dynamic> json) => Contradictions(
        items: _list(json['items'])
            .map((item) => ContradictionNote(
                  title: _string(item['title']),
                  text: _string(item['text']),
                ))
            .toList(),
        badge: _string(json['badge']),
      );
}

/// Volatilité réalisée et volatilité implicite, jamais additionnées: l'une
/// décrit ce qui s'est produit, l'autre ce que les options font payer.
class VolatilityReading {
  final String headline;
  final String realisedLabel;
  final String realisedDirection;
  final bool impliedAvailable;
  final String impliedLabel;
  final String impliedReason;
  final String note;

  const VolatilityReading({
    this.headline = 'Inconnue',
    this.realisedLabel = 'Inconnue',
    this.realisedDirection = 'STABLE',
    this.impliedAvailable = false,
    this.impliedLabel = 'Indisponible',
    this.impliedReason = '',
    this.note = '',
  });

  static const unavailable = VolatilityReading();

  factory VolatilityReading.fromJson(Map<String, dynamic> json) {
    final realised = _map(json['realised']);
    final implied = _map(json['implied']);
    return VolatilityReading(
      headline: _string(json['headline'], 'Inconnue'),
      realisedLabel: _string(realised['label'], 'Inconnue'),
      realisedDirection: _string(realised['direction'], 'STABLE'),
      impliedAvailable: implied['available'] as bool? ?? false,
      impliedLabel: _string(implied['label'], 'Indisponible'),
      impliedReason: _string(implied['reason']),
      note: _string(json['note']),
    );
  }
}

/// Ce qu'une famille apporte à la pression acheteuse ou vendeuse.
///
/// Une source absente n'est ni neutre ni zéro: elle sort du calcul et reste
/// listée, avec la raison de son absence.
class PressureContribution {
  final String family;
  final String label;
  final bool available;
  final double? normalizedScore;
  final double? contributionPoints;
  final String direction;
  final double weight;
  final String source;
  final String? timestamp;
  final String freshness;
  final String explanation;

  const PressureContribution({
    required this.family,
    required this.label,
    this.available = false,
    this.normalizedScore,
    this.contributionPoints,
    this.direction = 'UNKNOWN',
    this.weight = 0,
    this.source = '',
    this.timestamp,
    this.freshness = 'UNAVAILABLE',
    this.explanation = '',
  });

  factory PressureContribution.fromJson(Map<String, dynamic> json) =>
      PressureContribution(
        family: _string(json['family']),
        label: _string(json['label']),
        available: json['available'] as bool? ?? false,
        normalizedScore: _double(json['normalized_score']),
        contributionPoints: _double(json['contribution_points']),
        direction: _string(json['direction'], 'UNKNOWN'),
        weight: _double(json['weight_if_any']) ?? 0,
        source: _string(json['source']),
        timestamp: json['timestamp'] as String?,
        freshness: _string(json['freshness'], 'UNAVAILABLE'),
        explanation: _string(json['explanation']),
      );
}

class PressureBreakdown {
  final String state;
  final String label;
  final String headline;
  final double? score;
  final int familiesActive;
  final int familiesTotal;
  final String familiesLine;
  final List<PressureContribution> buyers;
  final List<PressureContribution> sellers;
  final List<PressureContribution> neutral;
  final List<PressureContribution> unavailable;
  final String buyersTitle;
  final String sellersTitle;
  final String unavailableTitle;
  final List<String> contradictions;
  final String tooltip;
  final String missingNote;

  const PressureBreakdown({
    this.state = 'INSUFFICIENT_DATA',
    this.label = 'INDÉTERMINÉ',
    this.headline = 'Pression indéterminée',
    this.score,
    this.familiesActive = 0,
    this.familiesTotal = 0,
    this.familiesLine = '',
    this.buyers = const [],
    this.sellers = const [],
    this.neutral = const [],
    this.unavailable = const [],
    this.buyersTitle = 'FACTEURS ACHETEURS',
    this.sellersTitle = 'FACTEURS VENDEURS',
    this.unavailableTitle = 'INDISPONIBLE',
    this.contradictions = const [],
    this.tooltip = '',
    this.missingNote = '',
  });

  static const empty = PressureBreakdown();

  static List<PressureContribution> _items(dynamic value) =>
      _list(value).map(PressureContribution.fromJson).toList();

  factory PressureBreakdown.fromJson(Map<String, dynamic> json) =>
      PressureBreakdown(
        state: _string(json['state'], 'INSUFFICIENT_DATA'),
        label: _string(json['label'], 'INDÉTERMINÉ'),
        headline: _string(json['headline'], 'Pression indéterminée'),
        score: _double(json['score']),
        familiesActive: _int(json['families_active']),
        familiesTotal: _int(json['families_total']),
        familiesLine: _string(json['families_line']),
        buyers: _items(json['buyers']),
        sellers: _items(json['sellers']),
        neutral: _items(json['neutral']),
        unavailable: _items(json['unavailable']),
        buyersTitle: _string(json['buyers_title'], 'FACTEURS ACHETEURS'),
        sellersTitle: _string(json['sellers_title'], 'FACTEURS VENDEURS'),
        unavailableTitle: _string(json['unavailable_title'], 'INDISPONIBLE'),
        contradictions: ((json['contradictions'] as List?) ?? const [])
            .map((item) => '$item')
            .toList(),
        tooltip: _string(json['tooltip']),
        missingNote: _string(json['missing_note']),
      );
}

class CoverageFamily {
  final String family;
  final String label;
  final String coverage;
  final bool available;
  final bool fresh;
  final bool stale;
  final String reason;

  const CoverageFamily({
    required this.family,
    required this.label,
    required this.coverage,
    this.available = false,
    this.fresh = false,
    this.stale = false,
    this.reason = '',
  });

  factory CoverageFamily.fromJson(Map<String, dynamic> json) => CoverageFamily(
        family: _string(json['family']),
        label: _string(json['label']),
        coverage: _string(json['coverage'], 'EXPECTED_BUT_MISSING'),
        available: json['available'] as bool? ?? false,
        fresh: json['fresh'] as bool? ?? false,
        stale: json['stale'] as bool? ?? false,
        reason: _string(json['reason']),
      );
}

/// Combien de l'information visée a pu être réellement observée.
///
/// À ne pas confondre avec l'incertitude: « incertitude 60/100 élevée » et
/// « couverture 85 % bonne » sont parfaitement compatibles. La première décrit
/// la solidité de la conclusion, la seconde ce que nous avons pu regarder.
class DataCoverage {
  final int expected;
  final int available;
  final int fresh;
  final int stale;
  final int missing;
  final int? percent;
  final String level;
  final String label;
  final String summary;
  final List<CoverageFamily> families;
  final double? uncertaintyScore;
  final String uncertaintyNote;
  final String note;
  final Map<String, String> titles;

  const DataCoverage({
    this.expected = 0,
    this.available = 0,
    this.fresh = 0,
    this.stale = 0,
    this.missing = 0,
    this.percent,
    this.level = 'UNKNOWN',
    this.label = 'Couverture inconnue',
    this.summary = '',
    this.families = const [],
    this.uncertaintyScore,
    this.uncertaintyNote = '',
    this.note = '',
    this.titles = const {},
  });

  static const unavailable = DataCoverage();

  List<CoverageFamily> get availableFamilies => families
      .where((item) => item.coverage == 'EXPECTED_AND_AVAILABLE')
      .toList();

  List<CoverageFamily> get missingFamilies => families
      .where((item) => item.coverage == 'EXPECTED_BUT_MISSING')
      .toList();

  List<CoverageFamily> get notApplicableFamilies =>
      families.where((item) => item.coverage == 'NOT_APPLICABLE').toList();

  List<CoverageFamily> get byDesignFamilies => families
      .where((item) => item.coverage == 'UNAVAILABLE_BY_DESIGN')
      .toList();

  factory DataCoverage.fromJson(Map<String, dynamic> json) => DataCoverage(
        expected: _int(json['expected']),
        available: _int(json['available']),
        fresh: _int(json['fresh']),
        stale: _int(json['stale']),
        missing: _int(json['missing']),
        percent: (json['percent'] as num?)?.toInt(),
        level: _string(json['level'], 'UNKNOWN'),
        label: _string(json['label'], 'Couverture inconnue'),
        summary: _string(json['summary']),
        families: _list(json['families']).map(CoverageFamily.fromJson).toList(),
        uncertaintyScore: _double(json['uncertainty_score']),
        uncertaintyNote: _string(json['uncertainty_note']),
        note: _string(json['note']),
        titles:
            _map(json['titles']).map((key, value) => MapEntry(key, '$value')),
      );
}

/// Le dernier changement de verdict, uniquement s'il a été enregistré.
/// Rien n'est reconstruit après coup: sans historique, ce bloc n'apparaît pas.
class LastDecisionChange {
  final bool available;
  final String title;
  final String changedAt;
  final String text;
  final String reason;
  final String unavailableReason;

  const LastDecisionChange({
    this.available = false,
    this.title = 'DERNIER CHANGEMENT DE LECTURE',
    this.changedAt = '',
    this.text = '',
    this.reason = '',
    this.unavailableReason = '',
  });

  static const none = LastDecisionChange();

  DateTime? get changedAtLocal =>
      DateTime.tryParse(changedAt)?.toUtc().toLocal();

  factory LastDecisionChange.fromJson(Map<String, dynamic> json) =>
      LastDecisionChange(
        available: json['available'] as bool? ?? false,
        title: _string(json['title'], 'DERNIER CHANGEMENT DE LECTURE'),
        changedAt: _string(json['changed_at']),
        text: _string(json['text']),
        reason: _string(json['reason']),
        unavailableReason: _string(json['reason']),
      );
}

class EtfReading {
  final bool available;
  final String headline;
  final double? latestMusd;
  final double? net5dMusd;
  final double? net20dMusd;
  final String source;
  final String reason;
  final String caveat;

  const EtfReading({
    this.available = false,
    this.headline = 'Indisponible',
    this.latestMusd,
    this.net5dMusd,
    this.net20dMusd,
    this.source = '',
    this.reason = '',
    this.caveat = '',
  });

  static const unavailable = EtfReading();

  factory EtfReading.fromJson(Map<String, dynamic> json) => EtfReading(
        available: json['available'] as bool? ?? false,
        headline: _string(json['headline'], 'Indisponible'),
        latestMusd: _double(json['latest_musd']),
        net5dMusd: _double(json['net_5d_musd']),
        net20dMusd: _double(json['net_20d_musd']),
        source: _string(json['source']),
        reason: _string(json['reason']),
        caveat: _string(json['caveat']),
      );
}

class PositioningReading {
  final String positioning;
  final String funding;
  final String crowding;
  final String note;

  const PositioningReading({
    this.positioning = 'Indisponible',
    this.funding = 'Indisponible',
    this.crowding = 'Inconnu',
    this.note = '',
  });

  static const unavailable = PositioningReading();

  factory PositioningReading.fromJson(Map<String, dynamic> json) =>
      PositioningReading(
        positioning:
            _string(_map(json['positioning'])['value'], 'Indisponible'),
        funding: _string(_map(json['funding'])['value'], 'Indisponible'),
        crowding: _string(_map(json['crowding'])['value'], 'Inconnu'),
        note: _string(json['note']),
      );
}

class DecisionText {
  final String state;
  final String headline;
  final String label;
  final String sentence;
  final List<String> guardRails;

  const DecisionText({
    this.state = 'INSUFFICIENT_DATA',
    this.headline = 'DONNÉES INSUFFISANTES',
    this.label = 'DONNÉES INSUFFISANTES',
    this.sentence = '',
    this.guardRails = const [],
  });

  static const unavailable = DecisionText();

  factory DecisionText.fromJson(Map<String, dynamic> json) => DecisionText(
        state: _string(json['state'], 'INSUFFICIENT_DATA'),
        headline: _string(json['headline'], 'DONNÉES INSUFFISANTES'),
        label: _string(json['label'], 'DONNÉES INSUFFISANTES'),
        sentence: _string(json['sentence']),
        guardRails: ((json['guard_rails'] as List?) ?? const [])
            .map((item) => '$item')
            .toList(),
      );
}

class TodayPage {
  final String analysisId;
  final String analysisTime;
  final double? priceAtAnalysis;
  final DirectionTimingEdge readings;
  final DecisionText decision;
  final StructuralPosition position;
  final NearestLevels levels;
  final List<ContextItem> immediateContext;
  final PressureBreakdown pressure;
  final Catalysts catalysts;
  final ChangeConditions changeConditions;
  final TimeframeSummary timeframes;
  final Contradictions contradictions;
  final VolatilityReading volatility;
  final PositioningReading positioning;
  final EtfReading etf;
  final DataCoverage coverage;
  final LastDecisionChange lastChange;

  const TodayPage({
    this.analysisId = '',
    this.analysisTime = '',
    this.priceAtAnalysis,
    this.readings = DirectionTimingEdge.unavailable,
    this.decision = DecisionText.unavailable,
    this.position = StructuralPosition.unavailable,
    this.levels = NearestLevels.unavailable,
    this.immediateContext = const [],
    this.pressure = PressureBreakdown.empty,
    this.catalysts = Catalysts.empty,
    this.changeConditions = ChangeConditions.empty,
    this.timeframes = TimeframeSummary.empty,
    this.contradictions = Contradictions.none,
    this.volatility = VolatilityReading.unavailable,
    this.positioning = PositioningReading.unavailable,
    this.etf = EtfReading.unavailable,
    this.coverage = DataCoverage.unavailable,
    this.lastChange = LastDecisionChange.none,
  });

  /// Vrai quand le backend est plus ancien que cette page et ne l'envoie pas.
  /// L'écran retombe alors sur les blocs qu'il sait déjà rendre.
  static const unavailable = TodayPage();

  bool get isEmpty => analysisId.isEmpty;

  factory TodayPage.fromJson(Map<String, dynamic> json) => TodayPage(
        analysisId: _string(json['analysis_id']),
        analysisTime: _string(json['analysis_time']),
        priceAtAnalysis: _double(json['price_at_analysis']),
        readings:
            DirectionTimingEdge.fromJson(_map(json['direction_timing_edge'])),
        decision: DecisionText.fromJson(_map(json['decision'])),
        position:
            StructuralPosition.fromJson(_map(json['structural_position'])),
        levels: NearestLevels.fromJson(_map(json['levels'])),
        immediateContext:
            _list(json['immediate_context']).map(ContextItem.fromJson).toList(),
        pressure: PressureBreakdown.fromJson(_map(json['pressure'])),
        catalysts: Catalysts.fromJson(_map(json['catalysts'])),
        changeConditions:
            ChangeConditions.fromJson(_map(json['change_conditions'])),
        timeframes: TimeframeSummary.fromJson(_map(json['timeframes'])),
        contradictions: Contradictions.fromJson(_map(json['contradictions'])),
        volatility: VolatilityReading.fromJson(_map(json['volatility'])),
        positioning: PositioningReading.fromJson(_map(json['positioning'])),
        etf: EtfReading.fromJson(_map(json['etf'])),
        coverage: DataCoverage.fromJson(_map(json['coverage'])),
        lastChange: LastDecisionChange.fromJson(_map(json['last_change'])),
      );
}
