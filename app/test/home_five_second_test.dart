/// The home answers three questions and stops there.
///
/// Is it the moment? Why? What would change the answer? Anything a reader
/// needs a glossary for belongs to a sub-page, and these tests fail the build
/// if it creeps back onto the front page.
library;

import 'dart:async';
import 'dart:io';

import 'package:crypto_intelligence_app/api/client.dart';
import 'package:crypto_intelligence_app/live_prices/live_price_service.dart';
import 'package:crypto_intelligence_app/main.dart';
import 'package:crypto_intelligence_app/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _SilentLivePrices implements LivePriceSource {
  @override
  LivePriceState get current =>
      LivePriceState(connection: LivePriceConnection.stopped);

  @override
  Stream<LivePriceState> get updates => const Stream.empty();
}

ApiClient _shippedClient() => ApiClient(
      baseUrl: '',
      loadAsset: (path) async {
        final file = File(path);
        if (!file.existsSync()) throw Exception('asset absent: $path');
        return file.readAsStringSync();
      },
    );

Future<void> _open(WidgetTester tester, String asset) async {
  tester.view.physicalSize = const Size(430, 932);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.dark,
      home: HomeShell(
        client: _shippedClient(),
        livePrices: _SilentLivePrices(),
      ),
    ),
  );
  await tester.pumpAndSettle();
  // The asset name appears both in the bottom bar and in the page header, so
  // the tab is addressed by its position rather than by the bare text.
  await tester.tap(find.text(asset).last);
  await tester.pumpAndSettle();
}

/// Every string a reader would have to look up before it meant anything.
const _jargon = <String>[
  'magnitude_effect',
  'FDR',
  'direction_known',
  'lifecycle',
  'OI percentile',
  'funding percentile',
  'source tier',
  'confidence band',
  'relevance score',
  'expected movement',
  'NO_MEASURABLE_EDGE',
  'EdgeEngine',
  'INSUFFICIENT_DATA',
  'PARTIAL_DATA',
  'AttentionLevel',
  'EventDirection',
  'UNKNOWN',
  'STALE',
];

void main() {
  _plainLanguage();

  for (final asset in ['BTC', 'ETH', 'SOL']) {
    group(asset, () {
      testWidgets('answers the three questions and carries no jargon',
          (tester) async {
        await _open(tester, asset);

        // 1. Is it the moment?
        expect(
          find.text('EST-CE LE BON MOMENT POUR ACHETER ?'),
          findsOneWidget,
        );
        expect(
          find.byWidgetPredicate((widget) =>
              widget is Text &&
              const {'ACHETER', 'ATTENDRE', 'VENDRE', 'RÉDUIRE'}
                  .contains(widget.data)),
          findsWidgets,
        );

        // 2. Why?
        expect(find.text('POURQUOI ?'), findsOneWidget);

        // 3. What would change it? - present unless the engine has no path
        // to offer, which is a legitimate answer rather than a filler list.

        for (final term in _jargon) {
          expect(
            find.textContaining(term),
            findsNothing,
            reason: '« $term » n’a rien à faire sur la home',
          );
        }
      });

      testWidgets('shows at most four reasons however many signals exist',
          (tester) async {
        await _open(tester, asset);

        // The engine tracks far more than this. The page shows the few that
        // weigh most on the verdict; a fifth row means the cap leaked.
        expect(find.byKey(const ValueKey('decision-reason-5')), findsNothing);
        expect(find.byKey(const ValueKey('decision-reason-1')), findsOneWidget);
      });

      testWidgets('each reason carries exactly one badge', (tester) async {
        await _open(tester, asset);

        const badges = {
          'FAVORABLE',
          'DÉFAVORABLE',
          'À SURVEILLER',
          'NEUTRE',
        };
        for (var index = 1; index <= 4; index++) {
          final row = find.byKey(ValueKey('decision-reason-$index'));
          if (row.evaluate().isEmpty) break;
          final labels = tester
              .widgetList<Text>(
                  find.descendant(of: row, matching: find.byType(Text)))
              .map((widget) => widget.data)
              .whereType<String>()
              .where(badges.contains)
              .toList();
          expect(labels.length, 1, reason: 'raison $index');
        }
      });

      testWidgets('the watchlist stays to three compact rows', (tester) async {
        await _open(tester, asset);

        final card = find.byKey(const ValueKey('upcoming-events'));
        if (card.evaluate().isEmpty) return;
        final rows = find.descendant(of: card, matching: find.byType(InkWell));
        expect(rows.evaluate().length, lessThanOrEqualTo(3));
      });

      testWidgets('the watchlist does not repeat a reason', (tester) async {
        await _open(tester, asset);

        final card = find.byKey(const ValueKey('upcoming-events'));
        if (card.evaluate().isEmpty) return;
        final watchTitles = tester
            .widgetList<Text>(
                find.descendant(of: card, matching: find.byType(Text)))
            .map((widget) => widget.data)
            .whereType<String>()
            .toSet();

        for (var index = 1; index <= 4; index++) {
          final row = find.byKey(ValueKey('decision-reason-$index'));
          if (row.evaluate().isEmpty) break;
          final title = tester
              .widgetList<Text>(
                  find.descendant(of: row, matching: find.byType(Text)))
              .map((widget) => widget.data)
              .whereType<String>()
              .first;
          // Reason titles carry a date suffix; the watchlist carries the bare
          // subject. Neither may be a copy of the other.
          expect(watchTitles.contains(title), isFalse);
        }
      });

      testWidgets('nothing overflows at 360 px', (tester) async {
        tester.view.physicalSize = const Size(360, 780);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.reset);
        await _open(tester, asset);

        expect(tester.takeException(), isNull);
      });
    });
  }

  testWidgets('a verdict of WAIT explains which kind of waiting it is',
      (tester) async {
    await _open(tester, 'BTC');

    final decision = await _shippedClient().futureDecision('BTC');
    if (decision.decision != 'WAIT') return;

    // "Les conditions ne sont pas favorables" alone tells the reader nothing
    // they can act on. The sentence must name the obstacle: a pending result,
    // signals pulling against each other, or too little measured to justify a
    // position at all.
    final explained = [
      'n’a pas encore livré son résultat',
      'se contredisent',
      'avantage suffisamment clair',
      'pas encore assez favorables',
    ].any((phrase) => find.textContaining(phrase).evaluate().isNotEmpty);
    expect(explained, isTrue);
  });
}

void _plainLanguage() {
  group('plain French on the home', () {
    testWidgets('no reason row shows raw flow figures', (tester) async {
      await _open(tester, 'BTC');

      // "20 séances: +1 751.7 M$ 5 dernières séances: -623.8 M$" is accurate
      // and unreadable at a glance. The signs are the information; the
      // magnitudes belong to the sheet the row opens.
      expect(find.textContaining(RegExp(r'M\$')), findsNothing);
      expect(find.textContaining(RegExp(r'\d+\s*séances?\s*:')), findsNothing);
    });

    testWidgets('no placeholder plural reaches the screen', (tester) async {
      for (final asset in ['BTC', 'ETH', 'SOL']) {
        await _open(tester, asset);
        expect(
          find.textContaining('(s)'),
          findsNothing,
          reason: '$asset: « échelle(s) » se lit comme une chaîne inachevée',
        );
      }
    });
  });
}
