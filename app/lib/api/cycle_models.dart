/// The market cycle page: a phase, a chart, and the history behind both.
library;

double? _number(Object? raw) => raw is num ? raw.toDouble() : null;

List<String> _strings(Object? raw) =>
    (raw as List? ?? const []).map((item) => item.toString()).toList();

Map<String, dynamic> _map(Object? raw) =>
    raw is Map ? Map<String, dynamic>.from(raw) : const <String, dynamic>{};

List<Map<String, dynamic>> _maps(Object? raw) => (raw as List? ?? const [])
    .whereType<Map>()
    .map((item) => Map<String, dynamic>.from(item))
    .toList();

/// One point of the price curve: a day and its close, in dollars.
class CyclePoint {
  final DateTime date;
  final double price;

  const CyclePoint({required this.date, required this.price});

  factory CyclePoint.fromJson(Map<String, dynamic> json) => CyclePoint(
        date: DateTime.tryParse(json['t']?.toString() ?? '') ?? DateTime(2011),
        price: _number(json['c']) ?? 0,
      );
}

/// A stretch of the chart the engine classified as one phase.
class CyclePhaseRun {
  final String phase;
  final String label;
  final String tone;
  final DateTime start;
  final DateTime end;
  final int days;

  const CyclePhaseRun({
    required this.phase,
    required this.label,
    required this.tone,
    required this.start,
    required this.end,
    required this.days,
  });

  factory CyclePhaseRun.fromJson(Map<String, dynamic> json) => CyclePhaseRun(
        phase: json['phase']?.toString() ?? '',
        label: json['label']?.toString() ?? '',
        tone: json['tone']?.toString() ?? 'WHITE',
        start: DateTime.tryParse(json['start']?.toString() ?? '') ?? DateTime(2011),
        end: DateTime.tryParse(json['end']?.toString() ?? '') ?? DateTime(2011),
        days: (_number(json['days']) ?? 0).round(),
      );
}

/// A halving, a record, a confirmed bottom or a measured shock.
class CycleMarker {
  final String kind;
  final String emoji;
  final String label;
  final DateTime date;
  final double? price;
  final bool estimated;

  const CycleMarker({
    required this.kind,
    required this.emoji,
    required this.label,
    required this.date,
    this.price,
    this.estimated = false,
  });

  factory CycleMarker.fromJson(Map<String, dynamic> json, {String kind = ''}) => CycleMarker(
        kind: json['kind']?.toString() ?? kind,
        emoji: json['emoji']?.toString() ?? '',
        label: json['label']?.toString() ?? '',
        date: DateTime.tryParse(json['date']?.toString() ?? '') ?? DateTime(2011),
        price: _number(json['price']),
        estimated: json['estimated'] == true,
      );
}

class CycleChart {
  final bool logScale;
  final List<CyclePoint> points;
  final List<CyclePhaseRun> phases;
  final List<CycleMarker> halvings;
  final List<CycleMarker> annotations;
  final DateTime todayDate;
  final double todayPrice;
  final Map<String, dynamic> localLow;

  const CycleChart({
    required this.logScale,
    required this.points,
    required this.phases,
    required this.halvings,
    required this.annotations,
    required this.todayDate,
    required this.todayPrice,
    required this.localLow,
  });

  factory CycleChart.fromJson(Map<String, dynamic> json) {
    final today = _map(json['today']);
    return CycleChart(
      logScale: json['log_scale'] != false,
      points: (json['points'] as List? ?? const [])
          .whereType<Map>()
          .map((p) => CyclePoint.fromJson(Map<String, dynamic>.from(p)))
          .toList(),
      phases: _maps(json['phases']).map(CyclePhaseRun.fromJson).toList(),
      halvings: _maps(json['halvings'])
          .map((h) => CycleMarker.fromJson(h, kind: 'HALVING'))
          .toList(),
      annotations: _maps(json['annotations']).map(CycleMarker.fromJson).toList(),
      todayDate: DateTime.tryParse(today['date']?.toString() ?? '') ?? DateTime.now(),
      todayPrice: _number(today['price']) ?? 0,
      localLow: _map(json['local_low']),
    );
  }
}

