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
      );
}

class FutureEventRead {
  final String id;
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

  /// What would have to happen to move the decision each way (section 14).
  final List<String> conditionsToBuy;
  final List<String> conditionsToSell;

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
      conditionsToBuy: (json['conditions_to_buy'] as List? ?? const [])
          .map((value) => value.toString())
          .toList(),
      conditionsToSell: (json['conditions_to_sell'] as List? ?? const [])
          .map((value) => value.toString())
          .toList(),
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
