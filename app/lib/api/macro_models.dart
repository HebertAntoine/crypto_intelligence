/// The macro radar (backend `engines/macro_drivers.py`): fifteen drivers
/// watched, five shown. Nothing is computed here - importance, direction and
/// every figure come from the engine.
library;

Map<String, dynamic> _m(Object? raw) =>
    raw is Map ? Map<String, dynamic>.from(raw) : <String, dynamic>{};

/// One figure under a driver, with the period it describes.
class MacroValue {
  final String label;
  final String value;
  final String change;
  final String period;
  final String source;

  const MacroValue({
    this.label = '',
    this.value = '',
    this.change = '',
    this.period = '',
    this.source = '',
  });

  factory MacroValue.fromJson(Object? raw) {
    final j = _m(raw);
    return MacroValue(
      label: j['label']?.toString() ?? '',
      value: j['value']?.toString() ?? '',
      change: j['change']?.toString() ?? '',
      period: j['period']?.toString() ?? '',
      source: j['source']?.toString() ?? '',
    );
  }
}

/// One driver as it currently reads.
///
/// `attention` and `direction` are two separate scales and must stay that
/// way: a central bank decision due tomorrow is CRITICAL and UNKNOWN at the
/// same time, and that is the honest reading.
class MacroDriver {
  final String key;
  final String emoji;
  final String name;
  final String state;
  final String direction;
  final String attention;
  final int importance;
  final List<String> importanceReasons;
  final String summary;
  final String channel;
  final String watching;
  final List<MacroValue> values;
  final DateTime? lastRelease;
  final DateTime? nextRelease;
  final String nextReleaseLabel;
  final bool available;
  final String unavailableReason;

  const MacroDriver({
    this.key = '',
    this.emoji = '📊',
    this.name = '',
    this.state = '',
    this.direction = 'UNKNOWN',
    this.attention = 'LOW',
    this.importance = 0,
    this.importanceReasons = const [],
    this.summary = '',
    this.channel = '',
    this.watching = '',
    this.values = const [],
    this.lastRelease,
    this.nextRelease,
    this.nextReleaseLabel = '',
    this.available = true,
    this.unavailableReason = '',
  });

  factory MacroDriver.fromJson(Object? raw) {
    final j = _m(raw);
    return MacroDriver(
      key: j['key']?.toString() ?? '',
      emoji: j['emoji']?.toString() ?? '📊',
      name: j['name']?.toString() ?? '',
      state: j['state']?.toString() ?? '',
      direction: j['direction']?.toString() ?? 'UNKNOWN',
      attention: j['attention']?.toString() ?? 'LOW',
      importance: (j['importance'] as num?)?.round() ?? 0,
      importanceReasons: [
        for (final r in (j['importance_reasons'] as List? ?? const []))
          r.toString()
      ],
      summary: j['summary']?.toString() ?? '',
      channel: j['channel']?.toString() ?? '',
      watching: j['watching']?.toString() ?? '',
      values: [
        for (final v in (j['values'] as List? ?? const [])) MacroValue.fromJson(v)
      ],
      lastRelease: DateTime.tryParse(j['last_release']?.toString() ?? '')?.toLocal(),
      nextRelease: DateTime.tryParse(j['next_release']?.toString() ?? '')?.toLocal(),
      nextReleaseLabel: j['next_release_label']?.toString() ?? '',
      available: j['available'] != false,
      unavailableReason: j['unavailable_reason']?.toString() ?? '',
    );
  }

  /// The colour and the word for a direction. Never derived from importance:
  /// an important driver can point nowhere yet.
  (String, String) get directionLabel => switch (direction) {
        'FAVORABLE' => ('🟢', 'Soutien'),
        'UNFAVORABLE' => ('🔴', 'Pression'),
        'NEUTRAL' => ('⚪', 'Neutre'),
        'MIXED' => ('🟡', 'Partagé'),
        _ => ('🔵', 'Sens inconnu'),
      };

  String get attentionLabel => switch (attention) {
        'CRITICAL' => 'Attention critique',
        'HIGH' => 'Attention élevée',
        'MODERATE' => 'Attention modérée',
        'LOW' => 'Attention faible',
        _ => 'Hors radar',
      };
}

/// What changed between two recorded cycles - read from the snapshots, never
/// re-derived from today's data.
class MacroChange {
  final String key;
  final String emoji;
  final String name;
  final String from;
  final String to;
  final String fromState;
  final String toState;

  const MacroChange({
    this.key = '',
    this.emoji = '',
    this.name = '',
    this.from = '',
    this.to = '',
    this.fromState = '',
    this.toState = '',
  });

  factory MacroChange.fromJson(Object? raw) {
    final j = _m(raw);
    return MacroChange(
      key: j['key']?.toString() ?? '',
      emoji: j['emoji']?.toString() ?? '',
      name: j['name']?.toString() ?? '',
      from: j['from']?.toString() ?? '',
      to: j['to']?.toString() ?? '',
      fromState: j['from_state']?.toString() ?? '',
      toState: j['to_state']?.toString() ?? '',
    );
  }
}

class MacroRadarRead {
  final DateTime? asOf;
  final DateTime? nextCheck;
  final List<MacroDriver> top;
  final List<MacroDriver> drivers;
  final List<MacroChange> changes;
  final String summary;
  final int watched;
  final List<String> unavailable;

  const MacroRadarRead({
    this.asOf,
    this.nextCheck,
    this.top = const [],
    this.drivers = const [],
    this.changes = const [],
    this.summary = '',
    this.watched = 0,
    this.unavailable = const [],
  });

  bool get isEmpty => drivers.isEmpty;

  factory MacroRadarRead.fromJson(Object? raw) {
    final j = _m(raw);
    return MacroRadarRead(
      asOf: DateTime.tryParse(j['as_of']?.toString() ?? '')?.toLocal(),
      nextCheck: DateTime.tryParse(j['next_check']?.toString() ?? '')?.toLocal(),
      top: [
        for (final d in (j['top'] as List? ?? const [])) MacroDriver.fromJson(d)
      ],
      drivers: [
        for (final d in (j['drivers'] as List? ?? const []))
          MacroDriver.fromJson(d)
      ],
      changes: [
        for (final c in (j['changes'] as List? ?? const []))
          MacroChange.fromJson(c)
      ],
      summary: j['summary']?.toString() ?? '',
      watched: (j['watched'] as num?)?.round() ?? 0,
      unavailable: [
        for (final u in (j['unavailable'] as List? ?? const [])) u.toString()
      ],
    );
  }
}
