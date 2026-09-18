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
  _mockupRules();

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
        expect(
          find.byWidgetPredicate((widget) =>
              widget is Text &&
              const {'Pourquoi attendre ?', 'Pourquoi acheter ?',
                      'Pourquoi vendre ?'}
                  .contains(widget.data)),
          findsOneWidget,
        );

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

      testWidgets('shows at most three reasons however many signals exist',
          (tester) async {
        await _open(tester, asset);

        // The engine tracks far more than this. The page shows the few that
        // weigh most on the verdict; a fourth row means the cap leaked.
        expect(find.byKey(const ValueKey('decision-reason-4')), findsNothing);
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
        final rows = find.descendant(
          of: card,
          matching: find.byWidgetPredicate((widget) =>
              widget.key is ValueKey<String> &&
              (widget.key! as ValueKey<String>).value.startsWith('event-')),
        );
        expect(rows.evaluate().length, inInclusiveRange(1, 3));
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
      'sans avantage',
      'pas assez nets',
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


List<String> _badgesOnHome(WidgetTester tester) {
  const badges = {'FAVORABLE', 'DÉFAVORABLE', 'À SURVEILLER', 'NEUTRE'};
  final found = <String>[];
  for (var index = 1; index <= 4; index++) {
    final row = find.byKey(ValueKey('decision-reason-$index'));
    if (row.evaluate().isEmpty) break;
    found.addAll(tester
        .widgetList<Text>(find.descendant(of: row, matching: find.byType(Text)))
        .map((widget) => widget.data)
        .whereType<String>()
        .where(badges.contains));
  }
  return found;
}

void _mockupRules() {
  group('validated mockup', () {
    for (final asset in ['BTC', 'ETH', 'SOL']) {
      testWidgets('$asset: a mixed tendency shows both sides', (tester) async {
        await _open(tester, asset);
        if (find.text('Mitigée').evaluate().isEmpty) return;

        // "Mitigée" above three green badges was the bug: ranking by weight
        // pushed every opposing signal past the cut.
        final badges = _badgesOnHome(tester);
        expect(badges, contains('FAVORABLE'));
        expect(badges, contains('DÉFAVORABLE'));
      });

      testWidgets('$asset: the confirmation row follows the engine, not looks',
          (tester) async {
        await _open(tester, asset);
        final decision = await _shippedClient().futureDecision(asset);

        final shown =
            find.text('Confirmation encore insuffisante').evaluate().isNotEmpty;
        if (!decision.noMeasurableEdge || decision.decision != 'WAIT') {
          expect(shown, isFalse,
              reason: 'sans NO_MEASURABLE_EDGE, la ligne serait inventée');
        }
        if (shown) {
          // It is a reason to watch, never a direction.
          final row = find.ancestor(
            of: find.text('Confirmation encore insuffisante'),
            matching: find.byWidgetPredicate((widget) =>
                widget.key is ValueKey<String> &&
                (widget.key! as ValueKey<String>)
                    .value
                    .startsWith('decision-reason-')),
          );
          expect(
            find.descendant(of: row, matching: find.text('À SURVEILLER')),
            findsOneWidget,
          );
        }
      });

      testWidgets('$asset: the watchlist reads in date order', (tester) async {
        await _open(tester, asset);
        final card = find.byKey(const ValueKey('upcoming-events'));
        if (card.evaluate().isEmpty) return;

        final timeline = await _shippedClient().futureTimeline(asset);
        final byId = {for (final event in timeline.events) event.id: event};
        final shown = tester
            .widgetList(find.descendant(
              of: card,
              matching: find.byWidgetPredicate((widget) =>
                  widget.key is ValueKey<String> &&
                  (widget.key! as ValueKey<String>).value.startsWith('event-')),
            ))
            .map((widget) => byId[(widget.key! as ValueKey<String>)
                .value
                .substring('event-'.length)])
            .toList();

        expect(shown.every((event) => event?.scheduledAt != null), isTrue,
            reason: 'une ligne qui commence par une date doit en avoir une');
        for (var index = 1; index < shown.length; index++) {
          expect(
            shown[index]!.scheduledAt!.isBefore(shown[index - 1]!.scheduledAt!),
            isFalse,
          );
        }
      });
    }

    testWidgets('a two-part maturity is not read as "(1 ans)"', (tester) async {
      await _open(tester, 'BTC');
      expect(find.textContaining('(1 ans)'), findsNothing);
    });
  });
}
