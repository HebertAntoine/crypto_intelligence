/// Typed models for the future-first decision endpoints.
library;

double? _number(dynamic value) => value is num ? value.toDouble() : null;

class FutureSourceRead {
  final String source;
  final String? url;

  const FutureSourceRead({required this.source, this.url});

  factory FutureSourceRead.fromJson(Map<String, dynamic> json) =>
      FutureSourceRead(
        source: json['source']?.toString() ?? 'Source indisponible',
        url: json['url']?.toString(),
      );
}

class FutureReasonRead {
  final String title;
  final String explanation;
  final String? dateTime;
  final String? impact;
  final String? source;
  final String? sourceUrl;

  const FutureReasonRead({
    required this.title,
    required this.explanation,
    this.dateTime,
    this.impact,
    this.source,
    this.sourceUrl,
  });

  factory FutureReasonRead.fromJson(Map<String, dynamic> json) =>
      FutureReasonRead(
        title: json['title']?.toString() ?? 'Raison',
        explanation: json['explanation']?.toString() ?? '',
        dateTime: json['date_time']?.toString(),
        impact: json['impact']?.toString(),
        source: json['source']?.toString(),
        sourceUrl: json['source_url']?.toString(),
      );
}

class FutureCounterSignalRead {
  final String family;
  final String direction;
  final String explanation;

  const FutureCounterSignalRead({
    required this.family,
    required this.direction,
    required this.explanation,
  });

  factory FutureCounterSignalRead.fromJson(Map<String, dynamic> json) =>
      FutureCounterSignalRead(
        family: json['family']?.toString() ?? '',
        direction: json['directional_bias']?.toString() ?? 'NEUTRAL',
        explanation: json['explanation']?.toString() ?? '',
      );
}

class FutureFamilyRead {
  final String id;
  final String label;
  final bool available;
  final String? direction;
  final String? movement;
  final String summary;
  final String freshness;
  final String? unavailableReason;

  /// How well the engine could measure this family, in [0, 1]. It weighs on the
  /// ranking: a barely-measured reading must not outrank a material event.
  final double confidence;

  const FutureFamilyRead({
    required this.id,
    required this.label,
    required this.available,
    required this.summary,
    required this.freshness,
    this.direction,
    this.movement,
    this.unavailableReason,
    this.confidence = 0,
  });

  factory FutureFamilyRead.fromJson(Map<String, dynamic> json) =>
      FutureFamilyRead(
        id: json['family']?.toString() ?? '',
        label: json['label']?.toString() ?? '',
        available: json['available'] == true,
        direction: json['directional_bias']?.toString(),
        movement: json['expected_movement']?.toString(),
        summary: json['summary']?.toString() ?? '',
        freshness: json['freshness']?.toString() ?? 'UNAVAILABLE',
        unavailableReason: json['unavailable_reason']?.toString(),
        confidence: _number(json['confidence']) ?? 0,
      );
}

/// Normalised semantics for one factor.
///
/// Direction, impact, trend and confidence are four separate readings. The
/// screen must never infer one from another, and UNKNOWN is not NEUTRAL: an
/// event that has not happened is unknown, a measured balance is neutral.
class FutureFactorRead {
  final String key;
  final String label;
  final String direction;
  final String impact;
  final String trend;
  final double confidence;
  final String freshness;
  final String rationale;

  /// "NONE" when the instrument cannot speak about direction at all, as for
  /// Bollinger compression. It bounds what the reading may be used for.
  final String impactOnDirection;

  /// Raw data → observation → mechanism, written by the engine. The UI renders
  /// it; it never composes an interpretation of its own.
  final List<String> causalChain;
  final List<String> missingRequirements;
  final String provider;
  final String? sourceUrl;
  final String availability;

  const FutureFactorRead({
    required this.key,
    required this.label,
    required this.direction,
    required this.impact,
    required this.trend,
    required this.confidence,
    required this.freshness,
    required this.rationale,
    required this.impactOnDirection,
    this.causalChain = const [],
    this.missingRequirements = const [],
    this.provider = '',
    this.sourceUrl,
    this.availability = 'AVAILABLE',
  });

