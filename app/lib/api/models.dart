/// Data models mirroring the backend payloads.
///
/// Every model that carries a recognition confidence also carries an edge
/// state, because the UI must never be able to render the first without the
/// second. That separation is the whole point of the system: a pattern can be
/// recognised perfectly and still predict nothing.
library;

import 'freshness.dart';

/// Whether a relationship has actually been shown to precede anything.
enum EdgeState {
  positiveEdge,
  negativeEdge,
  noMeasurableEdge,
  unstable,
  insufficientData,
  notYetTested,
  unknown;

  static EdgeState parse(String? raw) => switch (raw) {
        'POSITIVE_EDGE' => EdgeState.positiveEdge,
        'NEGATIVE_EDGE' => EdgeState.negativeEdge,
        'NO_MEASURABLE_EDGE' => EdgeState.noMeasurableEdge,
        'UNSTABLE' => EdgeState.unstable,
        'INSUFFICIENT_DATA' => EdgeState.insufficientData,
        'NOT_YET_TESTED' => EdgeState.notYetTested,
        _ => EdgeState.unknown,
      };

  String get label => switch (this) {
        EdgeState.positiveEdge => 'Edge mesurable',
        EdgeState.negativeEdge => 'Edge opposé au signal',
        EdgeState.noMeasurableEdge => 'Aucun edge mesurable',
        EdgeState.unstable => 'Instable',
        EdgeState.insufficientData => 'Données insuffisantes',
        EdgeState.notYetTested => 'Pas encore testé',
        EdgeState.unknown => 'Inconnu',
      };

  /// Only a positive edge is ever grounds for calling something actionable.
  bool get isMeasured => this == EdgeState.positiveEdge;
}

class DecisionSummary {
  final String asset;
  final String marketDirection;
  final String directionConfidence;
  final String entryTiming;
  final EdgeState edgeState;
  final String crowding;
  final String volatilityRegime;
  final double uncertainty;
  final bool actionable;
  final String statement;
  final List<String> caveats;

  const DecisionSummary({
    required this.asset,
    required this.marketDirection,
    required this.directionConfidence,
    required this.entryTiming,
    required this.edgeState,
    required this.crowding,
    required this.volatilityRegime,
    required this.uncertainty,
    required this.actionable,
    required this.statement,
    required this.caveats,
  });

  factory DecisionSummary.fromJson(Map<String, dynamic> json) =>
      DecisionSummary(
        asset: json['asset'] as String? ?? '',
        marketDirection: json['market_direction'] as String? ?? 'UNDETERMINED',
        directionConfidence: '${json['direction_confidence'] ?? '—'}',
        entryTiming: json['entry_timing'] as String? ?? 'UNDETERMINED',
        edgeState: EdgeState.parse(json['edge_state'] as String?),
        crowding: json['crowding'] as String? ?? 'UNKNOWN',
        volatilityRegime: json['volatility_regime'] as String? ?? 'UNKNOWN',
        uncertainty: (json['uncertainty'] as num?)?.toDouble() ?? 100,
        actionable: json['actionable'] as bool? ?? false,
        statement: json['statement'] as String? ?? '',
        caveats: (json['caveats'] as List?)?.cast<String>() ?? const [],
      );
}

class UncertaintyDriver {
  final String driver;
  final num contribution;
  final String detail;

  const UncertaintyDriver({
    required this.driver,
    required this.contribution,
    required this.detail,
  });

  factory UncertaintyDriver.fromJson(Map<String, dynamic> json) =>
      UncertaintyDriver(
        driver: json['driver'] as String? ?? '',
        contribution: json['contribution'] as num? ?? 0,
        detail: json['detail'] as String? ?? '',
      );
}

class MarketProviderRead {
  final String provider;
  final String source;
  final String status;
  final String unit;
  final double? price;
  final double? change24hPct;
  final String? timestamp;
  final String? fetchedAt;
  final String freshness;
  final String quality;
  final String message;

  const MarketProviderRead({
    required this.provider,
    required this.source,
    required this.status,
    required this.unit,
    required this.price,
    required this.change24hPct,
    required this.timestamp,
    required this.fetchedAt,
    required this.freshness,
    required this.quality,
    required this.message,
  });

  factory MarketProviderRead.fromJson(Map<String, dynamic> json) =>
      MarketProviderRead(
        provider: json['provider'] as String? ?? '',
        source: json['source'] as String? ?? '',
        status: json['status'] as String? ?? 'UNAVAILABLE',
        unit: json['unit'] as String? ?? '',
        price: (json['price'] as num?)?.toDouble(),
        change24hPct: (json['change_24h_pct'] as num?)?.toDouble(),
        timestamp: json['timestamp'] as String?,
        fetchedAt: json['fetched_at'] as String?,
        freshness: json['freshness'] as String? ?? 'UNAVAILABLE',
        quality: json['quality'] as String? ?? 'UNAVAILABLE',
        message: json['message'] as String? ?? '',
      );
}

class MarketPriceRead {
  final String asset;
  final String status;
  final double? priceUsd;
  final double? priceEur;
  final double? change24hPct;
  final String? timestamp;
  final String? asOf;
  final String? fetchedAt;
  final double? ageSeconds;
  final List<MarketProviderRead> providers;
  final int providerCount;
  final double? dispersionPct;
  final String quality;
  final String freshness;
  final double? fxRate;
  final String? fxTimestamp;
  final String? fxSource;
  final String method;

  const MarketPriceRead({
    required this.asset,
    required this.status,
    required this.priceUsd,
    required this.priceEur,
    required this.change24hPct,
    required this.timestamp,
    required this.asOf,
    required this.fetchedAt,
    required this.ageSeconds,
    required this.providers,
    required this.providerCount,
    required this.dispersionPct,
    required this.quality,
    required this.freshness,
    required this.fxRate,
    required this.fxTimestamp,
    required this.fxSource,
    required this.method,
  });

