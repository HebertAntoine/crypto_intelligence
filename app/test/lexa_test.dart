import 'dart:convert';

import 'package:crypto_intelligence_app/lexa/lexa_client.dart';
import 'package:crypto_intelligence_app/lexa/lexa_models.dart';
import 'package:crypto_intelligence_app/lexa/lexa_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

Map<String, dynamic> _level(int id, String kind, double value,
        {double? pct,
        double? eur,
        String? ts,
        String state = 'WAITING',
        bool toVerify = false,
        double? corrected}) =>
    {
      'id': id,
      'kind': kind,
      'emoji': kind == 'TARGET' ? '🎯' : '🟢',
      'kind_label': kind == 'TARGET' ? 'Objectif' : 'Zone d\'achat Lexa',
      'value': corrected ?? value,
      'original_value': value,
      'corrected_value': corrected,
      'corrected_at': corrected == null ? null : '2026-09-21T10:00:00+00:00',
      'allocation_pct': pct,
      'allocation_eur': eur,
      'timestamp': ts,
      'source_text': 'la zone d\'achat se situe vers 1,26',
      'condition': 'UNKNOWN',
      'condition_label': 'Condition non précisée',
      'to_verify': toVerify,
      'state': {
        'state': state,
        'emoji': state == 'TOUCHED' ? '🟢' : '⏳',
        'label': state == 'TOUCHED' ? 'Touché' : 'Non atteint',
        'first_touched_at': state == 'TOUCHED' ? '2026-09-21T11:00:00' : null,
        'note': '',
      },
    };

Map<String, dynamic> _report({double? performance = 4.21}) => {
      'analysis_id': 7,
      'asset': 'XRP',
      'video': {
        'id': 3,
        'title': 'Analyse XRP du 21 septembre',
        'published_at': '2026-09-21T08:00:00+00:00',
        'source_ref': '',
        'source': 'Lexa Moon',
      },
      'published_at': '2026-09-21T08:00:00+00:00',
      'processed_at': '2026-09-21T09:00:00',
      'price_at_video': 1.38,
      'stance': 'WAIT',
      'stance_emoji': '🟠',
      'stance_label': 'Attente',
      'summary': '',
      'capital_eur': 100,
      'current_price': 1.41,
      'levels': [
        _level(1, 'BUY_ZONE', 1.2688,
            pct: 60, eur: 60, ts: '18:42', state: 'TOUCHED', corrected: 1.268),
        _level(2, 'REINFORCEMENT', 1.2141, pct: 40, eur: 40, toVerify: true),
        _level(3, 'TARGET', 1.5339, pct: 25),
      ],
      'simulation': {
        'capital_eur': 100,
        'fills': [
          {'level_id': 1}
        ],
        'exits': [],
        'executed_eur': 60,
        'remaining_eur': 40,
        'quantity_held': 47.3,
        'average_price': 1.268,
        'realised_eur': 0,
        'current_price': 1.41,
        'current_value_eur': 106.7,
        'performance_pct': performance,
        'targets_hit': [],
        'invalidation_reached': false,
        'assumptions': [],
        'disclaimer':
            'Simulation du scénario extrait de la vidéo, pas une recommandation.',
      },
      'origin': 'LEXA',
      'note': 'Ce que dit Lexa - distinct de ce que montrent les données.',
    };