  factory FutureFactorRead.fromJson(Map<String, dynamic> json) => FutureFactorRead(
        key: json['key']?.toString() ?? '',
        label: json['label']?.toString() ?? '',
        direction: json['direction']?.toString() ?? 'UNKNOWN',
        impact: json['impact']?.toString() ?? 'MODERATE',
        trend: json['trend']?.toString() ?? 'UNKNOWN',
        confidence: _number(json['confidence']) ?? 0,
        freshness: json['freshness']?.toString() ?? 'UNAVAILABLE',
        rationale: json['rationale']?.toString() ?? '',
        impactOnDirection: json['impact_on_direction']?.toString() ?? 'MEASURED',
        causalChain: (json['causal_chain'] as List? ?? const [])
            .map((value) => value.toString())
            .toList(),
        missingRequirements: (json['missing_requirements'] as List? ?? const [])
            .map((value) => value.toString())
            .toList(),
        provider: json['provider']?.toString() ?? '',
        sourceUrl: json['source_url']?.toString(),
        availability: json['availability']?.toString() ?? 'AVAILABLE',
      );
}

/// The chief synthesis: a state, the evidence for it, and the evidence against.
///
/// The counter-evidence is never omitted. A reading that only collects agreeing
/// facts is how a screen talks a reader into a conclusion.
class FutureSynthesisRead {
  final String state;
  final String stateLabel;
  final String headline;
  final String summary;
  final List<FutureEvidenceRead> whyNow;
  final List<FutureEvidenceRead> counterEvidence;
  final List<FutureConditionRead> confirmationConditions;
  final String confirmationMet;
  final List<FutureConditionRead> invalidationConditions;
  final FutureScenarioBriefRead? mainScenario;
  final FutureScenarioBriefRead? alternativeScenario;
  final List<FutureCatalystRead> upcomingEvents;
  final String uncertainty;
  final List<String> missingFamilies;
  final String dataStatus;

  const FutureSynthesisRead({
    required this.state,
    required this.stateLabel,
    required this.headline,
    required this.summary,
    required this.whyNow,
    required this.counterEvidence,
    required this.confirmationConditions,
    required this.confirmationMet,
    required this.invalidationConditions,
    required this.upcomingEvents,
    required this.uncertainty,
    required this.missingFamilies,
    required this.dataStatus,
    this.mainScenario,
    this.alternativeScenario,
  });

  static List<T> _list<T>(dynamic raw, T Function(Map<String, dynamic>) build) =>
      (raw as List? ?? const [])
          .whereType<Map>()
          .map((value) => build(Map<String, dynamic>.from(value)))
          .toList();

  factory FutureSynthesisRead.fromJson(Map<String, dynamic> json) =>
      FutureSynthesisRead(
        state: json['state']?.toString() ?? 'INSUFFICIENT_DATA',
        stateLabel: json['state_label']?.toString() ?? '',
        headline: json['headline']?.toString() ?? '',
        summary: json['summary']?.toString() ?? '',
        whyNow: _list(json['why_now'], FutureEvidenceRead.fromJson),
        counterEvidence:
            _list(json['counter_evidence'], FutureEvidenceRead.fromJson),
        confirmationConditions:
            _list(json['confirmation_conditions'], FutureConditionRead.fromJson),
        confirmationMet: json['confirmation_met']?.toString() ?? '',
        invalidationConditions:
            _list(json['invalidation_conditions'], FutureConditionRead.fromJson),
        mainScenario: json['main_scenario'] is Map
            ? FutureScenarioBriefRead.fromJson(
                Map<String, dynamic>.from(json['main_scenario'] as Map))
            : null,
        alternativeScenario: json['alternative_scenario'] is Map
            ? FutureScenarioBriefRead.fromJson(
                Map<String, dynamic>.from(json['alternative_scenario'] as Map))
            : null,
        upcomingEvents:
            _list(json['upcoming_events'], FutureCatalystRead.fromJson),
        uncertainty: json['uncertainty']?.toString() ?? 'MEDIUM',
        missingFamilies: (json['missing_families'] as List? ?? const [])
            .map((value) => value.toString())
            .toList(),
        dataStatus: json['data_status']?.toString() ?? 'AVAILABLE',
      );
}

class FutureEvidenceRead {
  final String label;
  final String direction;
  final String impact;
  final String observation;
  final String whyItMatters;
  final String source;
  final String freshness;

