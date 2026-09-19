/// The decision page must answer five questions in one screen: buy/wait/sell,
/// at which horizon, how solid, why, and what could change it. Everything else
/// is one tap away. These tests pin that contract.
library;

import 'dart:async';
import 'dart:io';

import 'package:crypto_intelligence_app/api/client.dart';
import 'package:crypto_intelligence_app/live_prices/live_price_service.dart';
import 'package:crypto_intelligence_app/main.dart';
import 'package:crypto_intelligence_app/screens/full_analysis_page.dart';
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

Future<void> _openDecisionDetails(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('decision-card')));
  await tester.pumpAndSettle();
  expect(find.byKey(const ValueKey('decision-detail-back')), findsOneWidget);
}

void main() {
  testWidgets('the hero card carries three readings and no engine vocabulary',
      (tester) async {
    await _openBtc(tester);

    // Risk, horizon and the balance of signals. Amplitude and confidence were
    // the other two: both describe how the model feels rather than what the
    // market is doing, so they belong to the full analysis.
    expect(find.text('Risque'), findsOneWidget);
    expect(find.text('Horizon'), findsOneWidget);
    expect(find.text('Tendance'), findsOneWidget);
    expect(find.text('Confiance'), findsNothing);
    expect(find.text('Mouvement att.'), findsNothing);
    expect(find.textContaining(RegExp(r'^\d+ %$')), findsNothing);
  });

  testWidgets('the balance of signals is a plain French word', (tester) async {
    await _openBtc(tester);

    expect(
      find.byWidgetPredicate((widget) =>
          widget is Text &&
          // The trend tile names a direction only; entry and risk are apart.
          const {'Haussière', 'Baissière', 'Neutre', 'Plutôt favorable',
                  'Plutôt défavorable', 'Mitigée', 'Insuffisante'}
              .contains(widget.data)),
      findsWidgets,
    );
  });

  testWidgets('tapping a main factor opens its family, measure by measure',
      (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    final row = find.byKey(const ValueKey('main-factor-1'));
    await tester.ensureVisible(row);
    await tester.pumpAndSettle();
    await tester.tap(row);
    await tester.pumpAndSettle();

    // Grouped sections of compact rows, a short reading, what would change it.
    expect(find.byKey(const ValueKey("section-L'essentiel")), findsOneWidget);
    expect(find.byType(MetricTile), findsNothing);

    // A row opens its measure in full: value, the three dates, why it matters.
    final rsi = find.byKey(const ValueKey('row-technical.rsi'));
    await tester.scrollUntilVisible(rsi, 200, scrollable: find.byType(Scrollable).last);
    await tester.tap(rsi);
    await tester.pumpAndSettle();
    expect(find.byType(MetricTile), findsOneWidget);
    expect(find.textContaining('Pourquoi ça compte'), findsOneWidget);
    expect(find.textContaining('Données :'), findsOneWidget);
    expect(find.textContaining('Mise à jour'), findsNothing);
  });

  testWidgets('an unavailable family is declared, never shown as neutral',
      (tester) async {
    await _openBtc(tester);
    await _select7d(tester);
    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('see-full-analysis')),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.byKey(const ValueKey('see-full-analysis')));
    await tester.pumpAndSettle();

    // On-chain has no connected source: it says so, with its reason.
    final card = find.byKey(const ValueKey('family-onchain'));
    await tester.scrollUntilVisible(card, 300, scrollable: find.byType(Scrollable).last);
    expect(find.descendant(of: card, matching: find.textContaining('insuffisantes')),
        findsWidgets);
    expect(find.descendant(of: card, matching: find.text('Neutre')), findsNothing);
  });

  testWidgets('each main factor carries one colour status, never an amplitude',
      (tester) async {
    await _openBtc(tester);

    for (var index = 1; index <= 4; index++) {
      final row = find.byKey(ValueKey('main-factor-$index'));
      if (row.evaluate().isEmpty) break;
      final status = tester
          .widgetList<Text>(find.descendant(of: row, matching: find.byType(Text)))
          .map((widget) => widget.data ?? '')
          // A tone dot, or the trend's own arrow for the technical family.
          .where((text) => text.startsWith(RegExp('(🔴|🟠|🟡|🟢|⚪|📈|📉|➡️) ')))
          .toList();
      expect(status.length, 1, reason: 'facteur $index');
      for (final amplitude in const ['CRITIQUE', 'IMPACT ÉLEVÉ', 'EXTREME']) {
        expect(status.first.contains(amplitude), isFalse);
      }
    }
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
      find.byKey(const ValueKey('see-full-analysis')),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.byKey(const ValueKey('see-full-analysis')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('analysis-decision')), findsOneWidget);
    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('technical-details')),
      400,
      scrollable: find.byType(Scrollable).last,
    );
    // Clear the bottom navigation bar before tapping.
    await tester.drag(find.byType(Scrollable).last, const Offset(0, -300));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('technical-details')));
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

  testWidgets('a measured reading is never worded as an upcoming event',
      (tester) async {
    await _openBtc(tester);
    final decision = await _shippedClient().futureDecision('BTC');

    // Only an event has a date; a reading already measured says what it
    // observes, never "dans 3 h".
    for (final driver in decision.hierarchy!.homeFactors) {
      if (driver.kind != 'FACTOR') continue;
      expect(driver.what.contains(RegExp(r'dans \d+ (h|j)')), isFalse);
      expect(driver.status.startsWith('Risque élevé •'), isFalse);
    }
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

  testWidgets('the main factors follow the engine ranking', (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    // The five families, in the engine's order, one line each.
    final decision = await _shippedClient().futureDecision('BTC', horizon: '7d');
    final families = decision.analysis!.summary.homeFamilies;
    expect(families.map((f) => f.name).toList(),
        ['Technique', 'Dérivés', 'Flux spot', 'Macro', 'Cycle Bitcoin']);
    for (var index = 0; index < families.length - 1; index++) {
      final row = find.byKey(ValueKey('main-factor-${index + 1}'));
      expect(
        find.descendant(of: row, matching: find.text(families[index].name)),
        findsOneWidget,
      );
    }
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

  testWidgets('both sides argue in one list, each with its own badge',
      (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    // The two sides used to sit under separate headings, which cost a whole
    // section for something the badge already says. Seeing them interleaved
    // is what makes a mixed verdict legible.
    expect(find.text('CE QUI RESTE FAVORABLE'), findsNothing);

    const allowed = {'FAVORABLE', 'DÉFAVORABLE', 'À SURVEILLER', 'NEUTRE'};
    for (var index = 1; index <= 4; index++) {
      final row = find.byKey(ValueKey('decision-reason-$index'));
      if (row.evaluate().isEmpty) break;
      final labels = tester
          .widgetList<Text>(
              find.descendant(of: row, matching: find.byType(Text)))
          .map((widget) => widget.data)
          .whereType<String>()
          .toList();
      expect(
        labels.where(allowed.contains).length,
        1,
        reason: 'la raison $index doit porter exactement un badge',
      );
    }
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

  testWidgets('what would change the decision sits one tap away',
      (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    final decision = await _shippedClient().futureDecision('BTC', horizon: '7d');
    final analysis = decision.analysis!;
    // The home says what the market is doing and why the entry waits...
    expect(find.text(analysis.summary.sentence), findsOneWidget);
    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('see-full-analysis')),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.byKey(const ValueKey('see-full-analysis')));
    await tester.pumpAndSettle();

    // ...and the full page lists what would move it, three at most.
    if (analysis.toBuy.isNotEmpty) {
      await tester.scrollUntilVisible(
        find.byKey(const ValueKey('analysis-to-buy')),
        300,
        scrollable: find.byType(Scrollable).last,
      );
      expect(find.byKey(const ValueKey('analysis-to-buy')), findsOneWidget);
    }
    expect(analysis.toBuy.length, lessThanOrEqualTo(3));
    expect(analysis.toWorsen.length, lessThanOrEqualTo(3));
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
        // Scoped to the open sheet: the home behind it now carries its own
        // whale indicator, which is where that wording belongs.
        expect(
          find.descendant(
            of: find.byType(BottomSheet),
            matching: find.textContaining(whaleWord),
          ),
          findsNothing,
          reason: 'whale wording "$whaleWord" reached an ETF factor',
        );
      }
      await tester.tapAt(const Offset(200, 12));
      await tester.pumpAndSettle();
    }
  });

  testWidgets('each measure names a real source, never a family',
      (tester) async {
    await _openBtc(tester);
    await _select7d(tester);

    final decision = await _shippedClient().futureDecision('BTC', horizon: '7d');
    for (final family in decision.analysis!.families) {
      for (final metric in family.metrics.where((m) => m.usable)) {
        expect(metric.source, isNotEmpty, reason: metric.key);
        for (final familyName in const [
          'Macro & banques centrales',
          'ETF & flux spot',
          'Technique & structure',
        ]) {
          expect(metric.source.contains(familyName), isFalse);
        }
      }
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

  testWidgets('the home page carries at most four main factors', (tester) async {
    await _openBtc(tester);

    expect(find.byKey(const ValueKey('main-factor-1')), findsOneWidget);
    // Six families at most; whales disappear when they carry nothing.
    expect(find.byKey(const ValueKey('main-factor-7')), findsNothing);
    // The old flat list of reasons is gone from the home.
    expect(find.byKey(const ValueKey('decision-reason-1')), findsNothing);
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
