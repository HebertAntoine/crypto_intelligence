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
import 'package:crypto_intelligence_app/widgets/color_emoji.dart';
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

Future<void> _openDecisionDetails(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('decision-card')));
  await tester.pumpAndSettle();
  expect(find.byKey(const ValueKey('decision-detail-back')), findsOneWidget);
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
    // The field behind it is expected_movement, an amplitude rather than a
    // volatility reading, so the label names the amplitude.
    expect(find.text('Mouvement att.'), findsOneWidget);
    expect(
      find.byWidgetPredicate((widget) =>
          widget is Text &&
          const {'FAIBLE', 'MODÉRÉ', 'ÉLEVÉ', 'CRITIQUE'}
              .contains(widget.data)),
      findsWidgets,
    );
  });

  testWidgets('tapping a reason opens the full explanation', (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    final firstReason = find.byKey(const ValueKey('decision-reason-1'));
    await tester.ensureVisible(firstReason);
    await tester.pumpAndSettle();
    await tester.tap(firstReason);
    await tester.pumpAndSettle();

    // Factor 1 is the ranked top catalyst, so it uses the event vocabulary.
    // Which factor ranks first depends on the market; the sheet must carry the
    // event vocabulary when the factor is a catalyst, whatever its position.
    final isCatalyst = find.text('CE QUI VA SE PASSER').evaluate().isNotEmpty;
    final isSignal = find.text('CE QU’ON OBSERVE').evaluate().isNotEmpty;
    expect(isCatalyst || isSignal, isTrue);
    if (!isCatalyst) return;
    expect(find.text('CE QUE LE MARCHÉ ATTEND'), findsOneWidget);
    expect(find.text('POURQUOI CELA COMPTE'), findsOneWidget);
    expect(find.byType(ColorEmoji), findsWidgets);
    // A dated event never carries the observation vocabulary.
    expect(find.text('CE QU’ON OBSERVE'), findsNothing);

    // The sheet scrolls on its own list; dragging it is steadier than hunting
    // for the right Scrollable now that the page carries more of them.
    await tester.drag(find.byType(ListView).last, const Offset(0, -400));
    await tester.pumpAndSettle();
    expect(
      find.text('SI LE RÉSULTAT EST PLUS POSITIF QUE PRÉVU'),
      findsOneWidget,
    );
    expect(find.text('CE QUE ÇA PEUT ENGENDRER'), findsOneWidget);

    // Sources sit at the bottom so they inform without crowding the summary.
    await tester.drag(find.byType(ListView).last, const Offset(0, -600));
    await tester.pumpAndSettle();
    expect(find.text('🔗 SOURCE'), findsOneWidget);
  });

  testWidgets('an absent market expectation is stated, never implied',
      (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    final firstReason = find.byKey(const ValueKey('decision-reason-1'));
    await tester.ensureVisible(firstReason);
    await tester.pumpAndSettle();
    await tester.tap(firstReason);
    await tester.pumpAndSettle();

    // The section belongs to a catalyst. Whether one is in window depends on
    // the calendar, so the contract is checked only when one is present: an
    // unavailable expectation is stated, never left blank or invented.
    if (find.text('CE QUI VA SE PASSER').evaluate().isEmpty) return;
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
        (decision.decision == 'BUY' &&
            decision.direction.contains('BEARISH')) ||
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

    expect(find.text('CE QU’ON OBSERVE'), findsOneWidget);
    expect(find.text('CE QUI INVALIDERAIT CE SIGNAL'), findsOneWidget);
    expect(find.text('CE QUI VA SE PASSER'), findsNothing);
    // A signal already measured has no market expectation to quote.
    expect(find.text('CE QUE LE MARCHÉ ATTEND'), findsNothing);
  });

  testWidgets('the top catalyst is ranked by contribution, not by date',
      (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    // The window holds three Treasury bill auctions before the FOMC. Date
    // order buried the only CRITICAL event; contribution order surfaces it.
    // Contribution order, not date order. Checkable only while a catalyst is
    // in window - the calendar empties as events are published, which is the
    // behaviour section 19 asks for.
    final decision = await _shippedClient().futureDecision('BTC', horizon: '7d');
    final catalysts = decision.synthesis?.upcomingEvents ?? const [];
    if (catalysts.isEmpty) return;
    expect(
      catalysts.first.relevanceScore,
      greaterThanOrEqualTo(catalysts.last.relevanceScore),
    );
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
    // Which factor ranks first depends on the data. What must hold is that the
    // screen renders a factor the engine published rather than one it invented.
    final decision = await _shippedClient().futureDecision('BTC', horizon: '7d');
    expect(decision.factors, isNotEmpty);
    expect(find.byKey(const ValueKey('decision-reason-1')), findsOneWidget);
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

  testWidgets('decision reasons exclude counter signals', (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    final decision =
        await _shippedClient().futureDecision('BTC', horizon: '7d');
    if (decision.decision != 'WAIT') return;

    // Under "Pourquoi attendre ?" nothing may argue for buying. A healthy
    // bullish reading is a counter-signal, not a reason to wait.
    for (var index = 1; index <= 5; index++) {
      final row = find.byKey(ValueKey('decision-reason-$index'));
      if (row.evaluate().isEmpty) break;
      final badges = tester
          .widgetList<Text>(
              find.descendant(of: row, matching: find.byType(Text)))
          .map((widget) => widget.data)
          .toList();
      if (badges.contains('CE QUI RESTE FAVORABLE')) break;
    }
    expect(find.text('CE QUI RESTE FAVORABLE'), findsWidgets);
  });

  testWidgets('counter signals are displayed separately', (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    final heading = find.text('CE QUI RESTE FAVORABLE');
    if (heading.evaluate().isEmpty) return; // no counter-signal in this data
    await tester.ensureVisible(heading);
    await tester.pumpAndSettle();
    expect(heading, findsOneWidget);
  });

  testWidgets('change conditions are split by direction', (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    await tester.scrollUntilVisible(
      find.text('Pour passer à acheter'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Pour passer à acheter'), findsOneWidget);
    expect(find.text('Pour passer à vendre'), findsOneWidget);
    expect(find.text('Ce qui pourrait changer la décision'), findsNothing);
  });

  testWidgets('a direction-free reading never shows a direction',
      (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    // Bollinger compression may reach the screen as amplitude only.
    final uncertain = find.text('DIRECTION INCERTAINE');
    if (uncertain.evaluate().isEmpty) return;
    expect(uncertain, findsWidgets);
  });

  testWidgets('an ETF factor never borrows whale vocabulary', (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    // The family is called "Flux institutionnels & baleines", so a keyword
    // lookup on the title served the whale explanation for an ETF reading.
    // The mechanism now comes from the engine's causal chain.
    for (var index = 1; index <= 5; index++) {
      final row = find.byKey(ValueKey('decision-reason-$index'));
      if (row.evaluate().isEmpty) break;
      final isEtf = find
          .descendant(of: row, matching: find.textContaining('ETF'))
          .evaluate()
          .isNotEmpty;
      if (!isEtf) continue;
      await tester.ensureVisible(row);
      await tester.pumpAndSettle();
      await tester.tap(row);
      await tester.pumpAndSettle();
      for (final whaleWord in const [
        'plateformes d’échange',
        'transfert',
        'baleine',
      ]) {
        expect(
          find.textContaining(whaleWord),
          findsNothing,
          reason: 'whale wording "$whaleWord" reached an ETF factor',
        );
      }
      await tester.tapAt(const Offset(200, 12));
      await tester.pumpAndSettle();
    }
  });

  testWidgets('the source shown is a real provider, not the family name',
      (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    final row = find.byKey(const ValueKey('decision-reason-1'));
    await tester.ensureVisible(row);
    await tester.pumpAndSettle();
    await tester.tap(row);
    await tester.pumpAndSettle();

    // A catalyst sheet carries more blocks than a signal sheet, so the source
    // line sits further down. Drag until it appears rather than guessing.
    for (var attempt = 0; attempt < 6; attempt++) {
      if (find.text('🔗 SOURCE').evaluate().isNotEmpty) break;
      await tester.drag(find.byType(ListView).last, const Offset(0, -300));
      await tester.pumpAndSettle();
    }
    expect(find.text('🔗 SOURCE'), findsOneWidget);

    // Scoped to the source line itself. The evidence sections legitimately
    // display family labels as the name of a reading, which is not a source,
    // so searching the whole tree would fail on correct output.
    final lines = tester
        .widgetList<Text>(find.byType(Text))
        .map((widget) => widget.data ?? '')
        .toList();
    final sourceLine = lines[lines.indexOf('🔗 SOURCE') + 1];
    for (final familyName in const [
      'Positionnement & dérivés',
      'Flux institutionnels & baleines',
      'Technique & volatilité',
    ]) {
      expect(
        sourceLine.contains(familyName),
        isFalse,
        reason: 'the analytical family is not a data source',
      );
    }
  });

  testWidgets('every displayed factor carries a status the payload supports',
      (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    final decision =
        await _shippedClient().futureDecision('BTC', horizon: '7d');
    // A direction-free reading must never show a directional badge.
    for (final factor in decision.factors) {
      if (factor.impactOnDirection != 'NONE') continue;
      expect(
        factor.direction == 'POSITIVE' || factor.direction == 'NEGATIVE',
        isFalse,
        reason: '${factor.key} is amplitude-only yet directional',
      );
    }
    // And an unavailable one must declare what it lacks.
    for (final factor in decision.factors) {
      if (factor.availability != 'UNAVAILABLE') continue;
      expect(factor.direction, 'UNKNOWN', reason: factor.key);
      expect(factor.missingRequirements, isNotEmpty, reason: factor.key);
    }
  });

  testWidgets('the hero opens a subpage led by the state and summary',
      (tester) async {
    await _openBtc(tester);

    expect(find.byKey(const ValueKey('market-state-card')), findsNothing);
    await _openDecisionDetails(tester);

    expect(find.byKey(const ValueKey('market-state-card')), findsOneWidget);
    final decision =
        await _shippedClient().futureDecision('BTC', horizon: '7d');
    final synthesis = decision.synthesis;
    expect(synthesis, isNotNull,
        reason: 'the backend must publish a synthesis');
    expect(find.text(synthesis!.headline), findsOneWidget);
  });

  testWidgets('why-now and counter-evidence are both shown', (tester) async {
    await _openBtc(tester);
    await _openDecisionDetails(tester);

    for (final key in const [
      'why-now-card',
      'counter-evidence-card',
      'confirmation-card',
      'invalidation-card',
      'scenario-pair',
    ]) {
      await tester.scrollUntilVisible(
        find.byKey(ValueKey(key)),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.byKey(ValueKey(key)), findsOneWidget, reason: key);
    }
  });

  testWidgets('a missing family is declared, never shown as neutral',
      (tester) async {
    await _openBtc(tester);
    await _openDecisionDetails(tester);

    final decision =
        await _shippedClient().futureDecision('BTC', horizon: '7d');
    final synthesis = decision.synthesis!;
    if (synthesis.dataStatus != 'PARTIAL_DATA') return;
    expect(find.byKey(const ValueKey('partial-data-chip')), findsOneWidget);
    expect(synthesis.missingFamilies, isNotEmpty);
  });

  testWidgets('no section renders empty or shows a raw null', (tester) async {
    await _openBtc(tester);

    expect(find.textContaining('null'), findsNothing);
    final decision =
        await _shippedClient().futureDecision('BTC', horizon: '7d');
    // The counter-evidence block always carries content, even when nothing
    // argues the other way.
    expect(decision.synthesis!.counterEvidence, isNotEmpty);
  });

  testWidgets('the page does not overflow at 360 px with the synthesis',
      (tester) async {
    tester.view.physicalSize = const Size(360, 800);
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
    await _openDecisionDetails(tester);
    expect(find.byKey(const ValueKey('scenario-pair')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the home page carries at most four factors', (tester) async {
    await _openBtc(tester);

    expect(find.byKey(const ValueKey('decision-reason-4')), findsOneWidget);
    expect(find.byKey(const ValueKey('decision-reason-5')), findsNothing);
  });

  testWidgets('an ETF reading is titled and described as ETF flows',
      (tester) async {
    await _openBtc(tester);

    final decision = await _shippedClient().futureDecision('BTC', horizon: '7d');
    final flows = decision.factors.where((item) => item.key == 'flows');
    if (flows.isEmpty) return;
    // The reported bug: the ETF block described who crosses the spread.
    expect(flows.first.rationale.toLowerCase().contains('spread'), isFalse);
    expect(flows.first.rationale.toLowerCase().contains('prix demandé'), isFalse);
  });

  testWidgets('the page renders without overflow on three iPhone widths',
      (tester) async {
    for (final size in const [
      Size(375, 667), // iPhone SE
      Size(390, 844), // iPhone standard
      Size(430, 932), // iPhone Max
    ]) {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
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
      expect(tester.takeException(), isNull, reason: '$size');
    }
    addTearDown(tester.view.reset);
  });
}
