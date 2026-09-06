/// Data models mirroring the backend payloads.
///
/// Every model that carries a recognition confidence also carries an edge
/// state, because the UI must never be able to render the first without the
/// second. That separation is the whole point of the system: a pattern can be
/// recognised perfectly and still predict nothing.
library;

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
        EdgeState.positiveEdge => 'Measured edge',
        EdgeState.negativeEdge => 'Edge runs against the signal',
        EdgeState.noMeasurableEdge => 'No measurable edge',
        EdgeState.unstable => 'Unstable',
        EdgeState.insufficientData => 'Insufficient data',
        EdgeState.notYetTested => 'Not yet tested',
        EdgeState.unknown => 'Unknown',
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

  factory DecisionSummary.fromJson(Map<String, dynamic> json) => DecisionSummary(
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

  factory UncertaintyDriver.fromJson(Map<String, dynamic> json) => UncertaintyDriver(
        driver: json['driver'] as String? ?? '',
        contribution: json['contribution'] as num? ?? 0,
        detail: json['detail'] as String? ?? '',
      );
}

class TodayRead {
  final String asset;
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

  const TodayRead({
    required this.asset,
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
  });

  factory TodayRead.fromJson(Map<String, dynamic> json) {
    final edge = json['edge'] as Map<String, dynamic>? ?? const {};
    final uncertainty = json['uncertainty'] as Map<String, dynamic>? ?? const {};
    final crowding = json['crowding'] as Map<String, dynamic>? ?? const {};
    final leverage = json['leverage_state'] as Map<String, dynamic>? ?? const {};
    final funding = json['funding'] as Map<String, dynamic>? ?? const {};
    final volatility = json['volatility'] as Map<String, dynamic>? ?? const {};

    return TodayRead(
      asset: json['asset'] as String? ?? '',
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

  factory StructuralLocation.fromJson(Map<String, dynamic> json) => StructuralLocation(
        state: json['state'] as String? ?? 'NO_VALID_RANGE',
        price: (json['price'] as num?)?.toDouble(),
        relativePosition: (json['relative_position'] as num?)?.toDouble(),
        distanceToTopAtr: (json['distance_to_top_atr'] as num?)?.toDouble(),
        distanceToBottomAtr: (json['distance_to_bottom_atr'] as num?)?.toDouble(),
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

  factory MarketStructure.fromJson(Map<String, dynamic> json) => MarketStructure(
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

  factory DetectedPattern.fromJson(Map<String, dynamic> json) => DetectedPattern(
        name: json['name'] as String? ?? '',
        patternClass: json['pattern_class'] as String? ?? '',
        state: json['state'] as String? ?? '',
        recognitionConfidence:
            (json['recognition_confidence'] as num?)?.toDouble() ?? 0,
        directionIfTextbook: json['direction_if_textbook'] as String? ?? 'NEUTRAL',
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

  factory EntryOpportunity.fromJson(Map<String, dynamic> json) => EntryOpportunity(
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
