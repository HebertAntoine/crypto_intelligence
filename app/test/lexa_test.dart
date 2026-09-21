// The 🎬 Lexa tab. Plans come from test/fixtures/lexa_fictive.json, produced
// by the real backend on a scripted market with FICTIONAL levels: no Lexa
// content is committed to this public repository.
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto_intelligence_app/lexa/lexa_client.dart';
import 'package:crypto_intelligence_app/lexa/lexa_home.dart';
import 'package:crypto_intelligence_app/lexa/lexa_listen_screen.dart';
import 'package:crypto_intelligence_app/lexa/recorder/recorder.dart';
import 'package:crypto_intelligence_app/lexa/lexa_models.dart';
import 'package:crypto_intelligence_app/lexa/lexa_plan_page.dart';
import 'package:crypto_intelligence_app/lexa/lexa_screen.dart';
import 'package:crypto_intelligence_app/lexa/lexa_test_screen.dart';
import 'package:crypto_intelligence_app/lexa/lexa_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

final Map<String, dynamic> fixtures =
    jsonDecode(File('test/fixtures/lexa_fictive.json').readAsStringSync())
        as Map<String, dynamic>;

Map<String, dynamic> _copy(String key) =>
    jsonDecode(jsonEncode(fixtures[key])) as Map<String, dynamic>;

http.Response _json(Object body) => http.Response(jsonEncode(body), 200,
    headers: {'content-type': 'application/json; charset=utf-8'});

LexaClient _backend(Map<String, Object> routes) => LexaClient(
      baseUrl: 'http://127.0.0.1:8100',
      client: MockClient((request) async {
        final path = request.url.path.replaceFirst('/api/lexa', '');
        final body = routes[path];
        return body == null ? http.Response('{}', 404) : _json(body);
      }),
    );