  const FutureEvidenceRead({
    required this.label,
    required this.direction,
    required this.impact,
    required this.observation,
    required this.whyItMatters,
    required this.source,
    required this.freshness,
  });

  factory FutureEvidenceRead.fromJson(Map<String, dynamic> json) =>
      FutureEvidenceRead(
        label: json['label']?.toString() ?? '',
        direction: json['direction']?.toString() ?? 'UNKNOWN',
        impact: json['impact']?.toString() ?? 'MODERATE',
        observation: json['observation']?.toString() ?? '',
        whyItMatters: json['why_it_matters']?.toString() ?? '',
        source: json['source']?.toString() ?? '',
        freshness: json['freshness']?.toString() ?? '',
      );
}

class FutureConditionRead {
  final String text;
  final bool met;
  final int weight;
  final String evidence;

  const FutureConditionRead({
    required this.text,
    required this.met,
    required this.weight,
    required this.evidence,
  });

  factory FutureConditionRead.fromJson(Map<String, dynamic> json) =>
      FutureConditionRead(
        text: json['text']?.toString() ?? '',
        met: json['met'] == true,
        weight: (_number(json['weight']) ?? 1).round(),
        evidence: json['evidence']?.toString() ?? '',
      );
}

class FutureScenarioBriefRead {
  final String name;
  final String description;
  final String likelihood;

  const FutureScenarioBriefRead({
    required this.name,
    required this.description,
    required this.likelihood,
  });

  factory FutureScenarioBriefRead.fromJson(Map<String, dynamic> json) =>
      FutureScenarioBriefRead(
        name: json['name']?.toString() ?? '',
        description: json['description']?.toString() ?? '',
        likelihood: json['likelihood']?.toString() ?? '',
      );
}

class FutureCatalystRead {
  final String title;
  final String assetImpact;
  final int relevanceScore;
  final String importance;
  final String? scheduledAt;
  final String source;

  /// How closely to watch this. Never a direction.
  final String attention;

  /// Stays UNKNOWN until a result exists to compare with what was expected.
  final String direction;

  const FutureCatalystRead({
    required this.title,
    required this.assetImpact,
    required this.relevanceScore,
    required this.importance,
    required this.source,
    this.scheduledAt,
    this.attention = 'LOW',
    this.direction = 'UNKNOWN',
  });

  /// True while nothing can honestly be said about which way this points.
  bool get directionIsUnknown => direction == 'UNKNOWN' || direction.isEmpty;

  factory FutureCatalystRead.fromJson(Map<String, dynamic> json) =>
      FutureCatalystRead(
        title: json['title']?.toString() ?? '',
        assetImpact: json['asset_impact']?.toString() ?? 'MEDIUM',
        relevanceScore: (_number(json['relevance_score']) ?? 0).round(),
        importance: json['importance']?.toString() ?? 'MEDIUM',
        scheduledAt: json['scheduled_at']?.toString(),
        source: json['source']?.toString() ?? '',
        attention: json['attention']?.toString() ?? 'LOW',
        direction: json['direction']?.toString() ?? 'UNKNOWN',
      );
}

class FutureEventRead {
  final String id;

  /// FOMC_DECISION, ECB_RATE_DECISION, CPI... - what kind of date this is.
  final String eventType;
  final String title;
  final DateTime? scheduledAt;
  final int? countdownSeconds;
  final String importance;
  final String status;
  final String direction;
  final String movement;
  final String source;
  final String? sourceUrl;
  final String freshness;

  const FutureEventRead({
    this.eventType = '',
    required this.id,
    required this.title,
    required this.importance,
    required this.status,
    required this.direction,
    required this.movement,
    required this.source,
    required this.freshness,
    this.scheduledAt,
    this.countdownSeconds,
    this.sourceUrl,
  });

