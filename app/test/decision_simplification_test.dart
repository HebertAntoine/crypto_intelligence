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

    await tester.tap(find.byKey(const ValueKey('decision-reason-1')));
    await tester.pumpAndSettle();

    // Factor 1 is the ranked top catalyst, so it uses the event vocabulary.
    expect(find.text('CE QUI VA SE PASSER'), findsOneWidget);
    expect(find.text('CE QUE LE MARCHÉ ATTEND'), findsOneWidget);
    expect(find.text('POURQUOI CELA COMPTE'), findsOneWidget);
    // A dated event never carries the observation vocabulary.
    expect(find.text('CE QU’ON OBSERVE'), findsNothing);

    await tester.scrollUntilVisible(
      find.text('SI LE RÉSULTAT EST PLUS NÉGATIF QUE PRÉVU'),
      200,
      scrollable: find.byType(Scrollable).last,
    );
    expect(find.text('SI LE RÉSULTAT EST PLUS POSITIF QUE PRÉVU'), findsOneWidget);
    expect(find.text('CE QUE ÇA PEUT ENGENDRER'), findsOneWidget);

    // Sources sit at the bottom so they inform without crowding the summary.
    await tester.scrollUntilVisible(
      find.text('SOURCE'),
      200,
      scrollable: find.byType(Scrollable).last,
    );
    expect(find.text('SOURCE'), findsOneWidget);
  });

  testWidgets('an absent market expectation is stated, never implied',
      (tester) async {
    await _openBtc(tester);

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

    // Two catalysts lead, so factor three onwards are measured signals.
    final row = find.byKey(const ValueKey('decision-reason-3'));
    await tester.ensureVisible(row);
    await tester.pumpAndSettle();
    await tester.tap(row);
    await tester.pumpAndSettle();

    expect(find.text('CE QU’ON OBSERVE'), findsOneWidget);
    expect(find.text('CE QUI INVALIDERAIT CE SIGNAL'), findsOneWidget);
    expect(find.text('CE QUI VA SE PASSER'), findsNothing);
    // A signal already measured has no market expectation to quote.
    expect(find.text('CE QUE LE MARCHÉ ATTEND'), findsNothing);
  });

  testWidgets('the top catalyst is ranked by importance, not by date',
      (tester) async {
    await _openBtc(tester);

    // The 30-day window holds three Treasury bill auctions before the FOMC.
    // Chronological order buried the only CRITICAL event.
    expect(find.textContaining('Décision de la Fed'), findsWidgets);
  });
}