void _tall(WidgetTester tester) {
  tester.view.physicalSize = const Size(900, 5200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

void main() {
  test('without LEXA_ENABLED the Lexa tab is compiled out', () {
    expect(lexaEnabled, isFalse);
  });

  test('French numbers and prices keep every decimal said', () {
    expect(parseFrNumber('2,15696'), 2.15696);
    expect(parseFrNumber('70 000 \$'), 70000);
    expect(parseFrNumber('abc'), isNull);
    expect(fmtPrice(2.444175), '2,444175 \$');
    expect(fmtPrice(70250), '70 250 \$');
    expect(fmtPrice(null), '—');
  });

  test('a video link jumps to the passage when the platform allows it', () {
    expect(videoAt('https://www.youtube.com/watch?v=abc', 1122).toString(),
        'https://www.youtube.com/watch?v=abc&t=1122s');
    expect(videoAt('https://exemple.fr/v/1', 1122).toString(),
        'https://exemple.fr/v/1');
    expect(videoAt('', 10), isNull);
    expect(fmtTimestamp(1122), '18:42');
  });

  testWidgets('the plan answers « que faire maintenant ? » first',
      (tester) async {
    _tall(tester);
    final plan = _copy('plan_wait_close');
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: LexaPlanView(plan: plan, onWhy: () {}))));
    await tester.pumpAndSettle();
    expect(find.text('ATTENDRE CLÔTURE'), findsWidgets);
    expect(find.byKey(const ValueKey('lexa-verdict')), findsOneWidget);
    expect(find.text('ATTENDRE'), findsWidgets);
    expect(find.textContaining('pas une confirmation'), findsWidgets);
    expect(find.textContaining('heure de Paris'), findsWidgets);
    expect(find.text('Action en attente'), findsOneWidget);
    // A touch is never shown as a validated confirmation.
    expect(find.textContaining('Confirmé'), findsNothing);
    // Sections in the brief's order.
    final order = [
      'Prochaine action',
      'Plan',
      'Mon budget',
      'Dates',
      'Ce que dit Lexa',
      'Interprétation de l\'application',
      'Validation par nos données',
      'Historique du plan',
    ];
    final ys = [
      for (final t in order) tester.getTopLeft(find.text(t).first).dy
    ];
    expect(ys, [...ys]..sort());
  });

  testWidgets('our amounts are ours, Lexa\'s words are hers', (tester) async {
    _tall(tester);
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: LexaPlanView(plan: _copy('plan_wait_close')))));
    await tester.pumpAndSettle();
    expect(find.text('Montant décidé par toi'), findsNWidgets(2));
    expect(find.text('60,00 €'), findsWidgets);
    expect(find.textContaining('🎬 18:42'), findsWidgets);
    expect(find.textContaining('(dit par Lexa)'), findsWidgets); // TP shares
    expect(find.textContaining('Données insuffisantes'), findsWidgets);
    expect(find.textContaining('aucun ordre'), findsWidgets);
  });

  testWidgets('« Pourquoi ? » lists the reasons and the IF / THEN rules',
      (tester) async {
    _tall(tester);
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: LexaWhyView(plan: _copy('plan_wait_close')))));
    expect(find.text('Pourquoi attendre ?'), findsOneWidget);
    expect(find.textContaining('SI '), findsWidgets);
    expect(find.textContaining('ALORS '), findsWidgets);
    expect(find.text('Clôture'), findsWidgets);
  });

  testWidgets('the Lexa page follows plans by date, then shows each plan',
      (tester) async {
    _tall(tester);
    final client = _backend({
      '/overview': _copy('overview'),
      '/calendar': _copy('calendar'),
      '/plans-history': {'analyses': []},
    });
    await tester.pumpWidget(
        MaterialApp(home: Scaffold(body: LexaHomeScreen(client: client))));
    await tester.pumpAndSettle();
    expect(find.text('Plans & analyses'), findsOneWidget);
    expect(find.text('À suivre'), findsOneWidget);
    expect(find.text("AUJOURD'HUI"), findsOneWidget);
    expect(find.text('DEMAIN'), findsOneWidget);
    expect(find.byKey(const ValueKey('lexa-follow-XRP')), findsOneWidget);
    expect(find.text('Niveau surveillé : 2,444175 \$'), findsOneWidget);
    expect(find.byKey(const ValueKey('lexa-card-BTC')), findsOneWidget);
    expect(find.text('ENTRE DEUX NIVEAUX'), findsWidgets);

    // Filters: one crypto at a time, including those outside BTC/ETH/SOL.
    await tester.tap(find.text('XRP').first);
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('lexa-card-BTC')), findsNothing);
    expect(find.byKey(const ValueKey('lexa-card-XRP')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('lexa-view-CALENDAR')));
    await tester.pumpAndSettle();
    expect(find.text('Attendre clôture journalière'), findsOneWidget);
    expect(find.text('Réévaluation du scénario'), findsWidgets);
  });

  testWidgets('with no analysis the page explains how to add one',
      (tester) async {
    _tall(tester);
    final client = _backend({
      '/overview': {'follow': [], 'plans': [], 'unread_notifications': 0},
    });
    await tester.pumpWidget(
        MaterialApp(home: Scaffold(body: LexaHomeScreen(client: client))));
    await tester.pumpAndSettle();
    expect(find.text('Aucune analyse Lexa'), findsOneWidget);
    expect(find.text('Saisir une vidéo'), findsOneWidget);
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
      () => client.overview(),
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
    await client.plan(7);
    expect(called.toString(), 'http://127.0.0.1:8100/api/lexa/analyses/7/plan');
  });

  testWidgets('the entry form sends what was typed, conditions included',
      (tester) async {
    _tall(tester);
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
        find.widgetWithText(TextField, 'Titre de la vidéo'), 'Analyse test');
    await tester.enterText(find.widgetWithText(TextField, 'Crypto'), 'xrp');
    await tester.enterText(
        find.widgetWithText(TextField, 'Prix dans la vidéo (\$)'), '2,346');
    await tester.enterText(
        find.widgetWithText(TextField, 'Prix (\$)'), '2,15696');
    await tester.enterText(find.widgetWithText(TextField, 'Minutage'), '18:42');
    await tester.tap(find.text('+ 🚀 Confirmation'));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextField, 'Prix (\$)').last, '2,444175');
    await tester.tap(find.text('Non précisée dans la vidéo'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Clôture journalière').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Enregistrer la vidéo'));
    await tester.pumpAndSettle();

    expect(sent, isNotNull);
    expect(sent!['published_at'],
        DateTime(2026, 9, 21, 10).toUtc().toIso8601String());
    final asset = (sent!['assets'] as List).single as Map;
    expect(asset['asset'], 'XRP');
    expect(asset['price_at_video'], 2.346);
    expect(asset['review_at'],
        DateTime(2026, 9, 28, 10).toUtc().toIso8601String());
    final levels = (asset['levels'] as List).cast<Map>();
    expect(levels.first['kind'], 'BUY_ZONE');
    expect(
        levels.first['allocation_pct'], isNull); // nothing said, nothing sent
    expect(levels.first['basis'], 'EXPLICIT');
    expect(levels.first['conditions'], isEmpty);
    final cond = (levels.last['conditions'] as List).single as Map;
    expect(cond['timeframe'], '1D');
    expect(cond['operator'], 'ABOVE');
    expect(cond['required_closes'], 1);
  });

  testWidgets('a test run shows its report, validation, transcript and JSON',
      (tester) async {
    tester.view.physicalSize = const Size(900, 2400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    var polls = 0;
    Map<String, dynamic>? posted;
    final client = LexaClient(
      baseUrl: 'http://127.0.0.1:8100',
      client: MockClient((request) async {
        final path = request.url.path;
        if (request.method == 'POST') {
          posted = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(jsonEncode({'run_id': '20260921T120000Z'}), 200);
        }
        if (path.endsWith('/test-runs')) {
          return http.Response(jsonEncode({'runs': []}), 200);
        }
        polls++;
        final done = polls > 1;
        return http.Response(
            jsonEncode({
              'status': {'state': done ? 'DONE' : 'RUNNING'},
              if (done) ...{
                'report':
                    '# 🎬 Test\n## ADA\n| Niveau | Interprétation |\n|---|---|\n'
                        '| 0,487 \$ | 🟢 Achat principal |\n> **SIMULATION APP** : parts égales',
                'validation': '## CONCLUSION TECHNIQUE\n🟡 7 niveaux vérifiés',
                'transcript': '[03:02] Si ADA revient vers 0,4870',
                'extraction': {'schema_version': 'lexa-extraction/1'},
              },
            }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'});
      }),
    );
    await tester.pumpWidget(MaterialApp(
      home: LexaTestScreen(
          client: client, pollEvery: const Duration(milliseconds: 10)),
    ));
    await tester.enterText(
        find.widgetWithText(TextField, 'Titre de la vidéo'), 'Vidéo test');
    await tester.enterText(
        find.widgetWithText(TextField, 'Transcription horodatée'),
        '[03:02] Si ADA revient vers 0,4870');
    await tester.tap(find.text('Lancer le test'));
    // The spinner never settles while the run is RUNNING: pump until done.
    for (var i = 0; i < 50 && find.text('Rapport').evaluate().isEmpty; i++) {
      await tester.pump(const Duration(milliseconds: 20));
    }
    await tester.pumpAndSettle();

    expect(posted!['title'], 'Vidéo test');
    expect(posted!['published_at'], isNull);
    expect(find.text('0,487 \$'), findsOneWidget);
    expect(find.text('🟢 Achat principal'), findsOneWidget);
    await tester.tap(find.text('Validation'));
    await tester.pumpAndSettle();
    expect(find.text('CONCLUSION TECHNIQUE'), findsOneWidget);
    await tester.tap(find.text('JSON'));
    await tester.pumpAndSettle();
    expect(find.textContaining('lexa-extraction/1'), findsOneWidget);
  });

  testWidgets('listening: start, stop, check once, then the plan is created',
      (tester) async {
    _tall(tester);
    final calls = <String>[];
    var imported = false;
    var finished = false;
    final client = LexaClient(
      baseUrl: 'http://127.0.0.1:8100',
      client: MockClient((request) async {
        final path = request.url.path.replaceFirst('/api/lexa', '');
        calls.add('${request.method} $path');
        return switch (path) {
          '/settings/auto-import' => _json({
              'enabled': imported,
              'allowed': imported,
            }),
          '/listen' => _json({'session_id': '20260921T100000Z'}),
          '/listen/20260921T100000Z/chunk' => _json({'chunk': 1}),
          '/listen/20260921T100000Z/finish' => () {
              finished = true;
              return _json({'state': 'TRANSCRIBING'});
            }(),
          '/listen/20260921T100000Z' => _json({
              'state': finished ? 'TO_VALIDATE' : 'LISTENING',
              'segments': 12,
              'run_id': '20260921T100100Z',
              'preview': [],
            }),
          '/test-runs/20260921T100100Z' => _json({
              'status': {'state': 'DONE', 'run_id': '20260921T100100Z'},
              'report': '# 🎬 Vidéo\n## ADA',
              'validation': '## CONCLUSION',
              'transcript': '[00:00] ADA',
              'extraction': {},
            }),
          '/test-runs/20260921T100100Z/import' => () {
              imported = true;
              return _json({'video_id': 1});
            }(),
          _ => http.Response('{}', 404),
        };
      }),
    );
    final recorder = _FakeRecorder();
    await tester.pumpWidget(MaterialApp(
        home: LexaListenScreen(
            client: client,
            recorder: recorder,
            pollEvery: const Duration(milliseconds: 10))));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('lexa-listen-start')));
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.textContaining('Écoute en cours'), findsOneWidget);
    expect(calls, contains('POST /listen/20260921T100000Z/chunk'));

    await tester.tap(find.byKey(const ValueKey('lexa-listen-stop')));
    for (var i = 0; i < 30; i++) {
      await tester.pump(const Duration(milliseconds: 20));
    }
    await tester.pumpAndSettle();
    expect(find.text('À vérifier une fois'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('lexa-listen-import')));
    await tester.pumpAndSettle();
    expect(find.text('Plan créé'), findsOneWidget);
    expect(calls, contains('PUT /settings/auto-import'));
    expect(recorder.stopped, isTrue);
  });
}

class _FakeRecorder extends LexaRecorder {
  bool stopped = false;
  bool _on = false;

  @override
  bool get supported => true;

  @override
  bool get running => _on;

  @override
  Future<void> start(
      {required bool shareTab, required ChunkSink onChunk}) async {
    _on = true;
    await onChunk(Uint8List.fromList([1, 2, 3]), 'audio/mp4');
  }

  @override
  Future<void> stop() async {
    _on = false;
    stopped = true;
  }
}
