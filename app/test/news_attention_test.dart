/// A news item is not a directional signal.
///
/// Watching something closely and knowing which way it will go are two
/// different statements. These tests fail the build if the catalyst payload
/// lets one stand in for the other.
library;

import 'package:crypto_intelligence_app/api/future_models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('FutureCatalystRead', () {
    test('reads attention and direction as separate fields', () {
      final item = FutureCatalystRead.fromJson(const {
        'title': 'Décision de taux de la BCE',
        'relevance_score': 80,
        'attention': 'CRITICAL',
        'direction': 'UNKNOWN',
      });

      expect(item.attention, 'CRITICAL');
      expect(item.direction, 'UNKNOWN');
      expect(item.directionIsUnknown, isTrue);
    });

    test('high attention does not imply a direction', () {
      final item = FutureCatalystRead.fromJson(const {
        'title': 'Réunion du FOMC',
        'attention': 'CRITICAL',
        'direction': 'UNKNOWN',
      });

      expect(item.directionIsUnknown, isTrue);
    });

    test('a payload without the fields defaults to no direction at all', () {
      final item = FutureCatalystRead.fromJson(const {'title': 'Événement'});

      expect(item.direction, 'UNKNOWN');
      expect(item.directionIsUnknown, isTrue);
      expect(item.attention, 'LOW');
    });

    test('a known direction is reported as known', () {
      final item = FutureCatalystRead.fromJson(const {
        'title': 'CPI publié sous le consensus',
        'attention': 'HIGH',
        'direction': 'FAVORABLE',
      });

      expect(item.directionIsUnknown, isFalse);
    });

    test('relevance and attention are independent numbers', () {
      final item = FutureCatalystRead.fromJson(const {
        'title': 'Adjudication du Trésor',
        'relevance_score': 67,
        'attention': 'MODERATE',
      });

      expect(item.relevanceScore, 67);
      expect(item.attention, 'MODERATE');
    });
  });
}