  factory FutureEventRead.fromJson(Map<String, dynamic> json) {
    final scheduled = json['scheduled_at']?.toString();
    final countdown = _number(json['countdown_seconds']);
    final hours = _number(json['hours_until']);
    return FutureEventRead(
      id: json['id']?.toString() ?? '',
      eventType: json['event_type']?.toString() ?? '',
      title: json['title']?.toString() ?? '',
      scheduledAt:
          scheduled == null ? null : DateTime.tryParse(scheduled)?.toLocal(),
      countdownSeconds:
          countdown?.round() ?? (hours == null ? null : (hours * 3600).round()),
      importance: json['importance']?.toString() ?? 'MEDIUM',
      status: json['status']?.toString() ?? 'SCHEDULED',
      direction: (json['directional_bias'] ?? json['directional_effect'])
              ?.toString() ??
          'NEUTRAL',
      movement:
          (json['expected_movement'] ?? json['magnitude_effect'])?.toString() ??
              'NORMAL',
      source: json['source']?.toString() ?? 'Source indisponible',
      sourceUrl: json['source_url']?.toString(),
      freshness: (json['freshness'] ?? json['freshness_status'])?.toString() ??
          'UNAVAILABLE',
    );
  }
}

class FutureScenarioRead {
  final String id;
  final double? probability;
  final String? probabilitySource;
  final String direction;
  final String movement;
  final double confidence;
  final List<String> eventChain;

  const FutureScenarioRead({
    required this.id,
    required this.direction,
    required this.movement,
    required this.confidence,
    required this.eventChain,
    this.probability,
    this.probabilitySource,
  });

  factory FutureScenarioRead.fromJson(Map<String, dynamic> json) =>
      FutureScenarioRead(
        id: json['id']?.toString() ?? '',
        probability: _number(json['probability']),
        probabilitySource: json['probability_source']?.toString(),
        direction: json['directional_bias']?.toString() ?? 'NEUTRAL',
        movement: json['expected_movement']?.toString() ?? 'NORMAL',
        confidence: _number(json['confidence']) ?? 0,
        eventChain: (json['event_chain'] as List? ?? const [])
            .map((value) => value.toString())
            .toList(),
      );
}

class FutureDecisionRead {
  final String asset;
  final String analysisId;
  final DateTime? asOf;
  final String horizon;
  final String decision;
  final String direction;
  final String movement;
  final double confidence;
  final String eventRisk;
  final bool eventRiskActive;
  final String coverage;
  final List<FutureReasonRead> reasons;
  final List<FutureCounterSignalRead> counterSignals;
  final List<String> changes;
  final List<FutureFamilyRead> families;
  final List<FutureScenarioRead> scenarios;
  final FutureEventRead? nextEvent;

  /// What the market has priced for the next major event, when a licensed
  /// source actually provided it. Null means no expectation is available, and
  /// the UI must say so rather than imply one.
  final String? marketExpectation;

  /// Normalised factor semantics, published beside the five families.
  final List<FutureFactorRead> factors;

  /// The chief synthesis, when the backend published one.
  final FutureSynthesisRead? synthesis;

  /// What would have to happen to move the decision each way (section 14).
  final List<String> conditionsToBuy;
  final List<String> conditionsToSell;

  /// The consistency check found no relationship that survives the
  /// statistical tests. That, not the signals themselves, is what holds the
  /// verdict at WAIT - and the home has to be able to say so.
  final bool noMeasurableEdge;

  /// What can move the market on this horizon, ranked by the engine, and the
  /// explanation built from that ranking. Null on an older payload.
  final FutureHierarchyRead? hierarchy;

  const FutureDecisionRead({
    required this.asset,
    required this.analysisId,
    required this.horizon,
    required this.decision,
    required this.direction,
    required this.movement,
    required this.confidence,
    required this.eventRisk,
    required this.eventRiskActive,
    required this.coverage,
    required this.reasons,
    required this.counterSignals,
    required this.changes,
    required this.families,
    required this.scenarios,
    this.asOf,
    this.nextEvent,
    this.marketExpectation,
    this.factors = const [],
    this.conditionsToBuy = const [],
    this.conditionsToSell = const [],
    this.synthesis,
    this.noMeasurableEdge = false,
    this.hierarchy,
  });

  /// Build the sentence only from an AVAILABLE, priced expectation.
  static String? _readExpectation(dynamic raw) {
    for (final item in (raw as List? ?? const []).whereType<Map>()) {
      if (item['status']?.toString() != 'AVAILABLE') continue;
      final outcome = item['expected_outcome'];
      final label = outcome is Map ? outcome['outcome']?.toString() : null;
      final probability = outcome is Map ? _number(outcome['probability']) : null;
      if (label == null || label.isEmpty) continue;
      if (probability == null) return label;
      return '$label (${(probability * 100).round()} % implicite)';
    }
    return null;
  }