  /// Fraîcheur recalculée contre l'horloge courante.
  ///
  /// Les champs `status`, `freshness` et `ageSeconds` du payload sont
  /// conservés pour la traçabilité mais ne sont jamais affichés tels quels :
  /// dans un instantané embarqué ils sont figés à « LIVE · 0 s » pour
  /// toujours. Seul `asOf` (ou `timestamp` à défaut) est digne de confiance.
  DerivedFreshness derived({DateTime? now}) =>
      deriveFreshness(asOf ?? timestamp, family: DataFamily.price, now: now);

  /// Le prix ne doit être présenté comme une donnée de marché que si son
  /// horodatage le permet. `available` seul ne suffit pas : un instantané
  /// vieux de six mois reste « available ».
  bool trustworthyAt({DateTime? now}) =>
      available && displayPrice != null && derived(now: now).isTrustworthy;

  factory MarketPriceRead.fromJson(Map<String, dynamic> json) =>
      MarketPriceRead(
        asset: json['asset'] as String? ?? '',
        status: json['status'] as String? ?? 'UNAVAILABLE',
        priceUsd: (json['price_usd'] as num?)?.toDouble(),
        priceEur: (json['price_eur'] as num?)?.toDouble(),
        change24hPct: (json['change_24h_pct'] as num?)?.toDouble(),
        timestamp: json['timestamp'] as String?,
        asOf: json['as_of'] as String?,
        fetchedAt: json['fetched_at'] as String?,
        ageSeconds: (json['age_seconds'] as num?)?.toDouble(),
        providers: ((json['providers'] as List?) ?? const [])
            .map((item) => MarketProviderRead.fromJson(
                (item as Map).cast<String, dynamic>()))
            .toList(),
        providerCount: (json['provider_count'] as num?)?.toInt() ?? 0,
        dispersionPct: (json['dispersion_pct'] as num?)?.toDouble(),
        quality: json['quality'] as String? ?? 'UNAVAILABLE',
        freshness: json['freshness'] as String? ?? 'UNAVAILABLE',
        fxRate: (json['fx_rate'] as num?)?.toDouble(),
        fxTimestamp: json['fx_timestamp'] as String?,
        fxSource: json['fx_source'] as String?,
        method: json['method'] as String? ?? '',
      );

  bool get available => priceUsd != null && status != 'UNAVAILABLE';

  bool get displaysEur => priceEur != null;

  double? get displayPrice => priceEur ?? priceUsd;

  String get displayUnit => displaysEur ? 'EUR' : 'USD';
}

/// Une famille d'entrée, répondue quatre fois plutôt qu'une.
///
/// Le mot « OK » confondait quatre questions distinctes: la donnée existe-t-elle,
/// est-elle valide, est-elle assez récente, et peut-elle alimenter le verdict
/// affiché maintenant. Un instantané d'une heure répondait oui aux deux
/// premières et non aux deux dernières, et s'affichait quand même « OK ».
class FamilyState {
  final String family;
  final bool available;
  final bool valid;
  /// Tel que reçu: figé à l'instant du calcul backend. Ne pas afficher.
  /// Utiliser `derived()` et `usableNow()`.
  final String freshness;

  /// Tel que reçu, également figé. Voir `usableNow()`.
  final bool usable;
  final String? observedAt;
  final double? ageSeconds;
  final String source;
  final int? points;
  final String reason;

  const FamilyState({
    required this.family,
    required this.available,
    required this.valid,
    required this.freshness,
    required this.usable,
    required this.observedAt,
    required this.ageSeconds,
    required this.source,
    required this.points,
    required this.reason,
  });

  /// Fraîcheur recalculée contre l'horloge courante.
  ///
  /// Les champs `freshness`, `age_seconds` et `usable` du payload sont figés
  /// à l'instant où le backend les a calculés. Dans un instantané embarqué ils
  /// affirment « À JOUR · il y a 1 s » indéfiniment, ce qui est exactement
  /// l'affirmation que cette page existe pour ne pas faire. Seul `observed_at`
  /// est digne de confiance, et tout se redérive de lui.
  DerivedFreshness derived({DateTime? now}) =>
      deriveFreshness(observedAt, family: familyFor(family), now: now);

  /// Utilisable maintenant, et non « utilisable au moment de l'export ».
  bool usableNow({DateTime? now}) =>
      available && valid && derived(now: now).isTrustworthy;

  /// L'âge réel, pas celui qu'un instantané transporte depuis sa capture.
  Duration? ageNow({DateTime? now}) => derived(now: now).age;

  factory FamilyState.fromJson(Map<String, dynamic> json) => FamilyState(
        family: json['family'] as String? ?? '',
        available: json['available'] as bool? ?? false,
        valid: json['valid'] as bool? ?? false,
        freshness: json['freshness'] as String? ?? 'UNAVAILABLE',
        usable: json['usable'] as bool? ?? false,
        observedAt: json['observed_at'] as String?,
        ageSeconds: (json['age_seconds'] as num?)?.toDouble(),
        source: json['source'] as String? ?? '',
        points: (json['points'] as num?)?.toInt(),
        reason: json['reason'] as String? ?? '',
      );
}

/// Qui achète et qui vend, décomposé par source mesurable.
class PressureComponent {
  final String name;
  final String label;
  final bool available;
  final double? score;
  final dynamic rawValue;
  final double weight;
  final double confidence;
  final String detail;
  final String source;
  final String reason;
  final String? asOf;
  final String freshness;

  const PressureComponent({
    required this.name,
    required this.label,
    required this.available,
    required this.score,
    required this.rawValue,
    required this.weight,
    required this.confidence,
    required this.detail,
    required this.source,
    required this.reason,
    required this.asOf,
    required this.freshness,
  });