/// What a past cycle actually did - history, never a schedule.
class CycleStatsRead {
  final String name;
  final DateTime halving;
  final double? ath;
  final DateTime? athDate;
  final int? daysToAth;
  final double? gainPct;
  final double? drawdownPct;
  final int? bearDays;
  final int? recoveryDays;
  final bool ongoing;
  final bool bottomConfirmed;

  const CycleStatsRead({
    required this.name,
    required this.halving,
    required this.ongoing,
    required this.bottomConfirmed,
    this.ath,
    this.athDate,
    this.daysToAth,
    this.gainPct,
    this.drawdownPct,
    this.bearDays,
    this.recoveryDays,
  });

  factory CycleStatsRead.fromJson(Map<String, dynamic> json) => CycleStatsRead(
        name: json['name']?.toString() ?? '',
        halving: DateTime.tryParse(json['halving']?.toString() ?? '') ?? DateTime(2012),
        ongoing: json['ongoing'] == true,
        bottomConfirmed: json['bottom_confirmed'] == true,
        ath: _number(json['ath']),
        athDate: DateTime.tryParse(json['ath_date']?.toString() ?? ''),
        daysToAth: _number(json['days_to_ath'])?.round(),
        gainPct: _number(json['gain_from_halving_pct']),
        drawdownPct: _number(json['drawdown_after_ath_pct']),
        bearDays: _number(json['bear_days'])?.round(),
        recoveryDays: _number(json['recovery_days'])?.round(),
      );
}

/// One cycle rebased to 100 on its halving.
class NormalisedCycle {
  final String name;
  final bool ongoing;
  final List<({int day, double index})> points;

  const NormalisedCycle({
    required this.name,
    required this.ongoing,
    required this.points,
  });

  factory NormalisedCycle.fromJson(Map<String, dynamic> json) => NormalisedCycle(
        name: json['name']?.toString() ?? '',
        ongoing: json['ongoing'] == true,
        points: _maps(json['points'])
            .map((p) => (
                  day: (_number(p['day']) ?? 0).round(),
                  index: _number(p['index']) ?? 0,
                ))
            .toList(),
      );
}

/// One archived monthly reading, exactly as it was written that month.
class CycleSnapshotRead {
  final String monthLabel;
  final String phase;
  final String phaseLabel;
  final String phaseEmoji;
  final String direction;
  final double price;
  final double drawdown;
  final String notes;
  final List<String> changes;

  const CycleSnapshotRead({
    required this.monthLabel,
    required this.phase,
    required this.phaseLabel,
    required this.phaseEmoji,
    required this.direction,
    required this.price,
    required this.drawdown,
    required this.notes,
    required this.changes,
  });

  factory CycleSnapshotRead.fromJson(Map<String, dynamic> json) => CycleSnapshotRead(
        monthLabel: json['month_label']?.toString() ?? '',
        phase: json['phase']?.toString() ?? '',
        phaseLabel: json['phase_label']?.toString() ?? '',
        phaseEmoji: json['phase_emoji']?.toString() ?? '🔄',
        direction: json['direction']?.toString() ?? 'STABLE',
        price: _number(json['btc_price']) ?? 0,
        drawdown: _number(json['drawdown_from_ath']) ?? 0,
        notes: json['notes']?.toString() ?? '',
        changes: _strings(json['changes']),
      );
}

class CycleNextStep {
  final String toLabel;
  final String toEmoji;
  final List<String> conditions;
  final String invalidationLabel;
  final String invalidationEmoji;
  final String invalidation;
  final String? candidateLabel;
  final String candidateProgress;

