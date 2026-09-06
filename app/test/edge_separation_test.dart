/// The invariant this app exists to protect.
///
/// A recognition confidence must never be renderable without its edge state,
/// and a measured edge must never be inferred from a bullish direction. These
/// tests fail the build if either boundary is crossed.
library;

import 'package:crypto_intelligence_app/api/models.dart';
import 'package:crypto_intelligence_app/theme/app_theme.dart';
import 'package:crypto_intelligence_app/widgets/common.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('EdgeState parsing', () {
    test('maps every backend value', () {
      expect(EdgeState.parse('POSITIVE_EDGE'), EdgeState.positiveEdge);
      expect(EdgeState.parse('NEGATIVE_EDGE'), EdgeState.negativeEdge);
      expect(EdgeState.parse('NO_MEASURABLE_EDGE'), EdgeState.noMeasurableEdge);
      expect(EdgeState.parse('UNSTABLE'), EdgeState.unstable);
      expect(EdgeState.parse('INSUFFICIENT_DATA'), EdgeState.insufficientData);
      expect(EdgeState.parse('NOT_YET_TESTED'), EdgeState.notYetTested);
    });

    test('an unrecognised value becomes unknown, never a measured edge', () {
      expect(EdgeState.parse('SOMETHING_NEW'), EdgeState.unknown);
      expect(EdgeState.parse(null), EdgeState.unknown);
      expect(EdgeState.unknown.isMeasured, isFalse);
    });

    test('only POSITIVE_EDGE counts as measured', () {
      for (final state in EdgeState.values) {
        expect(state.isMeasured, state == EdgeState.positiveEdge,
            reason: '$state must not be treated as a measured edge');
      }
    });
  });

  group('Pattern model', () {
    test('recognition confidence and edge state are independent fields', () {
      final pattern = DetectedPattern.fromJson(const {
        'name': 'double_bottom',
        'pattern_class': 'DETERMINISTIC',
        'state': 'CONFIRMED',
        'recognition_confidence': 91.0,
        'direction_if_textbook': 'BULLISH',
        'edge_state': 'NO_MEASURABLE_EDGE',
        'key_levels': {'neckline': 100.5},
        'invalidation_rule': 'a close below 90 invalidates it',
        'notes': '',
        'separation_note': 'recognition is NOT a probability',
      });

      expect(pattern.recognitionConfidence, 91.0);
      expect(pattern.edgeState, EdgeState.noMeasurableEdge);
      expect(pattern.edgeState.isMeasured, isFalse);
    });

    test('an unknown edge_state never defaults to a measured one', () {
      final pattern = DetectedPattern.fromJson(const {
        'name': 'x',
        'recognition_confidence': 99.0,
      });
      expect(pattern.edgeState.isMeasured, isFalse);
    });

    test('detection class is surfaced so unreliable detectors say so', () {
      final experimental = DetectedPattern.fromJson(const {
        'name': 'wedge',
        'pattern_class': 'EXPERIMENTAL',
        'recognition_confidence': 88.0,
      });
      expect(experimental.classHint, contains('too subjective'));
    });
  });

  group('DecisionSummary', () {
    test('a bullish direction with no edge is not actionable', () {
      final summary = DecisionSummary.fromJson(const {
        'asset': 'BTC',
        'market_direction': 'STRONGLY_BULLISH',
        'edge_state': 'NO_MEASURABLE_EDGE',
        'actionable': false,
        'statement': 'BTC is strongly bullish, but we hold no robust edge.',
        'caveats': ['direction and edge are computed independently'],
      });

      expect(summary.marketDirection, 'STRONGLY_BULLISH');
      expect(summary.edgeState.isMeasured, isFalse);
      expect(summary.actionable, isFalse);
    });

    test('missing fields degrade to the most cautious values', () {
      final summary = DecisionSummary.fromJson(const {});
      expect(summary.marketDirection, 'UNDETERMINED');
      expect(summary.edgeState, EdgeState.unknown);
      expect(summary.actionable, isFalse);
      expect(summary.uncertainty, 100);
    });
  });

  group('EdgeBadge rendering', () {
    testWidgets('green is reserved for a measured edge', (tester) async {
      for (final state in EdgeState.values) {
        await tester.pumpWidget(
          MaterialApp(home: Scaffold(body: EdgeBadge(state: state))),
        );
        final badge = tester.widget<Text>(find.byType(Text));
        final isGreen = badge.style?.color == AppColors.measured;
        expect(isGreen, state == EdgeState.positiveEdge,
            reason: '$state must not use the measured-edge colour');
      }
    });

    testWidgets('every state renders a readable label', (tester) async {
      for (final state in EdgeState.values) {
        await tester.pumpWidget(
          MaterialApp(home: Scaffold(body: EdgeBadge(state: state))),
        );
        expect(find.text(state.label), findsOneWidget);
      }
    });
  });

  group('Absent values', () {
    test('formatters render null as an explicit dash, never as zero', () {
      expect(fmt(null), '—');
      expect(fmtSigned(null), '—');
      expect(fmt(double.nan), '—');
      expect(fmtSigned(1.5), '+1.50%');
      expect(fmtSigned(-1.5), '-1.50%');
    });

    testWidgets('UnavailableText states the absence rather than blank',
        (tester) async {
      await tester.pumpWidget(
        const MaterialApp(home: Scaffold(body: UnavailableText())),
      );
      expect(find.text('UNAVAILABLE'), findsOneWidget);
    });
  });
}