  factory PressureComponent.fromJson(Map<String, dynamic> json) =>
      PressureComponent(
        name: json['name'] as String? ?? '',
        label: json['label'] as String? ?? '',
        available: json['available'] as bool? ?? false,
        score: ((json['normalized_pressure'] ?? json['score']) as num?)
            ?.toDouble(),
        rawValue: json['raw_value'],
        weight: (json['weight'] as num?)?.toDouble() ?? 1,
        confidence: (json['confidence'] as num?)?.toDouble() ?? .5,
        detail: json['detail'] as String? ?? '',
        source: json['source'] as String? ?? '',
        reason: json['reason'] as String? ?? '',
        asOf: json['as_of'] as String?,
        freshness: json['freshness'] as String? ?? 'UNAVAILABLE',
      );
}

class MarketPressure {
  final String state;
  final double? pressureScore;
  /// 0 = vente totale, 50 = équilibre, 100 = achat total. Null si rien
  /// n'est mesurable: une absence ne vaut pas un équilibre.
  final double? balance;
  final String label;
  final List<PressureComponent> components;
  final int measured;
  final List<String> missing;
  final String note;
  final List<String> contradictions;
  final String summary;
  final String? asOf;

  const MarketPressure({
    required this.state,
    required this.pressureScore,
    required this.balance,
    required this.label,
    required this.components,
    required this.measured,
    required this.missing,
    required this.note,
    required this.contradictions,
    required this.summary,
    required this.asOf,
  });

  static const unavailable = MarketPressure(
    state: 'INSUFFICIENT_DATA',
    pressureScore: null,
    balance: null,
    label: 'INDÉTERMINÉ',
    components: [],
    measured: 0,
    missing: [],
    note: '',
    contradictions: [],
    summary: '',
    asOf: null,
  );

  factory MarketPressure.fromJson(Map<String, dynamic> json) => MarketPressure(
        state: json['state'] as String? ?? 'INSUFFICIENT_DATA',
        pressureScore: (json['pressure_score'] as num?)?.toDouble(),
        balance: (json['balance'] as num?)?.toDouble() ??
            ((json['pressure_score'] as num?) == null
                ? null
                : ((json['pressure_score'] as num).toDouble() + 100) / 2),
        label: json['label'] as String? ?? 'INDÉTERMINÉ',
        components: ((json['components'] as List?) ?? const [])
            .map((item) =>
                PressureComponent.fromJson((item as Map).cast<String, dynamic>()))
            .toList(),
        measured: (json['components_measured'] as num?)?.toInt() ?? 0,
        missing: ((json['components_missing'] as List?) ?? const [])
            .map((item) => '$item')
            .toList(),
        note: json['note'] as String? ?? '',
        contradictions: ((json['contradictions'] as List?) ?? const [])
            .map((item) => '$item')
            .toList(),
        summary: json['summary'] as String? ?? json['note'] as String? ?? '',
        asOf: json['as_of'] as String?,
      );
}

/// Une échéance macro programmée. Elle ne prédit rien; elle explique
/// pourquoi attendre peut être raisonnable.
class MacroEvent {
  final String kind;
  final String name;
  final String importance;
  final double daysUntil;

  const MacroEvent({
    required this.kind,
    required this.name,
    required this.importance,
    required this.daysUntil,
  });

  bool get isCritical => importance.toUpperCase() == 'CRITICAL';

  factory MacroEvent.fromJson(Map<String, dynamic> json) => MacroEvent(
        kind: json['kind'] as String? ?? '',
        name: json['name'] as String? ?? '',
        importance: json['importance'] as String? ?? '',
        daysUntil: (json['days_until'] as num?)?.toDouble() ?? 0,
      );
}

/// Un élément qui pèse dans la décision, avec sa provenance.
class OpportunityFactor {
  final String id;
  final String category;
  final String title;
  final String explanation;
  final dynamic rawValue;
  final double? normalizedValue;
  final String polarity;
  final int importance;
  final double confidence;
  final String evidenceLevel;
  final String timeframe;
  final String source;
  final String? asOf;
  final String freshness;
  final bool available;

  const OpportunityFactor({
    required this.id,
    required this.category,
    required this.title,
    required this.explanation,
    required this.rawValue,
    required this.normalizedValue,
    required this.polarity,
    required this.importance,
    required this.confidence,
    required this.evidenceLevel,
    required this.timeframe,
    required this.source,
    required this.asOf,
    required this.freshness,
    required this.available,
  });

  factory OpportunityFactor.fromJson(Map<String, dynamic> json) =>
      OpportunityFactor(
        id: json['id'] as String? ?? '',
        category: json['category'] as String? ?? '',
        title: json['title'] as String? ?? '',
        explanation: json['short_text'] as String? ??
            json['explanation'] as String? ?? '',
        rawValue: json['raw_value'],
        normalizedValue: (json['normalized_value'] as num?)?.toDouble(),
        polarity: json['polarity'] as String? ?? 'NEUTRAL',
        importance: (json['importance'] as num?)?.toInt() ?? 0,
        confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
        evidenceLevel: json['evidence_level'] as String? ?? 'UNAVAILABLE',
        timeframe: json['timeframe'] as String? ?? '',
        source: json['source'] as String? ?? '',
        asOf: json['as_of'] as String?,
        freshness: json['freshness'] as String? ?? 'UNAVAILABLE',
        available: json['available'] as bool? ?? true,
      );
}

/// La décision et tout ce qui la justifie. Calculée côté backend: le
/// frontend ne recalcule jamais l'état, il l'affiche.
class BuyOpportunity {
  final String state;
  final String headline;
  final String summary;
  final List<OpportunityFactor> positives;
  final List<OpportunityFactor> waits;
  final List<OpportunityFactor> negatives;
  final List<OpportunityFactor> missing;
  final List<String> whatWouldImprove;
  final List<String> whatWouldDeteriorate;
  final List<String> guardRails;
  final String measuredEdgeState;
  final String disclaimer;
  final String? asOf;
  final Map<String, dynamic> provenance;

