/// The decision page must answer five questions in one screen: buy/wait/sell,
/// at which horizon, how solid, why, and what could change it. Everything else
/// is one tap away. These tests pin that contract.
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

/// Switch to the 7-day horizon, the only one whose window holds the FOMC.
Future<void> _select7d(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('horizon-7d')).last);
  await tester.pumpAndSettle();
}

Future<void> _openBtc(WidgetTester tester) async {
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
}

void main() {
  testWidgets('confidence is a level, never an uncalibrated percentage',
      (tester) async {
    await _openBtc(tester);

    expect(find.text('Confiance'), findsOneWidget);
    final levels = find.byWidgetPredicate((widget) =>
        widget is Text &&
        const {'FAIBLE', 'MOYENNE', 'ÉLEVÉE'}.contains(widget.data));
    expect(levels, findsWidgets);

    // The old card rendered "56 %" right under the Confiance label.
    expect(find.textContaining(RegExp(r'^\d+ %$')), findsNothing);
  });

  testWidgets('risk and expected movement use their own French scales',
      (tester) async {
    await _openBtc(tester);

    expect(find.text('Risque'), findsOneWidget);
    expect(find.text('Mouvement'), findsOneWidget);
    expect(
      find.byWidgetPredicate((widget) =>
          widget is Text &&
          const {'FAIBLE', 'MODÉRÉ', 'ÉLEVÉ', 'CRITIQUE'}.contains(widget.data)),
      findsWidgets,
    );
  });

  testWidgets('tapping a reason opens the full explanation', (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    await tester.tap(find.byKey(const ValueKey('decision-reason-1')));
    await tester.pumpAndSettle();

    // Factor 1 is the ranked top catalyst, so it uses the event vocabulary.
    expect(find.text('📅 CE QUI VA SE PASSER'), findsOneWidget);
    expect(find.text('🎯 CE QUE LE MARCHÉ ATTEND'), findsOneWidget);
    expect(find.text('💡 POURQUOI CELA COMPTE'), findsOneWidget);
    // A dated event never carries the observation vocabulary.
    expect(find.text('🔍 CE QU’ON OBSERVE'), findsNothing);

    await tester.scrollUntilVisible(
      find.text('🔴 SI LE RÉSULTAT EST PLUS NÉGATIF QUE PRÉVU'),
      200,
      scrollable: find.byType(Scrollable).last,
    );
    expect(find.text('🟢 SI LE RÉSULTAT EST PLUS POSITIF QUE PRÉVU'), findsOneWidget);
    expect(find.text('📈 CE QUE ÇA PEUT ENGENDRER'), findsOneWidget);

    // Sources sit at the bottom so they inform without crowding the summary.
    await tester.scrollUntilVisible(
      find.text('🔗 SOURCE'),
      200,
      scrollable: find.byType(Scrollable).last,
    );
    expect(find.text('🔗 SOURCE'), findsOneWidget);
  });

  testWidgets('an absent market expectation is stated, never implied',
      (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    await tester.tap(find.byKey(const ValueKey('decision-reason-1')));
    await tester.pumpAndSettle();

    // Every shipped expectation is UNAVAILABLE, so the sheet must say so
    // rather than leave the section blank or invent a probability.
    expect(
      find.text('Anticipations actuellement indisponibles.'),
      findsOneWidget,
    );
  });

  testWidgets('the impact badge shows a direction, not an amplitude',
      (tester) async {
    await _openBtc(tester);

    // CRITIQUE/ÉLEVÉ/MODÉRÉ answered "how big" under a label promising "which
    // way". The badge now carries the directional reading of the family.
    expect(
      find.byWidgetPredicate((widget) =>
          widget is Text &&
          const {
            'POSITIF',
            'FORTEMENT POSITIF',
            'NÉGATIF',
            'FORTEMENT NÉGATIF',
            'NEUTRE',
            'DIRECTION INCONNUE',
          }.contains(widget.data)),
      findsWidgets,
    );
  });

  testWidgets('the summary carries no engine jargon', (tester) async {
    await _openBtc(tester);

    for (final jargon in const [
      'squeeze=',
      'DVOL',
      'spread crossing',
      'upper third',
      'mid range',
      'percentile',
    ]) {
      expect(
        find.textContaining(jargon),
        findsNothing,
        reason: '"$jargon" must be translated before it reaches the summary',
      );
    }
  });

  testWidgets('a decision that disagrees with its own bias is explained',
      (tester) async {
    await _openBtc(tester);

    // The shipped BTC snapshot is SELL on 24 h. Whenever decision and bias
    // diverge, the page must say why instead of showing both silently.
    final note = find.byKey(const ValueKey('decision-coherence-note'));
    final decision = await _shippedClient().futureDecision('BTC');
    final diverges = (decision.decision == 'SELL' &&
            decision.direction.contains('BULLISH')) ||
        (decision.decision == 'BUY' && decision.direction.contains('BEARISH')) ||
        (decision.decision == 'WAIT' && decision.eventRiskActive);
    expect(note, diverges ? findsOneWidget : findsNothing);
  });

  testWidgets('heavy sections are reachable but off the main page',
      (tester) async {
    await _openBtc(tester);

    expect(find.text('CONTEXTE ACTUEL'), findsNothing);

    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('see-full-details')),
      450,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.byKey(const ValueKey('see-full-details')));
    await tester.pumpAndSettle();

    expect(find.text('Détails complets'), findsOneWidget);
  });

  testWidgets('an analytical family is never rendered as a dated event',
      (tester) async {
    await _openBtc(tester);

    // The regression this replaces showed "Macro & liquidité — le 13 sept. à
    // 17h39", where the date was the analysis timestamp, not an event.
    for (final family in const [
      'Macro & liquidité',
      'Technique & volatilité',
      'Flux institutionnels & baleines',
      'Positionnement & dérivés',
    ]) {
      expect(
        find.textContaining(RegExp('$family\\s*—')),
        findsNothing,
        reason: '"$family" is a family, not something that happens on a date',
      );
    }

    // And the count-of-events phrasing is not an explanation a reader can use.
    expect(find.textContaining('événement(s) macro'), findsNothing);
    expect(find.textContaining('sourcé(s) dans la fenêtre'), findsNothing);
  });

  testWidgets('a measured signal uses observation wording, not event wording',
      (tester) async {
    await _openBtc(tester);

    // On the 24 h horizon the FOMC is out of window and a bill auction cannot
    // be explained, so every factor is a measured signal.
    await tester.tap(find.byKey(const ValueKey('horizon-24h')).last);
    await tester.pumpAndSettle();
    final row = find.byKey(const ValueKey('decision-reason-1'));
    await tester.ensureVisible(row);
    await tester.pumpAndSettle();
    await tester.tap(row);
    await tester.pumpAndSettle();

    expect(find.text('🔍 CE QU’ON OBSERVE'), findsOneWidget);
    expect(find.text('🔄 CE QUI INVALIDERAIT CE SIGNAL'), findsOneWidget);
    expect(find.text('📅 CE QUI VA SE PASSER'), findsNothing);
    // A signal already measured has no market expectation to quote.
    expect(find.text('🎯 CE QUE LE MARCHÉ ATTEND'), findsNothing);
  });

  testWidgets('the top catalyst is ranked by contribution, not by date',
      (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    // The window holds three Treasury bill auctions before the FOMC. Date
    // order buried the only CRITICAL event; contribution order surfaces it.
    expect(find.textContaining('Décision de la Fed'), findsWidgets);
  });

  testWidgets('an unexplainable auction never displaces a real catalyst',
      (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    // Section 6: without bid-to-cover or yield data the engine cannot say why
    // a bill auction matters, so it stays in "À surveiller", not in "Pourquoi".
    for (var index = 1; index <= 5; index++) {
      final row = find.byKey(ValueKey('decision-reason-$index'));
      if (row.evaluate().isEmpty) break;
      expect(
        find.descendant(
          of: row,
          matching: find.textContaining('Adjudication du Trésor'),
        ),
        findsNothing,
      );
    }
  });

  testWidgets('event names shown to the reader are in French', (tester) async {
    await _openBtc(tester);

    // Official English names stay in the Source line only.
    expect(find.textContaining('FOMC monetary policy'), findsNothing);
    expect(find.textContaining('Bill Treasury auction'), findsNothing);
  });

  testWidgets('factor ranking uses decision contribution, not date',
      (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    // The FOMC lands after two Treasury auctions, and a barely-measured
    // technical reading sits beside it. Contribution puts the unresolved
    // Tier-1 event first even though its direction is unknown.
    final first = find.byKey(const ValueKey('decision-reason-1'));
    expect(
      find.descendant(of: first, matching: find.textContaining('Décision de la Fed')),
      findsOneWidget,
    );
  });

  testWidgets('generic factor explanations are forbidden', (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    // Section 6: "Ce facteur fait partie des éléments suivis par l'analyse"
    // says nothing. A factor the engine cannot explain is not shown as a
    // factor at all.
    for (var index = 1; index <= 5; index++) {
      final row = find.byKey(ValueKey('decision-reason-$index'));
      if (row.evaluate().isEmpty) break;
      await tester.ensureVisible(row);
      await tester.pumpAndSettle();
      await tester.tap(row);
      await tester.pumpAndSettle();
      expect(
        find.textContaining('fait partie des éléments suivis'),
        findsNothing,
        reason: 'factor $index falls back to a generic explanation',
      );
      await tester.tapAt(const Offset(200, 12));
      await tester.pumpAndSettle();
    }
  });

  testWidgets('decision change conditions are concrete', (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    for (final filler in const [
      'Un catalyseur prioritaire change de sens',
      'Rétablir les familles indisponibles',
    ]) {
      expect(find.textContaining(filler), findsNothing);
    }
  });

  testWidgets('user facing text is french', (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    for (final english in const [
      'FOMC monetary policy',
      'Treasury auction',
      'Personal Income and Outlays',
      'inflow',
      'outflow',
      'squeeze',
    ]) {
      expect(
        find.textContaining(english),
        findsNothing,
        reason: '"$english" reached a user-facing string',
      );
    }
  });
}
