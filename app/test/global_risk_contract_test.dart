/// Typed client contract for the three exact global-risk windows.
library;

import 'package:crypto_intelligence_app/api/future_models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('global risk preserves exact windows and fail-closed long horizon', () {
    final read = GlobalRiskRead.fromJson({
      'asset': 'BTC',
      'analysis_id': 'an-risk',
      'assessment_time': '2026-10-30T08:00:00Z',
      'methodology': 'Aucune probabilité de rendement.',
      'risk_horizons': [
        _horizon(
          '31-90d',
          'INDETERMINATE',
          usable: 0,
          events: 1,
          limitation: 'Projection 31-90 jours indisponible.',
        ),
        _horizon('91-120d', 'HIGH', usable: 5, events: 2),
        _horizon('1-7d', 'HIGH', usable: 5, events: 2),
        _horizon('8-30d', 'MODERATE', usable: 4, events: 1),
      ],
    });

    expect(read.horizons.map((item) => item.horizon), [
      '1-7d',
      '8-30d',
      '31-90d',
    ]);
    expect(read.horizons.last.level, 'INDETERMINATE');
    expect(read.horizons.last.coverage.authorizedEventCount, 1);
    expect(read.horizons.first.mainDrivers.single, contains('BTC'));
    expect(read.horizons.last.coverage.limitations, isNotEmpty);
  });
}

Map<String, Object> _horizon(
  String horizon,
  String level, {
  required int usable,
  required int events,
  String? limitation,
}) =>
    {
      'risk_level': level,
      'horizon': horizon,
      'assessment_time': '2026-10-30T08:00:00Z',
      'data_coverage': {
        'status': usable >= 3 ? 'SUFFICIENT' : 'INSUFFICIENT',
        'available_families': <String>[],
        'usable_families': [
          for (var index = 0; index < usable; index++) 'f$index'
        ],
        'unavailable_families': <String>[],
        'total_families': 5,
        'authorized_event_count': events,
        'limitations': [if (limitation != null) limitation],
      },
      'main_drivers': ['Événement HIGH/HIGH: CPI (actifs affectés: BTC)'],
      'counter_signals': <String>[],
      'change_since_previous': 'NOT_AVAILABLE',
      'evidence_ids': ['evidence-cpi'],
      'invalidation_conditions': ['Reclasser après publication.'],
    };