  const BuyOpportunity({
    required this.state,
    required this.headline,
    required this.summary,
    required this.positives,
    required this.waits,
    required this.negatives,
    required this.missing,
    required this.whatWouldImprove,
    required this.whatWouldDeteriorate,
    required this.guardRails,
    required this.measuredEdgeState,
    required this.disclaimer,
    required this.asOf,
    required this.provenance,
  });

  static const unavailable = BuyOpportunity(
    state: 'INSUFFICIENT_DATA',
    headline: 'DONNÉES INSUFFISANTES',
    summary: '',
    positives: [], waits: [], negatives: [], missing: [],
    whatWouldImprove: [], whatWouldDeteriorate: [], guardRails: [],
    measuredEdgeState: 'NO_MEASURABLE_EDGE',
    disclaimer: '',
    asOf: null,
    provenance: {},
  );

  bool get isEmpty => summary.isEmpty && positives.isEmpty && waits.isEmpty;

  static List<OpportunityFactor> _list(dynamic raw) =>
      ((raw as List?) ?? const [])
          .map((item) =>
              OpportunityFactor.fromJson((item as Map).cast<String, dynamic>()))
          .toList();

  static List<String> _strings(dynamic raw) =>
      ((raw as List?) ?? const []).map((item) => '$item').toList();

  factory BuyOpportunity.fromJson(Map<String, dynamic> json) => BuyOpportunity(
        state: json['state'] as String? ?? 'INSUFFICIENT_DATA',
        headline: json['headline'] as String? ?? '',
        summary: json['summary'] as String? ??
            json['short_summary'] as String? ?? '',
        positives: _list(json['positives']),
        waits: _list(json['waits']),
        negatives: _list(json['negatives']),
        missing: _list(json['missing']),
        whatWouldImprove: _strings(
            json['improvement_conditions'] ?? json['what_would_improve']),
        whatWouldDeteriorate: _strings(
            json['deterioration_conditions'] ??
                json['what_would_deteriorate']),
        guardRails: _strings(json['guard_rails_applied']),
        measuredEdgeState:
            json['measured_edge_state'] as String? ?? 'NO_MEASURABLE_EDGE',
        disclaimer: json['disclaimer'] as String? ?? '',
        asOf: json['as_of'] as String?,
        provenance: ((json['provenance'] as Map?) ?? const {})
            .cast<String, dynamic>(),
      );
}

class TodayRead {
  final String asset;
  final MarketPriceRead? marketData;
  final DecisionSummary summary;
  final String directionSource;
  final EdgeState edgeState;
  final int admittedCount;
  final int rejectedCount;
  final String edgeStatement;
  final String uncertaintyLevel;
  final double uncertaintyScore;
  final List<UncertaintyDriver> uncertaintyDrivers;
  final String crowdingLevel;
  final double? crowdingScore;
  final String crowdingDirection;
  final String leverageState;
  final String fundingBand;
  final double? fundingPercentile;
  final String volatilityRegime;

  /// État de chaque famille d'entrée: disponible, valide, fraîche, utilisable.
  /// Vide quand le backend est plus ancien que ce champ.
  final Map<String, FamilyState> families;

  /// Ce que la page dans son ensemble a le droit d'affirmer.
  /// LIVE / RECENT / DEGRADED / STALE / SUSPENDED / UNAVAILABLE.
  final String overallStatus;
  final String overallStatusReason;

  /// Faux dès qu'une entrée critique n'est plus utilisable.
  final bool allowsAction;

  /// Pression achat / vente, décomposée par source.
  final MarketPressure pressure;

  /// Score de -100 à +100 du moteur de timing. Null quand il n'a pas pu
  /// s'exécuter — ce qui était le cas tant que l'endpoint ne l'appelait pas.
  final double? timingScore;
  final String timingSummary;

  /// Échéances macro programmées, du calendrier maintenu côté backend.
  final List<MacroEvent> upcomingMacro;

  /// La décision d'opportunité, calculée par le backend.
  final BuyOpportunity opportunity;

  const TodayRead({
    required this.asset,
    required this.marketData,
    required this.summary,
    required this.directionSource,
    required this.edgeState,
    required this.admittedCount,
    required this.rejectedCount,
    required this.edgeStatement,
    required this.uncertaintyLevel,
    required this.uncertaintyScore,
    required this.uncertaintyDrivers,
    required this.crowdingLevel,
    required this.crowdingScore,
    required this.crowdingDirection,
    required this.leverageState,
    required this.fundingBand,
    required this.fundingPercentile,
    required this.volatilityRegime,
    this.families = const {},
    this.overallStatus = 'UNAVAILABLE',
    this.overallStatusReason = '',
    this.allowsAction = false,
    this.pressure = MarketPressure.unavailable,
    this.timingScore,
    this.timingSummary = '',
    this.upcomingMacro = const [],
    this.opportunity = BuyOpportunity.unavailable,
  });

