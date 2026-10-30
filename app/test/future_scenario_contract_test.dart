import 'package:crypto_intelligence_app/api/future_models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('the iPhone model keeps the complete three-scenario contract', () {
    final scenario = FutureScenarioRead.fromJson(const {
      'id': 'bullish_case',
      'probability': null,
      'probability_source': null,
      'directional_bias': 'BULLISH',
      'expected_movement': 'HIGH',
      'confidence': 0.72,
      'event_chain': ['Décision Fed sourcée'],
      'hypothesis': 'Évolution favorable sous conditions.',
      'horizon': '7d',
      'affected_assets': ['BTC'],
      'confirmed_evidence': ['Flux mesuré favorable'],
      'evidence_ids': ['obs:etf:1'],
      'conditions': ['Maintien des entrées nettes'],
      'confirmation_signals': ['Clôture confirmée'],
      'invalidation_conditions': ['Retournement durable des flux'],
      'uncertainties': ['Issue Fed inconnue'],
      'prudence_note': 'Scénario conditionnel.',
      'calibrated': false,
    });

    expect(scenario.hypothesis, isNotEmpty);
    expect(scenario.horizon, '7d');
    expect(scenario.affectedAssets, ['BTC']);
    expect(scenario.confirmedEvidence, ['Flux mesuré favorable']);
    expect(scenario.evidenceIds, ['obs:etf:1']);
    expect(scenario.conditions, ['Maintien des entrées nettes']);
    expect(scenario.confirmationSignals, ['Clôture confirmée']);
    expect(scenario.invalidationConditions, ['Retournement durable des flux']);
    expect(scenario.uncertainties, ['Issue Fed inconnue']);
    expect(scenario.prudenceNote, 'Scénario conditionnel.');
    expect(scenario.calibrated, isFalse);
    expect(scenario.probability, isNull);
  });

  test('an older scenario payload remains readable without invented fields',
      () {
    final scenario = FutureScenarioRead.fromJson(const {
      'id': 'base_case',
      'directional_bias': 'NEUTRAL',
      'expected_movement': 'NORMAL',
      'confidence': 0.2,
      'event_chain': [],
    });

    expect(scenario.hypothesis, isEmpty);
    expect(scenario.conditions, isEmpty);
    expect(scenario.uncertainties, isEmpty);
    expect(scenario.calibrated, isFalse);
  });

  test('a numeric probability is exposed only with the calibration audit', () {
    final calibrated = FutureScenarioRead.fromJson(const {
      'id': 'base_case',
      'probability': 0.42,
      'probability_source': 'licensed model output',
      'probability_observed_at': '2026-10-29T09:30:00Z',
      'directional_bias': 'NEUTRAL',
      'expected_movement': 'NORMAL',
      'confidence': 0.6,
      'event_chain': [],
      'calibrated': true,
      'calibration_metadata': {
        'model_name': 'scenario-calibrator',
        'model_version': '1',
        'target_definition': 'Direction realised over the selected horizon',
        'target_horizon': '7 days',
        'calibration_method': 'isotonic',
        'out_of_sample_tested': true,
        'out_of_sample_sample_size': 500,
        'evaluation_metric': 'Brier score',
        'evaluation_score': 0.18,
        'evaluated_at': '2026-10-28T09:30:00Z',
        'evidence_ids': ['calibration:scenario:v1'],
      },
    });
    final uncalibrated = FutureScenarioRead.fromJson(const {
      'id': 'bullish_case',
      'probability': 0.99,
      'directional_bias': 'BULLISH',
      'expected_movement': 'HIGH',
      'confidence': 0.4,
      'event_chain': [],
      'calibrated': false,
    });

    expect(calibrated.calibratedProbability, 0.42);
    expect(calibrated.probabilityObservedAt, isNotNull);
    expect(calibrated.calibrationMetadata?.outOfSampleSampleSize, 500);
    expect(calibrated.calibrationMetadata?.evidenceIds,
        ['calibration:scenario:v1']);
    expect(uncalibrated.probability, 0.99);
    expect(uncalibrated.calibratedProbability, isNull);
  });

  test('only base, bull and bear are kept in contractual order', () {
    FutureScenarioRead scenario(String id) => FutureScenarioRead(
          id: id,
          direction: 'NEUTRAL',
          movement: 'NORMAL',
          confidence: 0,
          eventChain: const [],
        );

    final ordered = orderedPublicFutureScenarios([
      scenario('tail_risk_case'),
      scenario('bearish_case'),
      scenario('base_case'),
      scenario('bullish_case'),
      scenario('base_case'),
    ]);

    expect(ordered.map((item) => item.id),
        ['base_case', 'bullish_case', 'bearish_case']);
  });
}