  factory FutureDecisionRead.fromJson(Map<String, dynamic> json) {
    final familyBlock = json['families'] as Map? ?? const {};
    final familyItems = familyBlock['items'] as Map? ?? const {};
    final eventRisk = json['event_risk'] as Map? ?? const {};
    final next = json['next_major_event'];
    return FutureDecisionRead(
      asset: json['asset']?.toString() ?? '',
      analysisId: json['analysis_id']?.toString() ?? '',
      asOf: DateTime.tryParse(json['as_of']?.toString() ?? '')?.toLocal(),
      horizon: json['horizon']?.toString() ?? '7d',
      decision: json['decision']?.toString() ?? 'INSUFFICIENT_DATA',
      direction: json['directional_bias']?.toString() ?? 'NEUTRAL',
      movement: json['expected_movement']?.toString() ?? 'NORMAL',
      confidence: _number(json['decision_confidence']) ?? 0,
      eventRisk: eventRisk['level']?.toString() ?? 'UNKNOWN',
      eventRiskActive: eventRisk['active'] == true,
      marketExpectation: _readExpectation(json['market_expectations']),
      factors: (familyBlock['factors'] as List? ?? const [])
          .whereType<Map>()
          .map((value) =>
              FutureFactorRead.fromJson(Map<String, dynamic>.from(value)))
          .toList(),
      synthesis: json['synthesis'] is Map
          ? FutureSynthesisRead.fromJson(
              Map<String, dynamic>.from(json['synthesis'] as Map))
          : null,
      conditionsToBuy: (json['conditions_to_buy'] as List? ?? const [])
          .map((value) => value.toString())
          .toList(),
      conditionsToSell: (json['conditions_to_sell'] as List? ?? const [])
          .map((value) => value.toString())
          .toList(),
      hierarchy: json['hierarchy'] is Map
          ? FutureHierarchyRead.fromJson(
              Map<String, dynamic>.from(json['hierarchy'] as Map))
          : null,
      noMeasurableEdge: ((json['consistency'] as Map?)?['issues'] as List? ??
              const [])
          .whereType<Map>()
          .any((issue) => issue['code'] == 'NO_MEASURABLE_EDGE'),
      coverage: familyBlock['coverage']?.toString() ?? '0/5 disponibles',
      reasons: (json['reasons'] as List? ?? const [])
          .whereType<Map>()
          .map((value) =>
              FutureReasonRead.fromJson(Map<String, dynamic>.from(value)))
          .toList(),
      counterSignals: (json['counter_signals'] as List? ?? const [])
          .whereType<Map>()
          .map((value) => FutureCounterSignalRead.fromJson(
              Map<String, dynamic>.from(value)))
          .toList(),
      changes: (json['what_could_change_decision'] as List? ?? const [])
          .map((value) => value.toString())
          .toList(),
      families: familyItems.values
          .whereType<Map>()
          .map((value) =>
              FutureFamilyRead.fromJson(Map<String, dynamic>.from(value)))
          .toList(),
      scenarios: (json['scenarios'] as List? ?? const [])
          .whereType<Map>()
          .map((value) =>
              FutureScenarioRead.fromJson(Map<String, dynamic>.from(value)))
          .toList(),
      nextEvent: next is Map
          ? FutureEventRead.fromJson(Map<String, dynamic>.from(next))
          : null,
    );
  }
}

class FutureTimelineRead {
  final String asset;
  final List<FutureEventRead> events;

  const FutureTimelineRead({required this.asset, required this.events});

  factory FutureTimelineRead.fromJson(Map<String, dynamic> json) =>
      FutureTimelineRead(
        asset: json['asset']?.toString() ?? '',
        events: (json['events'] as List? ?? const [])
            .whereType<Map>()
            .map((value) =>
                FutureEventRead.fromJson(Map<String, dynamic>.from(value)))
            .toList(),
      );
}


/// One ranked driver: an event or a measured factor.
class FutureDriverRead {
  final String id;
  final String kind;
  final String key;
  final int tier;
  final String emoji;
  final String title;
  final String direction;
  final String attention;
  final String role;
  final double countedWeight;
  final String status;