  factory TodayRead.fromJson(Map<String, dynamic> json) {
    final edge = json['edge'] as Map<String, dynamic>? ?? const {};
    final uncertainty =
        json['uncertainty'] as Map<String, dynamic>? ?? const {};
    final crowding = json['crowding'] as Map<String, dynamic>? ?? const {};
    final leverage =
        json['leverage_state'] as Map<String, dynamic>? ?? const {};
    final funding = json['funding'] as Map<String, dynamic>? ?? const {};
    final volatility = json['volatility'] as Map<String, dynamic>? ?? const {};

    return TodayRead(
      families: ((json['families'] as Map?) ?? const {}).map(
        (key, value) => MapEntry(
          '$key',
          FamilyState.fromJson((value as Map).cast<String, dynamic>()),
        ),
      ),
      overallStatus: json['overall_status'] as String? ?? 'UNAVAILABLE',
      overallStatusReason: json['overall_status_reason'] as String? ?? '',
      allowsAction: json['allows_action'] as bool? ?? false,
      pressure: MarketPressure.fromJson(
        ((json['market_pressure'] as Map?) ?? const {}).cast<String, dynamic>(),
      ),
      timingScore: ((json['entry_timing'] as Map?)?['timing_score'] as num?)
          ?.toDouble(),
      timingSummary:
          (json['entry_timing'] as Map?)?['summary'] as String? ?? '',
      opportunity: BuyOpportunity.fromJson(
        ((json['buy_opportunity_explanation'] as Map?) ?? const {})
            .cast<String, dynamic>(),
      ),
      upcomingMacro: ((json['upcoming_macro'] as List?) ?? const [])
          .map((item) => MacroEvent.fromJson((item as Map).cast<String, dynamic>()))
          .toList(),
      asset: json['asset'] as String? ?? '',
      marketData: json['market_data'] == null
          ? null
          : MarketPriceRead.fromJson(
              json['market_data'] as Map<String, dynamic>,
            ),
      summary: DecisionSummary.fromJson(
        json['decision_summary'] as Map<String, dynamic>? ?? const {},
      ),
      directionSource: json['direction_source'] as String? ?? '',
      edgeState: EdgeState.parse(edge['state'] as String?),
      admittedCount: (edge['admitted_count'] as num?)?.toInt() ?? 0,
      rejectedCount: (edge['rejected_count'] as num?)?.toInt() ?? 0,
      edgeStatement: edge['statement'] as String? ?? '',
      uncertaintyLevel: uncertainty['level'] as String? ?? 'UNKNOWN',
      uncertaintyScore: (uncertainty['score'] as num?)?.toDouble() ?? 100,
      uncertaintyDrivers: ((uncertainty['drivers'] as List?) ?? const [])
          .map((e) => UncertaintyDriver.fromJson(e as Map<String, dynamic>))
          .toList(),
      crowdingLevel: crowding['level'] as String? ?? 'UNKNOWN',
      crowdingScore: (crowding['score'] as num?)?.toDouble(),
      crowdingDirection: crowding['direction'] as String? ?? 'UNKNOWN',
      leverageState: leverage['state'] as String? ?? 'UNDETERMINED',
      fundingBand: funding['band'] as String? ?? 'UNKNOWN',
      fundingPercentile: (funding['percentile'] as num?)?.toDouble(),
      volatilityRegime: volatility['regime'] as String? ?? 'UNKNOWN',
    );
  }
}

class ZoneQuality {
  final int touches;
  final double? dispersionAtr;
  final double? medianReactionAtr;
  final int closePenetrations;
  final double score;

  const ZoneQuality({
    required this.touches,
    required this.dispersionAtr,
    required this.medianReactionAtr,
    required this.closePenetrations,
    required this.score,
  });

  factory ZoneQuality.fromJson(Map<String, dynamic> json) => ZoneQuality(
        touches: (json['touches'] as num?)?.toInt() ?? 0,
        dispersionAtr: (json['dispersion_atr'] as num?)?.toDouble(),
        medianReactionAtr: (json['median_reaction_atr'] as num?)?.toDouble(),
        closePenetrations: (json['close_penetrations'] as num?)?.toInt() ?? 0,
        score: (json['score'] as num?)?.toDouble() ?? 0,
      );
}

class Zone {
  final double low;
  final double high;
  final String kind;
  final ZoneQuality quality;

  const Zone({
    required this.low,
    required this.high,
    required this.kind,
    required this.quality,
  });

  factory Zone.fromJson(Map<String, dynamic> json) => Zone(
        low: (json['low'] as num?)?.toDouble() ?? 0,
        high: (json['high'] as num?)?.toDouble() ?? 0,
        kind: json['kind'] as String? ?? '',
        quality: ZoneQuality.fromJson(
          json['quality'] as Map<String, dynamic>? ?? const {},
        ),
      );
}

class DetectedRange {
  final String rangeType;
  final bool valid;
  final String reason;
  final Zone? topZone;
  final Zone? bottomZone;
  final int durationBars;
  final double? widthAtr;
  final int topTouches;
  final int bottomTouches;
  final double confidence;

  const DetectedRange({
    required this.rangeType,
    required this.valid,
    required this.reason,
    required this.topZone,
    required this.bottomZone,
    required this.durationBars,
    required this.widthAtr,
    required this.topTouches,
    required this.bottomTouches,
    required this.confidence,
  });

  factory DetectedRange.fromJson(Map<String, dynamic> json) => DetectedRange(
        rangeType: json['range_type'] as String? ?? 'NO_VALID_RANGE',
        valid: json['valid'] as bool? ?? false,
        reason: json['reason'] as String? ?? '',
        topZone: json['top_zone'] == null
            ? null
            : Zone.fromJson(json['top_zone'] as Map<String, dynamic>),
        bottomZone: json['bottom_zone'] == null
            ? null
            : Zone.fromJson(json['bottom_zone'] as Map<String, dynamic>),
        durationBars: (json['duration_bars'] as num?)?.toInt() ?? 0,
        widthAtr: (json['width_atr'] as num?)?.toDouble(),
        topTouches: (json['top_touches'] as num?)?.toInt() ?? 0,
        bottomTouches: (json['bottom_touches'] as num?)?.toInt() ?? 0,
        confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
      );
}

class StructuralLocation {
  final String state;
  final double? price;
  final double? relativePosition;
  final double? distanceToTopAtr;
  final double? distanceToBottomAtr;
  final String rangeSummary;
  final String invalidation;
  final List<String> explanation;
  final DetectedRange? range;