Widget _host(Widget child) => MaterialApp(
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

void main() {
  test('the public build never contains the Lexa tab', () {
    expect(lexaEnabled, isFalse);
  });

  test('French numbers and prices', () {
    expect(parseFrNumber('1,2688'), 1.2688);
    expect(parseFrNumber('70 000 \$'), 70000);
    expect(parseFrNumber('abc'), isNull);
    expect(fmtPrice(1.2688), '1,2688 \$');
    expect(fmtPrice(70250), '70 250 \$');
    expect(fmtPrice(null), '—');
  });

  test('offset-less backend dates are read as UTC', () {
    final report = LexaReport.fromJson(_report());
    expect(report.processedAt!.toUtc(), DateTime.utc(2026, 9, 21, 9));
  });

  testWidgets('a report says it is Lexa, with states, timestamps and doubts',
      (tester) async {
    await tester.pumpWidget(_host(LexaReportView(
      report: LexaReport.fromJson(_report()),
      onCorrect: (_) {},
    )));
    expect(find.text('Ce que dit Lexa'), findsOneWidget);
    expect(find.text('🎬 Voir à 18:42'), findsOneWidget);
    expect(find.text('🟢 Touché'), findsOneWidget);
    expect(find.textContaining('À vérifier'), findsOneWidget);
    expect(find.textContaining('valeur d\'origine 1,2688 \$'), findsOneWidget);
    expect(find.text('+4,21 %'), findsOneWidget);
    expect(find.textContaining('pas une recommandation'), findsOneWidget);
    expect(find.text('✏️ Modifier'), findsNWidgets(3));
  });

  testWidgets('no fill is said as such, never as 0 %', (tester) async {
    await tester.pumpWidget(_host(LexaReportView(
        report: LexaReport.fromJson(_report(performance: null)))));
    expect(find.text('Aucun achat exécuté'), findsOneWidget);
    expect(find.text('0,00 %'), findsNothing);
  });

  testWidgets('the comparison keeps both readings apart', (tester) async {
    await tester.pumpWidget(_host(LexaComparisonCard(data: {
      'lexa': _report(),
      'ours': null,
      'ours_note':
          'L\'application n\'analyse pas XRP : aucune comparaison possible.',
      'rule':
          'Les deux lectures restent indépendantes : aucune ne corrige l\'autre.',
    })));
    expect(find.text('🎬 Ce que dit Lexa'), findsOneWidget);
    expect(find.text('📊 Ce que montrent nos données'), findsOneWidget);
    expect(find.textContaining('n\'analyse pas XRP'), findsOneWidget);
    expect(find.textContaining('indépendantes'), findsOneWidget);
  });

  test('the client surfaces the backend refusal in French', () async {
    final client = LexaClient(
      baseUrl: 'http://127.0.0.1:8100',
      client: MockClient((request) async => http.Response(
          jsonEncode(
              {'detail': 'Lexa n\'est accessible que depuis cette machine.'}),
          403)),
    );
    expect(
      () => client.videos(),
      throwsA(isA<LexaException>()
          .having((e) => e.message, 'message', contains('cette machine'))),
    );
  });

  test('the client only calls the configured local backend', () async {
    Uri? called;
    final client = LexaClient(
      baseUrl: 'http://127.0.0.1:8100/',
      client: MockClient((request) async {
        called = request.url;
        return http.Response(jsonEncode({'videos': []}), 200);
      }),
    );
    await client.videos();
    expect(called.toString(), 'http://127.0.0.1:8100/api/lexa/videos');
  });

  testWidgets('the entry form sends exactly what was typed', (tester) async {
    tester.view.physicalSize = const Size(900, 3000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    Map<String, dynamic>? sent;
    final client = LexaClient(
      baseUrl: 'http://127.0.0.1:8100',
      client: MockClient((request) async {
        sent = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(jsonEncode({'video_id': 1}), 200);
      }),
    );
    await tester.pumpWidget(MaterialApp(
      home: LexaEntryScreen(client: client, now: DateTime(2026, 9, 21, 10)),
    ));

    await tester.tap(find.text('Enregistrer la vidéo'));
    await tester.pump();
    expect(find.textContaining('titre de la vidéo est obligatoire'),
        findsOneWidget);
    expect(sent, isNull);

    await tester.enterText(
        find.widgetWithText(TextField, 'Titre de la vidéo'), 'Analyse XRP');
    await tester.enterText(find.widgetWithText(TextField, 'Crypto'), 'xrp');
    await tester.enterText(
        find.widgetWithText(TextField, 'Prix dans la vidéo (\$)'), '1,38');
    await tester.enterText(
        find.widgetWithText(TextField, 'Prix (\$)'), '1,2688');
    await tester.enterText(
        find.widgetWithText(TextField, '% du capital'), '60');
    await tester.enterText(find.widgetWithText(TextField, 'Minutage'), '18:42');
    await tester.tap(find.text('Enregistrer la vidéo'));
    await tester.pumpAndSettle();

    expect(sent, isNotNull);
    expect(sent!['title'], 'Analyse XRP');
    expect(sent!['published_at'],
        DateTime(2026, 9, 21, 10).toUtc().toIso8601String());
    final asset = (sent!['assets'] as List).single as Map;
    expect(asset['asset'], 'XRP');
    expect(asset['price_at_video'], 1.38);
    final level = (asset['levels'] as List).single as Map;
    expect(level['kind'], 'BUY_ZONE');
    expect(level['value'], 1.2688);
    expect(level['allocation_pct'], 60);
    expect(level['timestamp'], '18:42');
    expect(level['condition'], 'UNKNOWN');
    expect(level['confidence'], 'HIGH');
  });
}
