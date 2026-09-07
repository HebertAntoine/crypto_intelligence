/// The evidence screen's job is to make a negative result readable.
///
/// These tests guard the two ways that can go wrong: showing a verdict without
/// the funnel that produced it, and colouring a low-evidence claim as though it
/// were established.
library;

import 'dart:convert';

import 'package:crypto_intelligence_app/api/client.dart';
import 'package:crypto_intelligence_app/screens/evidence_screen.dart';
import 'package:crypto_intelligence_app/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

Map<String, dynamic> _evidencePayload() => {
  'generated_at': '2026-09-07T10:00:00Z',
  'verdict': 'NO_SIGNAL_SUPPORTED',
  'highest_level_reached': 4,
  'n_actionable': 0,
  'by_level': {'OBSERVED': 8, 'STRATIFIED': 3, 'CONTROLLED': 1},
  'funnel': {
    'tests_started': 12,
    'survivors': 0,
    'expected_false_positives_at_alpha_05': 0.6,
    'note': 'douze tests sont entrés et zéro a survécu',
    'stages': [
      {'stage': 'pre-registered', 'count': 12, 'lost_here': 0},
      {'stage': 'testable', 'count': 12, 'lost_here': 0},
      {'stage': 'significant under any pooling method', 'count': 4, 'lost_here': 8},
      {'stage': 'survives leave-one-out', 'count': 0, 'lost_here': 4},
    ],
  },
  'shortlist': {
    'note': 'rien ici n’est une recommandation',
    'shortlist': [
      {
        'claim': 'H1 options chères précèdent des rendements plus bas @30d',
        'evidence_level': 4,
        'level_name': 'CONTROLLED',
        'effect_pct': -6.55,
        'blocked_at': 'ROBUST',
      },
    ],
  },
};

Map<String, dynamic> _powerPayload() => {
  'verdict': 'PIPELINE_CALIBRATED_BUT_INSENSITIVE',
  'note': 'le plancher dépasse le seuil utile à chaque horizon',
  'detection_floors': [
    {
      'horizon_days': 7,
      'empirical_floor_pct': 3.0,
      'meaningful_effect_pct': 1.0,
      'floor_above_meaningful': true,
    },
    {
      'horizon_days': 30,
      'empirical_floor_pct': 8.0,
      'meaningful_effect_pct': 2.0,
      'floor_above_meaningful': true,
    },
  ],
};

Map<String, dynamic> _poolingPayload() => {
  'assets_pooled': ['BTC', 'ETH'],
  'assets_unavailable': {'SOL': 'aucune série DVOL n’existe'},
  'mean_cross_asset_correlation': 0.778,
  'verdict_counts': {'INSUFFICIENT_DATA': 12},
};

ApiClient _client({bool empty = false}) {
  final mock = MockClient((request) async {
    if (empty) return http.Response('{"detail":"not generated"}', 404);
    final path = request.url.path;
    if (path.endsWith('/evidence')) {
      return http.Response(_encode(_evidencePayload()), 200,
          headers: {'content-type': 'application/json'});
    }
    if (path.endsWith('/power')) {
      return http.Response(_encode(_powerPayload()), 200,
          headers: {'content-type': 'application/json'});
    }
    if (path.endsWith('/pooling')) {
      return http.Response(_encode(_poolingPayload()), 200,
          headers: {'content-type': 'application/json'});
    }
    return http.Response('{"detail":"unknown"}', 404);
  });
  return ApiClient(
    client: mock,
    baseUrl: 'http://test.local/api',
    loadAsset: (_) async => throw Exception('no snapshot in this test'),
  );
}

String _encode(Map<String, dynamic> payload) => jsonEncode(payload);

Widget _wrap(Widget child) => MaterialApp(
  theme: AppTheme.dark,
  home: child,
);

void main() {
  testWidgets('a verdict is never shown without its funnel', (tester) async {
    await tester.pumpWidget(_wrap(EvidenceScreen(client: _client())));
    await tester.pumpAndSettle();

    // StatePill renders underscores as spaces.
    expect(find.text('NO SIGNAL SUPPORTED'), findsOneWidget);
    expect(find.text('ENTONNOIR DES TESTS'), findsOneWidget);
    expect(find.textContaining('douze tests sont entrés'), findsOneWidget);
  });

  testWidgets('the chance baseline is stated next to the survivors',
      (tester) async {
    await tester.pumpWidget(_wrap(EvidenceScreen(client: _client())));
    await tester.pumpAndSettle();

    expect(find.textContaining('hasard seul'), findsOneWidget);
  });

  testWidgets('the detection floor is shown against the meaningful effect',
      (tester) async {
    await tester.pumpWidget(_wrap(EvidenceScreen(client: _client())));
    await tester.pumpAndSettle();

    expect(find.text('PLANCHER DE DÉTECTION'), findsOneWidget);
    expect(find.textContaining('plancher 3.0 %'), findsOneWidget);
    expect(find.textContaining('seuil utile 1.0 %'), findsOneWidget);
  });

  testWidgets('SOL is named as unavailable rather than quietly omitted',
      (tester) async {
    await tester.pumpWidget(_wrap(EvidenceScreen(client: _client())));
    await tester.pumpAndSettle();

    expect(find.text('SOL'), findsOneWidget);
    expect(find.textContaining('aucune série DVOL'), findsOneWidget);
  });

  testWidgets('a missing study says how to generate it, never renders blank',
      (tester) async {
    await tester.pumpWidget(_wrap(EvidenceScreen(client: _client(empty: true))));
    await tester.pumpAndSettle();

    expect(find.text('ÉTUDE NON GÉNÉRÉE'), findsOneWidget);
    expect(find.textContaining('crypto-intel lot6b'), findsOneWidget);
  });

  testWidgets('the full ladder renders even when nothing has climbed it',
      (tester) async {
    await tester.pumpWidget(_wrap(EvidenceScreen(client: _client(empty: true))));
    await tester.pumpAndSettle();

    expect(find.text('ÉCHELLE DE PREUVE'), findsOneWidget);
    expect(find.text('CONFIRMÉ EN LIVE'), findsOneWidget);
  });
}