  const StructuralLocation({
    required this.state,
    required this.price,
    required this.relativePosition,
    required this.distanceToTopAtr,
    required this.distanceToBottomAtr,
    required this.rangeSummary,
    required this.invalidation,
    required this.explanation,
    required this.range,
  });

  factory StructuralLocation.fromJson(Map<String, dynamic> json) =>
      StructuralLocation(
        state: json['state'] as String? ?? 'NO_VALID_RANGE',
        price: (json['price'] as num?)?.toDouble(),
        relativePosition: (json['relative_position'] as num?)?.toDouble(),
        distanceToTopAtr: (json['distance_to_top_atr'] as num?)?.toDouble(),
        distanceToBottomAtr:
            (json['distance_to_bottom_atr'] as num?)?.toDouble(),
        rangeSummary: json['range_summary'] as String? ?? '',
        invalidation: json['invalidation'] as String? ?? '',
        explanation: (json['explanation'] as List?)?.cast<String>() ?? const [],
        range: json['range'] == null
            ? null
            : DetectedRange.fromJson(json['range'] as Map<String, dynamic>),
      );
}

class StructureEvent {
  final String kind;
  final String direction;
  final double level;
  final String confirmationTime;

  const StructureEvent({
    required this.kind,
    required this.direction,
    required this.level,
    required this.confirmationTime,
  });

  factory StructureEvent.fromJson(Map<String, dynamic> json) => StructureEvent(
        kind: json['kind'] as String? ?? '',
        direction: json['direction'] as String? ?? '',
        level: (json['level'] as num?)?.toDouble() ?? 0,
        confirmationTime: json['confirmation_time'] as String? ?? '',
      );
}

class MarketStructure {
  final String state;
  final List<String> labels;
  final double? lastConfirmedHh;
  final double? lastConfirmedHl;
  final double? lastConfirmedLh;
  final double? lastConfirmedLl;
  final List<StructureEvent> events;
  final String interpretation;
  final String caveat;

  const MarketStructure({
    required this.state,
    required this.labels,
    required this.lastConfirmedHh,
    required this.lastConfirmedHl,
    required this.lastConfirmedLh,
    required this.lastConfirmedLl,
    required this.events,
    required this.interpretation,
    required this.caveat,
  });

  factory MarketStructure.fromJson(Map<String, dynamic> json) =>
      MarketStructure(
        state: json['state'] as String? ?? 'UNCLEAR',
        labels: (json['labels'] as List?)?.cast<String>() ?? const [],
        lastConfirmedHh: (json['last_confirmed_hh'] as num?)?.toDouble(),
        lastConfirmedHl: (json['last_confirmed_hl'] as num?)?.toDouble(),
        lastConfirmedLh: (json['last_confirmed_lh'] as num?)?.toDouble(),
        lastConfirmedLl: (json['last_confirmed_ll'] as num?)?.toDouble(),
        events: ((json['events'] as List?) ?? const [])
            .map((e) => StructureEvent.fromJson(e as Map<String, dynamic>))
            .toList(),
        interpretation: json['interpretation'] as String? ?? '',
        caveat: json['caveat'] as String? ?? '',
      );
}

/// A detected pattern. `recognitionConfidence` describes the SHAPE match;
/// `edgeState` describes whether it predicts anything. They are independent
/// and the UI renders them together, always.
class DetectedPattern {
  final String name;
  final String patternClass;
  final String state;
  final double recognitionConfidence;
  final String directionIfTextbook;
  final Map<String, double> keyLevels;
  final String invalidationRule;
  final EdgeState edgeState;
  final String notes;
  final String separationNote;

  const DetectedPattern({
    required this.name,
    required this.patternClass,
    required this.state,
    required this.recognitionConfidence,
    required this.directionIfTextbook,
    required this.keyLevels,
    required this.invalidationRule,
    required this.edgeState,
    required this.notes,
    required this.separationNote,
  });

  factory DetectedPattern.fromJson(Map<String, dynamic> json) =>
      DetectedPattern(
        name: json['name'] as String? ?? '',
        patternClass: json['pattern_class'] as String? ?? '',
        state: json['state'] as String? ?? '',
        recognitionConfidence:
            (json['recognition_confidence'] as num?)?.toDouble() ?? 0,
        directionIfTextbook:
            json['direction_if_textbook'] as String? ?? 'NEUTRAL',
        keyLevels: ((json['key_levels'] as Map?) ?? const {}).map(
          (key, value) => MapEntry('$key', (value as num?)?.toDouble() ?? 0),
        ),
        invalidationRule: json['invalidation_rule'] as String? ?? '',
        edgeState: EdgeState.parse(json['edge_state'] as String?),
        notes: json['notes'] as String? ?? '',
        separationNote: json['separation_note'] as String? ?? '',
      );

  /// How much to trust the DETECTION (not the prediction).
  String get classHint => switch (patternClass) {
        'DETERMINISTIC' => 'geometry fully specified',
        'HEURISTIC' => 'specified, but thresholds are choices',
        'HUMAN_LIKE' => 'approximates what an analyst draws',
        'EXPERIMENTAL' => 'definition still too subjective to trust',
        _ => '',
      };
}

class StructureRead {
  final String asset;
  final String timeframe;
  final StructuralLocation location;
  final MarketStructure marketStructure;
  final List<DetectedPattern> patterns;
  final String separationNote;

  const StructureRead({
    required this.asset,
    required this.timeframe,
    required this.location,
    required this.marketStructure,
    required this.patterns,
    required this.separationNote,
  });

  factory StructureRead.fromJson(Map<String, dynamic> json) => StructureRead(
        asset: json['asset'] as String? ?? '',
        timeframe: json['timeframe'] as String? ?? '',
        location: StructuralLocation.fromJson(
          json['location'] as Map<String, dynamic>? ?? const {},
        ),
        marketStructure: MarketStructure.fromJson(
          json['market_structure'] as Map<String, dynamic>? ?? const {},
        ),
        patterns: ((json['patterns'] as List?) ?? const [])
            .map((e) => DetectedPattern.fromJson(e as Map<String, dynamic>))
            .toList(),
        separationNote: json['separation_note'] as String? ?? '',
      );
}