  const CycleNextStep({
    required this.toLabel,
    required this.toEmoji,
    required this.conditions,
    required this.invalidationLabel,
    required this.invalidationEmoji,
    required this.invalidation,
    required this.candidateProgress,
    this.candidateLabel,
  });

  factory CycleNextStep.fromJson(Map<String, dynamic> json) => CycleNextStep(
        toLabel: json['to_label']?.toString() ?? '',
        toEmoji: json['to_emoji']?.toString() ?? '',
        conditions: _strings(json['conditions']),
        invalidationLabel: json['invalidation_label']?.toString() ?? '',
        invalidationEmoji: json['invalidation_emoji']?.toString() ?? '',
        invalidation: json['invalidation']?.toString() ?? '',
        candidateLabel: json['candidate_label']?.toString(),
        candidateProgress: json['candidate_progress']?.toString() ?? '',
      );
}

class CycleRead {
  final String asset;
  final String title;
  final bool isBtc;
  final String phase;
  final String phaseLabel;
  final String phaseEmoji;
  final String tone;
  final String directionLabel;
  final String directionEmoji;
  final String summary;
  final List<String> reasons;
  final int? daysSinceHalving;
  final double drawdownPct;
  final int daysInPhase;
  final double price;
  final double ath;
  final CycleNextStep nextStep;
  final CycleChart chart;
  final List<CycleStatsRead> cycles;
  final List<NormalisedCycle> normalised;
  final List<CycleSnapshotRead> snapshots;
  final Map<String, dynamic> relativeStrength;
  final String disclaimer;

  const CycleRead({
    required this.asset,
    required this.title,
    required this.isBtc,
    required this.phase,
    required this.phaseLabel,
    required this.phaseEmoji,
    required this.tone,
    required this.directionLabel,
    required this.directionEmoji,
    required this.summary,
    required this.reasons,
    required this.drawdownPct,
    required this.daysInPhase,
    required this.price,
    required this.ath,
    required this.nextStep,
    required this.chart,
    required this.cycles,
    required this.normalised,
    required this.snapshots,
    required this.relativeStrength,
    required this.disclaimer,
    this.daysSinceHalving,
  });

  factory CycleRead.fromJson(Map<String, dynamic> json) {
    final phase = _map(json['phase']);
    final figures = _map(json['figures']);
    return CycleRead(
      asset: json['asset']?.toString() ?? 'BTC',
      title: json['title']?.toString() ?? '🔄 Cycle Bitcoin',
      isBtc: json['is_btc'] == true,
      phase: phase['phase']?.toString() ?? '',
      phaseLabel: phase['phase_label']?.toString() ?? '',
      phaseEmoji: phase['phase_emoji']?.toString() ?? '🔄',
      tone: phase['tone']?.toString() ?? 'WHITE',
      directionLabel: phase['direction_label']?.toString() ?? '',
      directionEmoji: phase['direction_emoji']?.toString() ?? '',
      summary: phase['summary']?.toString() ?? '',
      reasons: _strings(phase['reasons']),
      daysSinceHalving: _number(figures['days_since_halving'])?.round(),
      drawdownPct: _number(figures['drawdown_pct']) ?? 0,
      daysInPhase: (_number(figures['days_in_phase']) ?? 0).round(),
      price: _number(figures['price']) ?? 0,
      ath: _number(figures['ath']) ?? 0,
      nextStep: CycleNextStep.fromJson(_map(json['next_step'])),
      chart: CycleChart.fromJson(_map(json['chart'])),
      cycles: _maps(json['cycles']).map(CycleStatsRead.fromJson).toList(),
      normalised: _maps(json['normalised']).map(NormalisedCycle.fromJson).toList(),
      snapshots: _maps(json['snapshots']).map(CycleSnapshotRead.fromJson).toList(),
      relativeStrength: _map(json['relative_strength']),
      disclaimer: json['disclaimer']?.toString() ?? '',
    );
  }
}
