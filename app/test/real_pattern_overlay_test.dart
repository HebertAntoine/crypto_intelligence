library;

import 'dart:convert';
import 'dart:io';

import 'package:crypto_intelligence_app/api/models.dart';
import 'package:crypto_intelligence_app/chart/pattern_geometry.dart';
import 'package:crypto_intelligence_app/widgets/real_pattern_overlay.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('Figures réelles du graphique', () {
    final snapshots = Directory('assets/api_snapshots')
        .listSync()
        .whereType<File>()
        .where((file) => file.path.split('/').last.startsWith('chart__'))
        .toList();

    test('les instantanés gardent des géométries vérifiables', () {
      expect(snapshots, isNotEmpty);
      var announced = 0;
      var verifiedCount = 0;
      for (final file in snapshots) {
        final chart = ChartRead.fromJson(
          (jsonDecode(file.readAsStringSync()) as Map).cast<String, dynamic>(),
        );
        announced += chart.structuralPatterns.length;
        final verified = verifiedRealPatterns(chart, maximum: 10000);
        verifiedCount += verified.length;
        for (final geometry in verified) {
          expect(drawablePatternNames, contains(geometry.pattern.name));
          expect(geometry.pattern.geometry.isEmpty, isFalse);
        }
      }
      expect(announced, greaterThan(0));
      expect(verifiedCount, greaterThan(0));
    });

    test('un prix de pivot qui ne correspond pas à sa bougie est refusé', () {
      final pattern = StructuralPatternRead.fromJson({
        'name': 'double_top',
        'geometry': {
          'points': [
            {
              'time': '2026-09-08T10:00:00Z',
              'price': 999,
              'role': 'first_top',
              'kind': 'pivot',
            },
            {
              'time': '2026-09-08T11:00:00Z',
              'price': 999,
              'role': 'second_top',
              'kind': 'pivot',
            },
          ],
          'trend_lines': [
            {
              'start': {'time': '2026-09-08T10:00:00Z', 'price': 90},
              'end': {'time': '2026-09-08T11:00:00Z', 'price': 90},
              'role': 'neckline',
            },
          ],
          'zones': [
            {
              'start_time': '2026-09-08T10:00:00Z',
              'end_time': '2026-09-08T11:00:00Z',
              'low': 90,
              'high': 100,
              'role': 'breakout',
            },
          ],
        },
      });
      final candles = [
        _candle(DateTime.utc(2026, 9, 8, 10)),
        _candle(DateTime.utc(2026, 9, 8, 11)),
      ];

      expect(verifyRealPatternGeometry(pattern, candles), isNull);
    });

    test('aucun rectangle générique ne devient une figure dessinable', () {
      expect(drawablePatternNames, isNot(contains('rectangle')));
    });

    test('la palette identifie chaque nom de façon stable', () {
      final colors = drawablePatternNames.map(realPatternColor).toSet();
      expect(colors, hasLength(drawablePatternNames.length));
    });
  });
}

CandlePoint _candle(DateTime time) => CandlePoint(
      time: time,
      open: 95,
      high: 100,
      low: 90,
      close: 96,
      volume: 1,
    );