class EntryOpportunity {
  final String state;
  final double? score;
  final List<String> whyNow;
  final String invalidation;
  final EdgeState measuredEdge;
  final String statement;
  final String disclaimer;
  final List<String> missing;

  const EntryOpportunity({
    required this.state,
    required this.score,
    required this.whyNow,
    required this.invalidation,
    required this.measuredEdge,
    required this.statement,
    required this.disclaimer,
    required this.missing,
  });

  factory EntryOpportunity.fromJson(Map<String, dynamic> json) =>
      EntryOpportunity(
        state: json['state'] as String? ?? 'INSUFFICIENT_DATA',
        score: (json['score'] as num?)?.toDouble(),
        whyNow: (json['why_now'] as List?)?.cast<String>() ?? const [],
        invalidation: json['invalidation'] as String? ?? '',
        measuredEdge: EdgeState.parse(json['measured_edge_state'] as String?),
        statement: json['statement'] as String? ?? '',
        disclaimer: json['disclaimer'] as String? ?? '',
        missing: (json['missing'] as List?)?.cast<String>() ?? const [],
      );
}

class CandlePoint {
  final DateTime? time;
  final double open;
  final double high;
  final double low;
  final double close;
  final double volume;

  const CandlePoint({
    required this.time,
    required this.open,
    required this.high,
    required this.low,
    required this.close,
    required this.volume,
  });

  factory CandlePoint.fromJson(Map<String, dynamic> json) => CandlePoint(
        time: DateTime.tryParse('${json['time'] ?? ''}'),
        open: (json['open'] as num?)?.toDouble() ?? 0,
        high: (json['high'] as num?)?.toDouble() ?? 0,
        low: (json['low'] as num?)?.toDouble() ?? 0,
        close: (json['close'] as num?)?.toDouble() ?? 0,
        volume: (json['volume'] as num?)?.toDouble() ?? 0,
      );
}

class ChartRead {
  final String asset;
  final String timeframe;
  final String period;
  final bool available;
  final String reason;
  final List<CandlePoint> candles;
  final Map<String, List<double?>> overlays;
  final Map<String, List<double?>> panels;
  final Map<String, dynamic> levels;
  final List<Map<String, dynamic>> patterns;
  final Map<String, dynamic> summary;

  const ChartRead({
    required this.asset,
    required this.timeframe,
    required this.period,
    required this.available,
    required this.reason,
    required this.candles,
    required this.overlays,
    required this.panels,
    required this.levels,
    required this.patterns,
    required this.summary,
  });

  factory ChartRead.fromJson(Map<String, dynamic> json) => ChartRead(
        asset: json['asset'] as String? ?? '',
        timeframe: json['timeframe'] as String? ?? '',
        period: json['period'] as String? ?? '',
        available: json['available'] as bool? ?? false,
        reason: json['reason'] as String? ?? '',
        candles: ((json['candles'] as List?) ?? const [])
            .map((item) => CandlePoint.fromJson(
                  (item as Map).cast<String, dynamic>(),
                ))
            .where((candle) =>
                candle.high > 0 && candle.low > 0 && candle.close > 0)
            .toList(),
        overlays: _seriesMap(json['overlays'] as Map?),
        panels: _seriesMap(json['panels'] as Map?),
        levels: (json['levels'] as Map?)?.cast<String, dynamic>() ?? const {},
        patterns: ((json['patterns'] as List?) ?? const [])
            .map((item) => (item as Map).cast<String, dynamic>())
            .toList(),
        summary: (json['summary'] as Map?)?.cast<String, dynamic>() ?? const {},
      );

  double? get lastPrice {
    final value = summary['last_price'];
    if (value is num) return value.toDouble();
    if (candles.isNotEmpty) return candles.last.close;
    return null;
  }

  double? get changePct {
    final value = summary['change_pct'];
    if (value is num) return value.toDouble();
    if (candles.length < 2) return null;
    final first = candles.first.close;
    if (first == 0) return null;
    return (candles.last.close - first) / first * 100;
  }

  int get bars {
    final value = summary['bars'];
    if (value is num) return value.toInt();
    return candles.length;
  }

  static Map<String, List<double?>> _seriesMap(Map? raw) {
    if (raw == null) return const {};
    return raw.cast<String, dynamic>().map((key, value) {
      final points = ((value as List?) ?? const [])
          .map<double?>((point) => point is num ? point.toDouble() : null)
          .toList();
      return MapEntry(key, points);
    });
  }
}

// --- LOT 6A models --------------------------------------------------------

/// Implied volatility and the variance risk premium.
///
/// The only family sourced from a market other than spot or perpetuals. SOL
/// has no Deribit index and is reported unavailable rather than approximated.
class ImpliedVolatilityRead {
  final String asset;
  final bool available;
  final String unavailableReason;
  final double? dvol;
  final double? dvolPercentile;
  final double? dvolChange30d;
  final double? realisedVolAnnualised;
  final double? variancePremium;
  final double? premiumPercentile;
  final String pricing;
  final String compression;
  final int historyDays;
  final String interpretation;
  final String edgeNote;

  const ImpliedVolatilityRead({
    required this.asset,
    required this.available,
    required this.unavailableReason,
    required this.dvol,
    required this.dvolPercentile,
    required this.dvolChange30d,
    required this.realisedVolAnnualised,
    required this.variancePremium,
    required this.premiumPercentile,
    required this.pricing,
    required this.compression,
    required this.historyDays,
    required this.interpretation,
    required this.edgeNote,
  });

