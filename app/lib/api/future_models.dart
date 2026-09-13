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

class FutureFamilyRead {
  final String id;
  final String label;
  final bool available;
  final String? direction;
  final String? movement;
  final String summary;
  final String freshness;
  final String? unavailableReason;

  const FutureFamilyRead({
    required this.id,
    required this.label,
    required this.available,
    required this.summary,
    required this.freshness,
    this.direction,
    this.movement,
    this.unavailableReason,
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
  final List<String> changes;
  final List<FutureFamilyRead> families;
  final List<FutureScenarioRead> scenarios;
  final FutureEventRead? nextEvent;

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
    required this.changes,
    required this.families,
    required this.scenarios,
    this.asOf,
    this.nextEvent,
  });

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
      coverage: familyBlock['coverage']?.toString() ?? '0/5 disponibles',
      reasons: (json['reasons'] as List? ?? const [])
          .whereType<Map>()
          .map((value) =>
              FutureReasonRead.fromJson(Map<String, dynamic>.from(value)))
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