  /// RED | ORANGE | YELLOW | GREEN | WHITE
  final String tone;
  final String what;
  final String why;
  final String? expectation;
  final String invalidation;
  final String? scheduledAt;
  final String source;
  final String? sourceUrl;

  const FutureDriverRead({
    required this.id,
    required this.kind,
    required this.key,
    required this.tier,
    required this.emoji,
    required this.title,
    required this.direction,
    required this.attention,
    required this.role,
    required this.countedWeight,
    required this.status,
    required this.tone,
    required this.what,
    required this.why,
    required this.invalidation,
    this.expectation,
    this.scheduledAt,
    this.source = '',
    this.sourceUrl,
  });

  factory FutureDriverRead.fromJson(Map<String, dynamic> json) =>
      FutureDriverRead(
        id: json['id']?.toString() ?? '',
        kind: json['kind']?.toString() ?? 'FACTOR',
        key: json['key']?.toString() ?? '',
        tier: (_number(json['tier']) ?? 4).round(),
        emoji: json['emoji']?.toString() ?? '📊',
        title: json['title']?.toString() ?? '',
        direction: json['direction']?.toString() ?? 'UNKNOWN',
        attention: json['attention']?.toString() ?? 'NONE',
        role: json['role']?.toString() ?? 'CONTEXT',
        countedWeight: (_number(json['counted_weight']) ?? 0).toDouble(),
        status: json['status']?.toString() ?? '',
        tone: json['tone']?.toString() ?? 'WHITE',
        what: json['what']?.toString() ?? '',
        why: json['why']?.toString() ?? '',
        expectation: json['expectation']?.toString(),
        invalidation: json['invalidation']?.toString() ?? '',
        scheduledAt: json['scheduled_at']?.toString(),
        source: json['source']?.toString() ?? '',
        sourceUrl: json['source_url']?.toString(),
      );
}

class FutureHierarchyRead {
  final String reading;
  final double coverage;
  final String headline;
  final List<String> explanation;
  final FutureDriverRead? primary;
  final List<FutureDriverRead> homeFactors;
  final List<FutureDriverRead> upcomingRisks;
  final List<String> dataGaps;
  final String whaleStatus;
  final String whaleTone;
  final String whaleDetail;
  final bool whalePrincipal;

  const FutureHierarchyRead({
    required this.reading,
    required this.coverage,
    required this.headline,
    required this.explanation,
    required this.homeFactors,
    required this.upcomingRisks,
    required this.dataGaps,
    required this.whaleStatus,
    required this.whaleTone,
    required this.whaleDetail,
    required this.whalePrincipal,
    this.primary,
  });

  factory FutureHierarchyRead.fromJson(Map<String, dynamic> json) {
    List<FutureDriverRead> drivers(Object? raw) => (raw as List? ?? const [])
        .whereType<Map>()
        .map((item) => FutureDriverRead.fromJson(Map<String, dynamic>.from(item)))
        .toList();
    final whale = json['whale_status'] is Map
        ? Map<String, dynamic>.from(json['whale_status'] as Map)
        : const <String, dynamic>{};
    return FutureHierarchyRead(
      reading: json['reading']?.toString() ?? 'UNKNOWN',
      coverage: (_number(json['coverage']) ?? 0).toDouble(),
      headline: json['headline']?.toString() ?? '',
      explanation: (json['explanation'] as List? ?? const [])
          .map((line) => line.toString())
          .where((line) => line.trim().isNotEmpty)
          .toList(),
      primary: json['primary_driver'] is Map
          ? FutureDriverRead.fromJson(
              Map<String, dynamic>.from(json['primary_driver'] as Map))
          : null,
      homeFactors: drivers(json['home_factors']),
      upcomingRisks: drivers(json['upcoming_invalidation_risks']),
      dataGaps: (json['data_gaps'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      whaleStatus: whale['status']?.toString() ?? 'Donnée indisponible',
      whaleTone: whale['tone']?.toString() ?? 'WHITE',
      whaleDetail: whale['detail']?.toString() ?? '',
      whalePrincipal: whale['principal'] == true,
    );
  }
}