  factory ImpliedVolatilityRead.fromJson(Map<String, dynamic> json) =>
      ImpliedVolatilityRead(
        asset: json['asset'] as String? ?? '',
        available: json['available'] as bool? ?? false,
        unavailableReason: json['unavailable_reason'] as String? ?? '',
        dvol: (json['dvol'] as num?)?.toDouble(),
        dvolPercentile: (json['dvol_percentile'] as num?)?.toDouble(),
        dvolChange30d: (json['dvol_change_30d'] as num?)?.toDouble(),
        realisedVolAnnualised:
            (json['realised_vol_annualised'] as num?)?.toDouble(),
        variancePremium: (json['variance_premium'] as num?)?.toDouble(),
        premiumPercentile: (json['premium_percentile'] as num?)?.toDouble(),
        pricing: json['pricing'] as String? ?? 'UNKNOWN',
        compression: json['compression'] as String? ?? 'UNKNOWN',
        historyDays: (json['history_days'] as num?)?.toInt() ?? 0,
        interpretation: json['interpretation'] as String? ?? '',
        edgeNote: json['edge_note'] as String? ?? '',
      );

  /// French label for the pricing state.
  String get pricingLabel => switch (pricing) {
        'EXPENSIVE' => 'chères',
        'SLIGHTLY_EXPENSIVE' => 'un peu chères',
        'FAIR' => 'au juste prix',
        'SLIGHTLY_CHEAP' => 'un peu bon marché',
        'CHEAP' => 'bon marché',
        _ => 'inconnu',
      };
}

class TimeframeReading {
  final String timeframe;
  final bool available;
  final int bars;
  final String structure;
  final String location;
  final double? relativePosition;
  final double? rangeTop;
  final double? rangeBottom;
  final String reasonUnavailable;

  const TimeframeReading({
    required this.timeframe,
    required this.available,
    required this.bars,
    required this.structure,
    required this.location,
    required this.relativePosition,
    required this.rangeTop,
    required this.rangeBottom,
    required this.reasonUnavailable,
  });

  factory TimeframeReading.fromJson(Map<String, dynamic> json) =>
      TimeframeReading(
        timeframe: json['timeframe'] as String? ?? '',
        available: json['available'] as bool? ?? false,
        bars: (json['bars'] as num?)?.toInt() ?? 0,
        structure: json['structure'] as String? ?? 'UNCLEAR',
        location: json['location'] as String? ?? 'NO_VALID_RANGE',
        relativePosition: (json['relative_position'] as num?)?.toDouble(),
        rangeTop: (json['range_top'] as num?)?.toDouble(),
        rangeBottom: (json['range_bottom'] as num?)?.toDouble(),
        reasonUnavailable: json['reason_unavailable'] as String? ?? '',
      );

  String get structureLabel => switch (structure) {
        'BULLISH_STRUCTURE' => 'haussière',
        'BEARISH_STRUCTURE' => 'baissière',
        'RANGE_STRUCTURE' => 'range',
        'TRANSITION' => 'transition',
        _ => 'indéterminée',
      };
}

/// One reading per timeframe plus what they say together.
///
/// A conflict between timeframes is the normal state of a market, not an
/// error. It is named rather than averaged away.
class MultiTimeframeRead {
  final String asset;
  final List<TimeframeReading> timeframes;
  final String alignment;
  final String dominantDirection;
  final List<String> conflicts;
  final String narrative;
  final String caveat;

  const MultiTimeframeRead({
    required this.asset,
    required this.timeframes,
    required this.alignment,
    required this.dominantDirection,
    required this.conflicts,
    required this.narrative,
    required this.caveat,
  });

  factory MultiTimeframeRead.fromJson(Map<String, dynamic> json) =>
      MultiTimeframeRead(
        asset: json['asset'] as String? ?? '',
        timeframes: ((json['timeframes'] as List?) ?? const [])
            .map((e) => TimeframeReading.fromJson(e as Map<String, dynamic>))
            .toList(),
        alignment: json['alignment'] as String? ?? 'INSUFFICIENT_DATA',
        dominantDirection:
            json['dominant_direction'] as String? ?? 'UNDETERMINED',
        conflicts: (json['conflicts'] as List?)?.cast<String>() ?? const [],
        narrative: json['narrative'] as String? ?? '',
        caveat: json['caveat'] as String? ?? '',
      );

  String get alignmentLabel => switch (alignment) {
        'HIGHER_TIMEFRAME_ALIGNMENT' => 'unités alignées',
        'CONFLICT' => 'unités en conflit',
        'TRANSITION' => 'transition',
        _ => 'données insuffisantes',
      };
}

/// A section of the daily report. An unavailable section carries its reason.
class ReportSection {
  final String title;
  final List<String> lines;
  final bool available;
  final String reason;

  const ReportSection({
    required this.title,
    required this.lines,
    required this.available,
    required this.reason,
  });

  factory ReportSection.fromJson(Map<String, dynamic> json) => ReportSection(
        title: json['title'] as String? ?? '',
        lines: (json['lines'] as List?)?.cast<String>() ?? const [],
        available: json['available'] as bool? ?? true,
        reason: json['reason'] as String? ?? '',
      );
}

class DailyReport {
  final String asset;
  final String generatedAt;
  final List<ReportSection> sections;
  final List<String> conclusion;

  const DailyReport({
    required this.asset,
    required this.generatedAt,
    required this.sections,
    required this.conclusion,
  });

  factory DailyReport.fromJson(Map<String, dynamic> json) => DailyReport(
        asset: json['asset'] as String? ?? '',
        generatedAt: json['generated_at'] as String? ?? '',
        sections: ((json['sections'] as List?) ?? const [])
            .map((e) => ReportSection.fromJson(e as Map<String, dynamic>))
            .toList(),
        conclusion: (json['conclusion'] as List?)?.cast<String>() ?? const [],
      );
}
